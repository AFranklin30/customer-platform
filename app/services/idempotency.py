"""Idempotency key rules and the canonical request hash.

The hash covers the validated customer payload, not the raw HTTP bytes.
Equivalent inputs such as mixed-case emails or a missing phone versus an
explicit null therefore replay the same request. The header value itself is
not part of the hash: it identifies the request, and the hash identifies the
payload that request claimed to create.
"""

from __future__ import annotations

import hashlib
import json
import re

from app.schemas.customer import CustomerCreate
from app.services.exceptions import InvalidIdempotencyKeyError

_IDEMPOTENCY_KEY = re.compile(r"[\x21-\x7E]{1,255}")


def validate_idempotency_key(idempotency_key: str | None) -> str | None:
    """Return a cleaned key, or None when the caller did not send one."""

    if idempotency_key is None:
        return None
    cleaned = idempotency_key.strip()
    if _IDEMPOTENCY_KEY.fullmatch(cleaned) is None:
        raise InvalidIdempotencyKeyError
    return cleaned


def canonical_request_hash(data: CustomerCreate) -> str:
    payload = data.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
