# Enterprise Inventory Orchestrator

An asynchronous FastAPI inventory catalog backed by SQLAlchemy and SQLite. Catalog requests use authenticated, parameterized queries; inventory reconciliations run as FastAPI background tasks and record their outcome in an audit table.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Set `API_KEY_SECRET` in `.env` to a long, unique secret before starting the service. If `.env` already exists, update it without overwriting existing values. The default configuration intentionally has no API key and rejects private requests until one is configured.

```powershell
python -m app.seed
uvicorn app.main:app --reload
```

The application creates missing tables on startup. The seed command is optional for local use and idempotently adds three example products. The SQLite database defaults to `enterprise_inventory.db` in the current directory; set `DATABASE_URL` to use another SQLAlchemy async database URL.

## Run with Docker Compose

Set `API_KEY_SECRET` in `.env` (copy `.env.example` first), then run:

```powershell
docker compose up --build
```

Compose runs the idempotent seed step before starting Uvicorn and persists SQLite data in the `inventory_data` volume. The application also creates the schema on startup.

## API

`/health`, `/docs`, `/redoc`, and `/openapi.json` are public. All other paths require the `X-Api-Key` header.

```powershell
curl.exe -H "X-Api-Key: your-configured-secret" "http://localhost:8000/api/v1/inventory?limit=10&offset=0&min_stock=5&is_active=true"
curl.exe -X POST -H "X-Api-Key: your-configured-secret" -H "Content-Type: application/json" -d '[{"sku":"SKU-1001","stock_quantity":50}]' http://localhost:8000/api/v1/inventory/reconcile
```

The catalog supports `limit` (1-100), `offset` (0 or greater), `min_stock` (inclusive), and `is_active` (`true` by default, or `false` for inactive products). Results are ordered by SKU and include `total`, `limit`, and `offset`.

Reconciliation accepts a JSON array of `{ "sku": string, "stock_quantity": nonnegative integer }`. A successful request returns `202 Accepted` and a reconciliation ID; the request does not wait for reconciliation work. Unknown SKUs reject the entire manifest without changing stock and create a `FAILED` audit entry. Successful runs create `SUCCESS` entries, or `RETRY_FALLBACK` entries when a SQLite lock retry was needed. Exhausted retries and unexpected processing errors are recorded as `FAILED` and surfaced in application logs.

## Architecture and operational decisions

- **Async database access:** SQLAlchemy's async engine and `aiosqlite` handle catalog reads and worker writes without running blocking database calls on the event loop. Each web request and background task owns its own session.
- **Atomic reconciliation:** the worker loads all referenced products, validates that every SKU exists, updates all stock values, and inserts the audit record in one database transaction. An unknown SKU prevents every inventory update in that manifest.
- **SQLite contention:** File-backed SQLite databases use WAL mode so catalog reads can continue during short worker writes, and connections use a finite five-second busy timeout. Only SQLite `database is locked`/`database is busy` operational errors are retried, with three bounded exponential-backoff retries. Each retry starts a fresh transaction; a failure audit is attempted separately after the transaction rolls back.
- **Authentication and observability:** the middleware fails closed when the configured key is empty and compares keys with `secrets.compare_digest`. Application logs are JSON-formatted, and responses include `X-Response-Time-Ms`.
- **Background-task limits:** FastAPI `BackgroundTasks` keeps processing off the request handler, but it is an in-process queue, not a durable job system. Use a persistent queue for workloads that must survive process restarts or be distributed across multiple workers.
- **Deployment:** the multi-stage Docker build installs prebuilt wheels into a non-root runtime image. Compose stores the database in a named volume and seeds only missing product SKUs.

## Tests

```powershell
pytest
```

The async integration tests cover API-key rejection, health-check access, catalog pagination/filtering, and background reconciliation, including audit persistence and event-loop progress while the worker runs.
