import asyncio
import sqlite3

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.main import app
from app.models import Product, ReconciliationAuditLog
from app.services import reconciliation_worker


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client


async def add_products() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add_all(
                [
                    Product(
                        sku="SKU-001",
                        name="Mouse",
                        stock_quantity=10,
                        warehouse_location="A",
                        base_price_usd=20.0,
                        is_active=True,
                    ),
                    Product(
                        sku="SKU-002",
                        name="Keyboard",
                        stock_quantity=5,
                        warehouse_location="B",
                        base_price_usd=40.0,
                        is_active=True,
                    ),
                    Product(
                        sku="SKU-003",
                        name="Old cable",
                        stock_quantity=1,
                        warehouse_location="A",
                        base_price_usd=5.0,
                        is_active=False,
                    ),
                ]
            )


@pytest.mark.asyncio
async def test_private_routes_require_api_key_and_health_is_public(
    client,
    monkeypatch,
):
    unauthorized = await client.get("/api/v1/inventory")
    health = await client.get("/health")
    monkeypatch.setattr(settings, "API_KEY_SECRET", "")
    unconfigured = await client.get(
        "/api/v1/inventory",
        headers={"X-Api-Key": "test-api-key"},
    )

    assert unauthorized.status_code == 401
    assert unauthorized.json() == {"detail": "Invalid or missing API key"}
    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}
    assert unconfigured.status_code == 401


@pytest.mark.asyncio
async def test_inventory_pagination_and_filters(client):
    await add_products()
    headers = {"X-Api-Key": "test-api-key"}

    page = await client.get(
        "/api/v1/inventory",
        params={"limit": 1, "offset": 1, "min_stock": 5},
        headers=headers,
    )
    inactive = await client.get(
        "/api/v1/inventory",
        params={"is_active": "false"},
        headers=headers,
    )

    assert page.status_code == 200
    assert page.json()["items"][0]["sku"] == "SKU-002"
    assert page.json()["total"] == 2
    assert page.json()["offset"] == 1
    assert [item["sku"] for item in inactive.json()["items"]] == ["SKU-003"]


@pytest.mark.asyncio
async def test_background_reconciliation_persists_atomically_without_blocking_loop(
    client,
):
    await add_products()
    ticks = 0

    async def keep_event_loop_moving() -> None:
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0)
            ticks += 1

    async def submit_reconciliation():
        return await client.post(
            "/api/v1/inventory/reconcile",
            headers={"X-Api-Key": "test-api-key"},
            json=[
                {"sku": "SKU-001", "stock_quantity": 25},
                {"sku": "SKU-002", "stock_quantity": 30},
            ],
        )

    response, _ = await asyncio.gather(
        submit_reconciliation(),
        keep_event_loop_moving(),
    )

    assert response.status_code == 202
    assert response.json()["items_queued"] == 2
    assert ticks == 20

    async with AsyncSessionLocal() as session:
        products = {
            product.sku: product.stock_quantity
            for product in (await session.scalars(select(Product))).all()
        }
        audits = (await session.scalars(select(ReconciliationAuditLog))).all()

    assert products["SKU-001"] == 25
    assert products["SKU-002"] == 30
    assert len(audits) == 1
    assert audits[0].status == "SUCCESS"
    assert audits[0].skus_processed == 2


@pytest.mark.asyncio
async def test_unknown_sku_fails_manifest_without_partial_updates(client):
    await add_products()

    response = await client.post(
        "/api/v1/inventory/reconcile",
        headers={"X-Api-Key": "test-api-key"},
        json=[
            {"sku": "SKU-001", "stock_quantity": 99},
            {"sku": "UNKNOWN", "stock_quantity": 10},
        ],
    )

    assert response.status_code == 202
    async with AsyncSessionLocal() as session:
        product = await session.get(Product, "SKU-001")
        audit = await session.scalar(select(ReconciliationAuditLog))

    assert product is not None
    assert product.stock_quantity == 10
    assert audit is not None
    assert audit.status == "FAILED"
    assert "UNKNOWN" in (audit.error_message or "")


@pytest.mark.asyncio
async def test_sqlite_lock_retry_records_fallback_status(client, monkeypatch):
    assert (await client.get("/health")).status_code == 200
    await add_products()
    original_process_manifest = reconciliation_worker._process_manifest
    attempts = 0

    async def fail_once_then_process(manifest, reconciliation_id, retried):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError(
                "update products",
                {},
                sqlite3.OperationalError("database is locked"),
            )
        await original_process_manifest(manifest, reconciliation_id, retried)

    monkeypatch.setattr(
        reconciliation_worker,
        "_process_manifest",
        fail_once_then_process,
    )
    await reconciliation_worker.reconcile_inventory(
        [{"sku": "SKU-001", "stock_quantity": 20}],
        "retry-test",
    )

    async with AsyncSessionLocal() as session:
        audit = await session.scalar(select(ReconciliationAuditLog))

    assert attempts == 2
    assert audit is not None
    assert audit.status == "RETRY_FALLBACK"
