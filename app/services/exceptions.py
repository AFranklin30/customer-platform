"""Domain errors raised by services and translated at the HTTP boundary."""


class DuplicateEmailError(Exception):
    """The email is already stored for another customer."""


class InvalidIdempotencyKeyError(Exception):
    """The Idempotency-Key header is missing or not usable."""


class IdempotencyConflictError(Exception):
    """The key was already used for a different request body."""


class IdempotencyInProgressError(Exception):
    """The key exists, but no completed response has been stored."""
