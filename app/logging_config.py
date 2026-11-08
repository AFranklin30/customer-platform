"""Application logging setup."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configure process logging.

    SQL statement logging stays at WARNING so customer email addresses in
    bound parameters are not written to the log on every query.
    """

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
