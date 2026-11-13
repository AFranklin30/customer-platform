"""Customer HTTP routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, IdempotencyKeyHeader
from app.schemas.customer import CustomerCreate, CustomerPage, CustomerRead
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


@router.get(
    "/customers",
    response_model=CustomerPage,
    summary="List customers",
    description=(
        "Returns customers newest first, ordered by created_at descending and "
        "id descending. limit defaults to 20 and cannot exceed 100. offset "
        "defaults to 0. total counts every customer, not just this page."
    ),
    responses={
        422: {"model": ErrorResponse, "description": "limit or offset is out of range."},
    },
)
def list_customers(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CustomerPage:
    return CustomerService(db).list_customers(limit=limit, offset=offset)


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerRead,
    summary="Get a customer",
    description="Returns one customer by id. The body uses the same fields as create.",
    responses={
        404: {"model": ErrorResponse, "description": "No customer has this id."},
        422: {"model": ErrorResponse, "description": "The id is not a UUID."},
    },
)
def get_customer(customer_id: uuid.UUID, db: DbSession) -> CustomerRead:
    return CustomerService(db).get_customer(customer_id)
