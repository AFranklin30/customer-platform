"""Customer table access."""

from __future__ import annotations

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
