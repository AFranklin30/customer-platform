"""Health probe tests. These use the test database, not the development database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import engine
from app.main import app


def test_health_reports_database_connectivity() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_hides_database_connection_details(monkeypatch) -> None:
    secret = "postgresql://customer:customer_dev_password@postgres:5432/customer_platform"

    def explode(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(engine, "connect", explode)
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert secret not in response.text
    assert "customer_dev_password" not in response.text
