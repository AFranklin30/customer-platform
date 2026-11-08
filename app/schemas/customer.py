"""Customer request and response schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_PHONE_CHARACTERS = re.compile(r"^\+?[0-9().\-\s]+$")


class CustomerCreate(BaseModel):
    """Payload for POST /customers.

    Assumptions for this first version:
    - A customer is identified for uniqueness by email only.
    - Email is stored lowercase so Ada@Example.com and ada@example.com are the same customer.
    - ASCII email addresses only. Internationalized addresses are deferred.
    - first_name and last_name are required. There is no separate display name.
    - phone is optional, not unique, and stored as trimmed input rather than a canonical format.
    - Address, status, and external account ids are not part of this version.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "email": "ada@example.com",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "phone": "+1 555 0100",
                }
            ]
        },
    )

    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if any(ord(character) > 127 for character in normalized):
            raise ValueError("Only ASCII email addresses are supported.")
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not _PHONE_CHARACTERS.fullmatch(value):
            raise ValueError("Phone number contains unsupported characters.")
        digit_count = sum(character.isdigit() for character in value)
        if not 7 <= digit_count <= 15:
            raise ValueError("Phone number must contain 7 to 15 digits.")
        return value


class CustomerRead(BaseModel):
    """Customer representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    phone: str | None
    created_at: datetime
    updated_at: datetime
