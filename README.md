# Customer API

Initial backend for creating and reading customers. The application is FastAPI, SQLAlchemy 2, and PostgreSQL. Local Docker Compose runs PostgreSQL, Alembic, and the API. Kubernetes and AWS are not part of this version.

## Architecture

A request moves through four layers:

1. **Route** (`app/api/routes/customers.py`) validates the body and query with Pydantic and reads the `Idempotency-Key` header on create.
2. **Service** (`app/services/customer_service.py`) owns the transaction, uniqueness conflicts, idempotent replay, and missing-customer failures.
3. **Repositories** execute the customer and idempotency reads and writes. They do not choose HTTP status codes.
4. **Models** map to PostgreSQL. Constraints in the database are the final integrity check.

The service is synchronous. Customer creation is a short database transaction, and the idempotency lock is easier to follow with one thread per request than with an async session.

Sessions are opened per request and closed in `get_db`. The service commits a successful create. A failure rolls the transaction back before the error reaches the client. The route does not call `commit`.

Configuration comes from `DATABASE_URL`, `LOG_LEVEL`, and `CORS_ORIGINS`. There is no default database URL. `CORS_ORIGINS` defaults to the local frontend origins below and rejects a wildcard.

## Customer schema

| Column | Required | Rules |
| --- | --- | --- |
| `id` | yes | UUID generated in the application |
| `email` | yes | ASCII email, stored lowercase, unique |
| `first_name` | yes | 1–100 characters |
| `last_name` | yes | 1–100 characters |
| `phone` | no | 7–15 digits, stored trimmed, not unique |
| `created_at` | yes | database timestamp |
| `updated_at` | yes | set on insert; no update endpoint yet |

Assumptions, because these fields were not specified earlier:

- Uniqueness is email only. Two people may share a phone number.
- `Ada@Example.com` and `ada@example.com` are the same customer.
- Internationalized email addresses are rejected.
- Address, status, and an external account id are deferred.
- `POST /customers` requires an `Idempotency-Key` header. A missing or blank key is rejected and stores nothing. The generated OpenAPI schema marks that header required. The runtime check is unchanged: a missing or blank key is still `400 invalid_idempotency_key`, not a validation error.

## Reading customers

`GET /customers/{id}` returns one customer. The body uses the same fields as create. An unknown id is `404 customer_not_found`. A path that is not a UUID is `422 validation_error`.

`GET /customers` returns one page:

```json
{
  "items": [],
  "limit": 20,
  "offset": 0,
  "total": 0
}
```

`items` contains customer objects and no other fields. `limit` defaults to 20 and must be from 1 to 100. `offset` defaults to 0 and must be 0 or greater. `total` counts every customer. Order is `created_at` descending, then `id` descending, so a repeated request for the same page returns the same sequence. A customer created between two page requests can still move a row from one page to the next.

## Idempotency

`idempotency_keys` lives in PostgreSQL. Retries are not stored in memory.

The key row and the customer row commit in one transaction. PostgreSQL blocks a second insert of the same key until the first transaction commits or rolls back:

- Same key and the same normalized payload: the original `201` body is returned again, with `Idempotency-Replayed: true`.
- Same key and a different payload: `409 idempotency_payload_conflict`. No second customer is created.
- The hash is the validated payload. Email case and a missing phone versus `null` normalize to the same request.
- A failed duplicate-email insert rolls back its idempotency row, so a later retry with a new key is not stuck behind a stored failure.
- A committed key always includes the original response. An incomplete key, if one is ever inserted outside this service, returns `409 idempotency_in_progress`.

## Authentication

No authentication design was documented in this repository. This version does not invent one.

Still undecided:

- Which provider issues credentials (for example Cognito, an internal IdP, or application-managed tokens).
- What a caller presents (bearer JWT, session, or mTLS).
- Who may create a customer, and whether email ownership must be proved.
- How services in Kubernetes will authenticate to this API and to RDS.

Until those decisions exist, the API does not check identity. Compose publishes the API on `127.0.0.1:8000` only. Do not expose it outside a trusted network.

Browser callers are limited to `CORS_ORIGINS`. The default allowlist is `http://127.0.0.1:5173` and `http://localhost:5173`. Credentials are not accepted. Allowed methods are `GET`, `POST`, and `OPTIONS`. Allowed request headers are `Content-Type` and `Idempotency-Key`. `Idempotency-Replayed` is exposed to the browser. A wildcard origin is rejected.

## Error shape

```json
{
  "error": {
    "code": "duplicate_email",
    "message": "A customer with this email already exists."
  }
}
```

Validation errors use the same envelope and include `details`.

| Status | Code | When |
| --- | --- | --- |
| 200 |  | `GET /customers/{id}` returns that customer, or `GET /customers` returns one page |
| 201 |  | Customer created, or an idempotent retry of that create |
| 400 | `invalid_idempotency_key` | Header is missing, blank, too long, or not visible ASCII |
| 404 | `customer_not_found` | No customer has the requested id |
| 409 | `duplicate_email` | Email already exists |
| 409 | `idempotency_payload_conflict` | Key reused with a different payload |
| 409 | `idempotency_in_progress` | Key exists without a stored response |
| 422 | `validation_error` | Body, customer id, limit, or offset failed validation |
| 200 |  | `GET /health` and the database accepted a connection |
| 503 |  | `GET /health` could not reach the database. The body is `status` and `database`, both `unavailable` |
| 500 | `internal_error` | Unexpected failure; the transaction is rolled back |

Unexpected failures are logged with a stack trace. The client receives a fixed message, not the exception text.

## Local setup

PostgreSQL 14 or newer is required. The project targets Python 3.12+. The test run for this version used Python 3.13.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
createdb customer_platform
cp .env.example .env
```

Edit `.env` so `DATABASE_URL` uses the `postgresql+psycopg://` driver and your local user. Then:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive docs are at `http://127.0.0.1:8000/docs`.

## Docker Compose

Compose runs three services on one network: `postgres`, `migrate`, and `api`. The containers receive `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST=postgres`, `POSTGRES_PORT`, and `POSTGRES_DB`. They do not receive the host `DATABASE_URL`. The application builds its connection URL with SQLAlchemy's `URL.create`, which encodes the password. PostgreSQL is not published on the host, so it does not share port 5432 with a local development database. The API is published on `127.0.0.1:8000` only, because callers are not authenticated yet. Customer rows live in the named volume `postgres_data`.

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs migrate
```

Stop the containers and keep the database volume:

```bash
docker compose down
```

`docker compose down -v` deletes that volume and the customer rows in it.

`GET /health` returns `{"status":"ok","database":"ok"}` when the process can run `SELECT 1`. It does not return the database URL.

## Tests

Pytest applies `alembic upgrade head` to a database whose name ends with `_test` (default `customer_platform_test`) and truncates tables around each test. It will not run against a database that does not end with `_test`.

```bash
pytest
```

Override the target with `TEST_DATABASE_URL` if needed. The URL still has to use `postgresql+psycopg://` and a `_test` database name.

## Migrations

`alembic/versions/0001_initial_schema.py` creates `customers` and `idempotency_keys`.

Database-enforced rules:

- `uq_customers_email`
- `ck_customers_email_lowercase`
- `uq_idempotency_keys_key`
- `ck_idempotency_keys_response_complete`

## Limitations

- There is no update or delete for a customer. `GET /health` only reports process and database reachability.
- `updated_at` changes only when an update path exists.
- Idempotency keys are not expired or deleted.
- The API does not authenticate callers.
- Phone numbers are not canonicalized to E.164.
