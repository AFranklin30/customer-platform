"""Customer table access."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer


class CustomerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, customer: Customer) -> Customer:
        self._session.add(customer)
        self._session.flush()
        self._session.refresh(customer)
        return customer

    def get_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        return self._session.get(Customer, customer_id)

    def list_page(self, *, limit: int, offset: int) -> tuple[list[Customer], int]:
        """Return one page and the unpaged row count.

        Order is newest first. id is the tie-break so two rows with the same
        created_at stay in one sequence across requests.
        """

        total = self._session.scalar(select(func.count()).select_from(Customer))
        rows = self._session.scalars(
            select(Customer)
            .order_by(Customer.created_at.desc(), Customer.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), int(total or 0)
