"""Customer HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import DbSession, IdempotencyKeyHeader
from app.schemas.customer import CustomerCreate, CustomerRead
from app.schemas.errors import ErrorResponse
from app.services.customer_service import CustomerService

router = APIRouter(tags=["customers"])


@router.post(
    "/customers",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
    description=(
        "Creates a customer. Idempotency-Key is required. Email is unique. "
        "A retry of the same key and payload returns the original customer and "
        "sets Idempotency-Replayed: true. Reusing the key with a different "
        "payload returns 409 and does not create another customer."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "The idempotency key is missing or malformed."},
        409: {
            "model": ErrorResponse,
            "description": "Duplicate email, idempotency payload conflict, or unfinished key.",
        },
        422: {"model": ErrorResponse, "description": "The request body failed validation."},
    },
)
def create_customer(
    payload: CustomerCreate,
    response: Response,
    db: DbSession,
    idempotency_key: IdempotencyKeyHeader,
) -> CustomerRead:
    result = CustomerService(db).create_customer(payload, idempotency_key)
    response.status_code = result.status_code
    if result.replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result.customer
