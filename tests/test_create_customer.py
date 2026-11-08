"""Integration tests for POST /customers against PostgreSQL."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from app.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.idempotency import IdempotencyKey
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerCreate
from app.services.customer_service import CreateCustomerResult, CustomerService
from app.services.exceptions import DuplicateEmailError, IdempotencyInProgressError
from app.services.idempotency import canonical_request_hash


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def customer_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "email": "ada@example.com",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "phone": "+1 555 0100",
    }
    body.update(overrides)
    return body


def customer_count() -> int:
    with SessionLocal() as session:
        return int(session.scalar(select(func.count()).select_from(Customer)) or 0)


def idempotency_count() -> int:
    with SessionLocal() as session:
        return int(session.scalar(select(func.count()).select_from(IdempotencyKey)) or 0)


def test_create_customer_persists_and_returns_201(client: TestClient) -> None:
    response = client.post("/customers", json=customer_body())

    assert response.status_code == 201
    body = response.json()
    customer_id = uuid.UUID(body["id"])
    assert body["email"] == "ada@example.com"
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["phone"] == "+1 555 0100"
    assert body["created_at"] == body["updated_at"]
    assert "idempotency-replayed" not in response.headers

    with SessionLocal() as session:
        stored = session.get(Customer, customer_id)
        assert stored is not None
        assert stored.email == "ada@example.com"
        assert stored.first_name == "Ada"
        assert stored.phone == "+1 555 0100"


def test_missing_required_fields(client: TestClient) -> None:
    response = client.post("/customers", json={})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    locations = {tuple(detail["loc"]) for detail in error["details"]}
    assert ("body", "email") in locations
    assert ("body", "first_name") in locations
    assert ("body", "last_name") in locations
    assert customer_count() == 0


def test_invalid_email(client: TestClient) -> None:
    response = client.post("/customers", json=customer_body(email="not-an-email"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert customer_count() == 0


def test_invalid_phone(client: TestClient) -> None:
    response = client.post("/customers", json=customer_body(phone="123"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert customer_count() == 0


def test_blank_name_is_rejected(client: TestClient) -> None:
    response = client.post("/customers", json=customer_body(first_name="   "))

    assert response.status_code == 422
    assert customer_count() == 0


def test_unknown_field_is_rejected(client: TestClient) -> None:
    response = client.post("/customers", json=customer_body(nickname="A"))

    assert response.status_code == 422
    assert customer_count() == 0


def test_duplicate_email_conflict(client: TestClient) -> None:
    assert client.post("/customers", json=customer_body()).status_code == 201

    response = client.post(
        "/customers",
        json=customer_body(first_name="Augusta"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_email"
    assert customer_count() == 1


def test_duplicate_email_is_case_insensitive(client: TestClient) -> None:
    created = client.post("/customers", json=customer_body(email="Ada@Example.com"))
    assert created.status_code == 201
    assert created.json()["email"] == "ada@example.com"

    duplicate = client.post("/customers", json=customer_body(email="ADA@example.com"))

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_email"
    assert customer_count() == 1


def test_idempotent_replay_returns_the_original_customer(client: TestClient) -> None:
    headers = {"Idempotency-Key": "create-ada-1"}
    first_body = customer_body(email="Ada@Example.com")
    first_body.pop("phone")
    second_body = customer_body(email="ada@example.com", phone=None)
    first = client.post("/customers", json=first_body, headers=headers)
    second = client.post("/customers", json=second_body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert second.headers["idempotency-replayed"] == "true"
    assert customer_count() == 1
    assert idempotency_count() == 1

    with SessionLocal() as session:
        record = session.scalar(select(IdempotencyKey))
        assert record is not None
        assert record.response_code == 201
        assert record.response_body is not None
        assert record.response_body["id"] == first.json()["id"]


def test_idempotency_key_with_different_payload_conflicts(client: TestClient) -> None:
    headers = {"Idempotency-Key": "create-ada-2"}
    first = client.post("/customers", json=customer_body(), headers=headers)
    conflict = client.post(
        "/customers",
        json=customer_body(first_name="Grace"),
        headers=headers,
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_payload_conflict"
    assert customer_count() == 1
    with SessionLocal() as session:
        stored = session.scalar(select(Customer))
        assert stored is not None
        assert stored.first_name == "Ada"


def test_invalid_idempotency_key_does_not_create_a_customer(client: TestClient) -> None:
    response = client.post(
        "/customers",
        json=customer_body(),
        headers={"Idempotency-Key": "not a valid key"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"
    assert customer_count() == 0
    assert idempotency_count() == 0


def test_duplicate_email_rolls_back_the_failed_idempotency_key(client: TestClient) -> None:
    first = client.post(
        "/customers",
        json=customer_body(),
        headers={"Idempotency-Key": "winner-key"},
    )
    failed = client.post(
        "/customers",
        json=customer_body(first_name="Grace"),
        headers={"Idempotency-Key": "loser-key"},
    )

    assert first.status_code == 201
    assert failed.status_code == 409
    assert failed.json()["error"]["code"] == "duplicate_email"
    with SessionLocal() as session:
        keys = session.scalars(select(IdempotencyKey.idempotency_key)).all()
    assert keys == ["winner-key"]


def test_unexpected_error_rolls_back_and_hides_internals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(self: CustomerRepository, customer: Customer) -> Customer:
        raise RuntimeError("disk failed")

    monkeypatch.setattr(CustomerRepository, "add", explode)

    # Starlette's server-error middleware returns the 500 response and then
    # re-raises. This client keeps the response so the body can be checked.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/customers",
            json=customer_body(),
            headers={"Idempotency-Key": "rollback-key"},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "disk failed" not in response.text
    assert customer_count() == 0
    assert idempotency_count() == 0


def test_incomplete_idempotency_record_reports_conflict() -> None:
    payload = CustomerCreate(
        email="ada@example.com",
        first_name="Ada",
        last_name="Lovelace",
        phone=None,
    )
    with SessionLocal() as session:
        session.add(
            IdempotencyKey(
                idempotency_key="still-running",
                request_hash=canonical_request_hash(payload),
            )
        )
        session.commit()

        with pytest.raises(IdempotencyInProgressError):
            CustomerService(session).create_customer(payload, "still-running")

    assert customer_count() == 0


def test_database_rejects_uppercase_email_and_duplicate_email() -> None:
    with SessionLocal() as session:
        session.add(
            Customer(email="Ada@Example.com", first_name="Ada", last_name="Lovelace")
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(Customer(email="ada@example.com", first_name="Ada", last_name="Lovelace"))
        session.commit()
        session.add(Customer(email="ada@example.com", first_name="Grace", last_name="Hopper"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_migrations_are_at_head_and_constraints_exist() -> None:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect, text

    from app.database import engine

    root = Path(__file__).resolve().parents[1]
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("script_location", str(root / "alembic"))
    head = ScriptDirectory.from_config(configuration).get_current_head()
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        constraint_names = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conname IN "
                    "('uq_customers_email', 'ck_customers_email_lowercase', "
                    "'uq_idempotency_keys_key', 'ck_idempotency_keys_response_complete')"
                )
            )
        }
        table_names = set(inspect(connection).get_table_names())

    assert version == head == "0001_initial"
    assert {"customers", "idempotency_keys", "alembic_version"} <= table_names
    assert constraint_names == {
        "uq_customers_email",
        "ck_customers_email_lowercase",
        "uq_idempotency_keys_key",
        "ck_idempotency_keys_response_complete",
    }


def test_concurrent_requests_with_the_same_idempotency_key_create_one_customer() -> None:
    payload = CustomerCreate(**customer_body())

    def attempt(index: int) -> CreateCustomerResult:
        del index
        with SessionLocal() as session:
            return CustomerService(session).create_customer(payload, "concurrent-same-key")

    results, errors = _run_together(8, attempt)

    assert errors == []
    assert len(results) == 8
    assert len({result.customer.id for result in results}) == 1
    assert sum(result.replayed for result in results) == 7
    assert customer_count() == 1
    assert idempotency_count() == 1


def test_concurrent_duplicate_email_creates_one_customer() -> None:
    def attempt(index: int) -> CreateCustomerResult:
        payload = CustomerCreate(
            email="shared@example.com",
            first_name=f"Person{index}",
            last_name="Test",
            phone=None,
        )
        with SessionLocal() as session:
            return CustomerService(session).create_customer(payload, None)

    results, errors = _run_together(8, attempt)

    assert len(results) == 1
    assert len(errors) == 7
    assert all(isinstance(error, DuplicateEmailError) for error in errors)
    assert customer_count() == 1
    assert idempotency_count() == 0


def test_concurrent_same_email_with_different_keys_keeps_one_record() -> None:
    payload = CustomerCreate(**customer_body(email="race@example.com"))

    def attempt(index: int) -> CreateCustomerResult:
        with SessionLocal() as session:
            return CustomerService(session).create_customer(payload, f"race-key-{index}")

    results, errors = _run_together(8, attempt)

    assert len(results) == 1
    assert len(errors) == 7
    assert all(isinstance(error, DuplicateEmailError) for error in errors)
    assert customer_count() == 1
    assert idempotency_count() == 1


def _run_together(
    workers: int,
    operation: Callable[[int], CreateCustomerResult],
) -> tuple[list[CreateCustomerResult], list[BaseException]]:
    barrier = threading.Barrier(workers)
    results: list[CreateCustomerResult] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def run(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            outcome = operation(index)
        except Exception as exc:
            with lock:
                errors.append(exc)
            return
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    return results, errors
