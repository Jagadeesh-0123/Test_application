import asyncio
import logging
import sqlite3
from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.database import AsyncSessionLocal
from app.models import Product, ReconciliationAuditLog

logger = logging.getLogger(__name__)
MAX_RETRIES = 3


class InventoryManifestItem(TypedDict):
    sku: str
    stock_quantity: int


def _is_sqlite_lock_error(error: OperationalError) -> bool:
    original_error = error.orig
    return isinstance(original_error, sqlite3.OperationalError) and any(
        phrase in str(original_error).lower()
        for phrase in ("database is locked", "database is busy")
    )


async def _record_failed_attempt(
    skus_processed: int,
    error_message: str,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    ReconciliationAuditLog(
                        status="FAILED",
                        skus_processed=skus_processed,
                        error_message=error_message[:1000],
                    )
                )
    except Exception:
        logger.exception("Could not persist failed reconciliation audit record")


async def _process_manifest(
    manifest: Sequence[InventoryManifestItem],
    reconciliation_id: str,
    retried: bool,
) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            sku_values = [item["sku"] for item in manifest]
            products_result = await session.execute(
                select(Product).where(Product.sku.in_(sku_values))
            )
            products = {product.sku: product for product in products_result.scalars()}
            missing_skus = sorted(set(sku_values) - products.keys())

            if missing_skus:
                message = f"Unknown SKUs in manifest: {', '.join(missing_skus)}"
                session.add(
                    ReconciliationAuditLog(
                        status="FAILED",
                        skus_processed=len(products),
                        error_message=message[:1000],
                    )
                )
                logger.warning(
                    "Reconciliation %s rejected: %s",
                    reconciliation_id,
                    message,
                )
                return

            for item in manifest:
                products[item["sku"]].stock_quantity = item["stock_quantity"]

            session.add(
                ReconciliationAuditLog(
                    status="RETRY_FALLBACK" if retried else "SUCCESS",
                    skus_processed=len(manifest),
                    error_message=None,
                )
            )

    logger.info(
        "Reconciliation %s completed for %d SKUs",
        reconciliation_id,
        len(manifest),
    )


async def reconcile_inventory(
    manifest: Sequence[InventoryManifestItem],
    reconciliation_id: str,
) -> None:
    for retry_count in range(MAX_RETRIES + 1):
        try:
            await _process_manifest(
                manifest,
                reconciliation_id,
                retried=retry_count > 0,
            )
            return
        except OperationalError as error:
            if not _is_sqlite_lock_error(error):
                await _record_failed_attempt(len(manifest), str(error))
                raise

            if retry_count == MAX_RETRIES:
                await _record_failed_attempt(len(manifest), str(error))
                logger.exception(
                    "Reconciliation %s exhausted %d SQLite lock retries",
                    reconciliation_id,
                    MAX_RETRIES,
                )
                raise

            logger.warning(
                "Reconciliation %s encountered a SQLite lock; retry %d of %d",
                reconciliation_id,
                retry_count + 1,
                MAX_RETRIES,
            )
            await asyncio.sleep(0.05 * (2**retry_count))
        except Exception as error:
            await _record_failed_attempt(len(manifest), str(error))
            logger.exception("Reconciliation %s failed", reconciliation_id)
            raise
