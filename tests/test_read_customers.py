"""Integration tests for reading customers against PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.database import SessionLocal
from app.main import app
from app.models.customer import Customer

CUSTOMER_FIELDS = {
    "id",
    "email",
    "first_name",
    "last_name",
    "phone",
    "created_at",
    "updated_at",
}


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def create_customer(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/customers",
        json={
            "email": f"{name}@example.com",
            "first_name": name,
            "last_name": "Customer",
            "phone": "+1 555 0100",
        },
        headers={"Idempotency-Key": f"read-{name}"},
    )
    assert response.status_code == 201
    return response.json()


def test_get_customer_returns_the_created_record(client: TestClient) -> None:
    created = create_customer(client, "ada")

    response = client.get(f"/customers/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created
    assert set(response.json()) == CUSTOMER_FIELDS


def test_missing_customer_returns_not_found(client: TestClient) -> None:
    response = client.get(f"/customers/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "customer_not_found", "message": "Customer not found."}
    }


def test_non_uuid_customer_id_is_a_validation_error(client: TestClient) -> None:
    response = client.get("/customers/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_list_uses_only_the_public_customer_fields(client: TestClient) -> None:
    create_customer(client, "ada")

    response = client.get("/customers")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "limit", "offset", "total"}
    assert set(body["items"][0]) == CUSTOMER_FIELDS


def test_list_defaults_to_twenty_customers(client: TestClient) -> None:
    for index in range(21):
        create_customer(client, f"customer{index:02d}")

    response = client.get("/customers")

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["total"] == 21
    assert len(body["items"]) == 20


def test_maximum_limit_is_accepted(client: TestClient) -> None:
    create_customer(client, "ada")

    response = client.get("/customers", params={"limit": 100})

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 100
    assert body["total"] == 1
    assert len(body["items"]) == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_pagination_bounds_are_rejected(client: TestClient, params: dict[str, int]) -> None:
    response = client.get("/customers", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_offset_past_the_end_returns_no_items(client: TestClient) -> None:
    create_customer(client, "ada")

    response = client.get("/customers", params={"offset": 50})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["offset"] == 50
    assert response.json()["limit"] == 20
    assert response.json()["total"] == 1


def test_list_order_is_stable_across_pages(client: TestClient) -> None:
    created = [create_customer(client, name) for name in ("ada", "grace", "lin")]
    shared = datetime(2024, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2024, 6, 1, tzinfo=timezone.utc)
    with SessionLocal() as session:
        session.execute(
            update(Customer)
            .where(Customer.id.in_([uuid.UUID(created[0]["id"]), uuid.UUID(created[1]["id"])]))
            .values(created_at=shared, updated_at=shared)
        )
        session.execute(
            update(Customer)
            .where(Customer.id == uuid.UUID(created[2]["id"]))
            .values(created_at=newer, updated_at=newer)
        )
        session.commit()
        rows = session.scalars(select(Customer)).all()

    expected = [
        str(row.id)
        for row in sorted(rows, key=lambda row: (row.created_at, row.id), reverse=True)
    ]
    first = client.get("/customers", params={"limit": 2, "offset": 0})
    second = client.get("/customers", params={"limit": 2, "offset": 2})
    repeated = client.get("/customers", params={"limit": 2, "offset": 0})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == repeated.json()
    assert [item["id"] for item in first.json()["items"]] == expected[:2]
    assert [item["id"] for item in second.json()["items"]] == expected[2:]
    assert first.json()["total"] == 3
    assert second.json()["total"] == 3
