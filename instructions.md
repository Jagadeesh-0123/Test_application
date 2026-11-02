# Take-Home Challenge: Enterprise Inventory Orchestrator

## 📋 Challenge Overview
You are tasked with implementing a modern, highly observable **Inventory Catalog & Asynchronous Reconciliation Engine** using **FastAPI** and **SQLite**. 

In an enterprise landscape, backend architectures must remain highly concurrent. Heavy database transformations and batch adjustments cannot happen blockingly on the web thread; they must be offloaded cleanly while ensuring isolation and thread safety.

---


📋 Context

In a distributed enterprise environment, APIs must be fast, secure, observable, and resilient. Operations like synchronizing external data or running optimization algorithms cannot happen blockingly on the web thread; they must be offloaded or handled concurrently.
You are building an InventoryOrchestration Service. This system must expose high-performance endpoints, run background reconciliation tasks safely, track client API usage via customized middleware, and maintain a highly structured, observable trace of its operations.

---

## 🛠️ Assignment Technical Specifications

### 1. Database Model Implementation (`app/models.py`)
Utilizing SQLAlchemy or SQLModel alongside the configured `aiosqlite` motor, establish definitions matching the schema properties outlined below:
* **`Product`**: `sku` (String, PK), `name` (String), `stock_quantity` (Integer), `warehouse_location` (String), `base_price_usd` (Float), `is_active` (Boolean).
* **`ReconciliationAuditLog`**: `id` (Integer, Primary Key, Auto-increment), `timestamp` (DateTime), `status` (String: constrained strictly to `'SUCCESS'`, `'RETRY_FALLBACK'`, or `'FAILED'`), `skus_processed` (Integer), `error_message` (String, Nullable).

### 2. Custom Security Middleware (`app/middleware.py`)
Construct and configure a custom application-level token validation interceptor:
* Intercept all inbound requests on private endpoints checking for an incoming `X-Api-Key` string header.
* Match the header against the configured environment string value (`API_KEY_SECRET`). 
* Reject non-matching or missing configurations directly, returning a `401 Unauthorized` JSON response before hitting system endpoint routing logic.

### 3. Asynchronous Reconciliation Engine (`app/services/reconciliation_worker.py`)
Build out the non-blocking inventory ledger reconciliation engine:
* **Asynchronous Execution**: The `/api/v1/inventory/reconcile` route handles bulk raw inventory manifests. It must instantly offload processing tasks to FastAPI's native `BackgroundTasks` handler and immediately return a `202 Accepted` tracking response to the caller.
* **Processing Mechanics & Transactional Boundaries**:
  * The background worker matches incoming data logs with rows in the `Product` table.
  * To simulate complex enterprise computation, the background worker must update stock counts, flag unexpected mismatches, and ensure write actions perform as an atomic unit transaction.
  * **Resilience Mechanism**: If a database concurrency deadlock or locking collision happens during processing (e.g., simulating a SQLite file write lock), the engine must gracefully execute up to 3 retry passes before raising errors, and finally record a logging snapshot row into `ReconciliationAuditLog`.

### 4. API Pagination & Filtering (`app/routers/inventory.py`)
Extend query controls over the core search and delivery components:
* Implement robust client-facing offset or cursor-based pagination parameters (`limit`, `offset`).
* Support server-side catalog filtering criteria, including query parameters to target records by `min_stock` status or active state properties (`is_active == True`).

### 5. Deployment Packaging (Docker) (Bonus points if you attempt correctly or complete this)
Provide configuration setup allowing clean deployment installation:
* **`Dockerfile`**: A multi-stage runtime profile optimized for minimal target storage spaces.
* **`docker-compose.yml`**: Automatically boots the container environment, instantiates the database schema file safely, and executes an automated database seeding step upon startup.

---

## 🔬 Testing Criteria
Your task requires delivering unit and integration test blocks verified through running `pytest`.
Ensure coverage captures:
1. Rejection of unauthenticated route access requests by the `X-Api-Key` middleware.
2. Accurate array offsets or cursor positions slicing paginated data sets returned on catalog query fetches.
3. Concurrency verification showing that triggering bulk reconciliation operates in a non-blocking loop and correctly saves matching logs to `ReconciliationAuditLog`.

---

## 🎯 Evaluation Metric Criteria
* **Async Comprehension:** Clear structural understanding of handling FastAPI event loops and preventing thread blocking during heavy database I/O processing.
* **SQL & Transactional Guardrails:** Clean execution of safe transactional isolation states, schema handling boundaries, and mitigation of potential write races.
* **Production Literacy:** Formatting structured application JSON logs, parameterizing processing requests to block injection vulnerabilities, and isolating test cases.
* **Comprehensive README.md:**
	• Instructions to spin up the app natively or via Docker Compose.
	• All the decisions you have taken to complete this project.
    • An architectural breakdown explaining how the background task updates state without causing race conditions or locking the SQLite database during concurrent web reads.


