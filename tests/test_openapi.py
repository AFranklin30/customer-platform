"""Generated OpenAPI contract for customer routes."""

from __future__ import annotations

from app.main import app


def test_create_customer_idempotency_key_is_required_in_openapi() -> None:
    schema = app.openapi()
    parameters = schema["paths"]["/customers"]["post"]["parameters"]
    header = next(
        parameter
        for parameter in parameters
        if parameter.get("in") == "header"
        and str(parameter.get("name", "")).lower() == "idempotency-key"
    )

    assert header["required"] is True
    assert header["schema"]["type"] == "string"


def test_read_routes_do_not_require_an_idempotency_key() -> None:
    schema = app.openapi()
    list_parameters = schema["paths"]["/customers"]["get"].get("parameters", [])
    detail_parameters = schema["paths"]["/customers/{customer_id}"]["get"].get("parameters", [])

    assert all(parameter.get("name") != "Idempotency-Key" for parameter in list_parameters)
    assert all(parameter.get("name") != "Idempotency-Key" for parameter in detail_parameters)
