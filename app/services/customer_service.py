"""Create customers and persist idempotent retries.

The idempotency row and the customer row commit together. PostgreSQL's unique
index on idempotency_keys.idempotency_key is the concurrency lock: a second
transaction inserting the same key waits until the first transaction commits
or rolls back. After the wait, the second transaction replays the stored
response, or it becomes the winner if the first transaction rolled back.
Nothing about this state is stored in process memory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.idempotency import IdempotencyKey
from app.repositories.customer_repository import CustomerRepository
from app.repositories.idempotency_repository import IdempotencyRepository
from app.schemas.customer import CustomerCreate, CustomerRead
from app.services.exceptions import (
    DuplicateEmailError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
)
from app.services.idempotency import canonical_request_hash, validate_idempotency_key

logger = logging.getLogger(__name__)

_CUSTOMER_EMAIL_CONSTRAINT = "uq_customers_email"
_IDEMPOTENCY_KEY_CONSTRAINT = "uq_idempotency_keys_key"


@dataclass(frozen=True)
class CreateCustomerResult:
    customer: CustomerRead
    replayed: bool
    status_code: int


class CustomerService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._customers = CustomerRepository(session)
        self._idempotency = IdempotencyRepository(session)

    def create_customer(
        self,
        data: CustomerCreate,
        idempotency_key: str | None,
    ) -> CreateCustomerResult:
        # Reject a missing key before opening the create transaction.
        key = validate_idempotency_key(idempotency_key)
        try:
            return self._create_customer(data, key)
        except Exception:
            # Expected failures roll back before they are re-raised. This also
            # covers an unexpected failure after a flush and before commit.
            self._session.rollback()
            raise

    def _create_customer(
        self,
        data: CustomerCreate,
        key: str,
    ) -> CreateCustomerResult:
        request_hash = canonical_request_hash(data)
        record = IdempotencyKey(idempotency_key=key, request_hash=request_hash)
        try:
            self._idempotency.add(record)
        except IntegrityError as exc:
            self._session.rollback()
            if _constraint_name(exc) != _IDEMPOTENCY_KEY_CONSTRAINT:
                raise
            return self._replay(key, request_hash)

        customer = Customer(
            email=data.email,
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
        )
        try:
            self._customers.add(customer)
        except IntegrityError as exc:
            self._session.rollback()
            if _constraint_name(exc) == _CUSTOMER_EMAIL_CONSTRAINT:
                logger.info("duplicate_email")
                raise DuplicateEmailError from exc
            raise

        body = CustomerRead.model_validate(customer)
        record.response_code = 201
        record.response_body = body.model_dump(mode="json")

        self._session.commit()
        logger.info("customer_created customer_id=%s", customer.id)
        return CreateCustomerResult(customer=body, replayed=False, status_code=201)

    def _replay(self, key: str, request_hash: str) -> CreateCustomerResult:
        record = self._idempotency.get_by_key(key)
        if record is None:
            raise RuntimeError(
                "The idempotency key conflicted, but no stored request was visible afterward."
            )
        if record.request_hash != request_hash:
            logger.warning("idempotency_payload_conflict")
            raise IdempotencyConflictError
        if record.response_code is None or record.response_body is None:
            logger.warning("idempotency_in_progress")
            raise IdempotencyInProgressError
        customer = CustomerRead.model_validate(record.response_body)
        logger.info("customer_create_replayed customer_id=%s", customer.id)
        return CreateCustomerResult(
            customer=customer,
            replayed=True,
            status_code=record.response_code,
        )


def _constraint_name(exc: IntegrityError) -> str | None:
    original = exc.orig
    diagnostic = getattr(original, "diag", None)
    if diagnostic is not None:
        name = getattr(diagnostic, "constraint_name", None)
        if name:
            return str(name)
    message = str(original)
    for name in (
        _IDEMPOTENCY_KEY_CONSTRAINT,
        _CUSTOMER_EMAIL_CONSTRAINT,
        "ck_customers_email_lowercase",
    ):
        if name in message:
            return name
    return None
