from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.database import get_db
from app.models import Product
from app.services.reconciliation_worker import (
    InventoryManifestItem as WorkerManifestItem,
    reconcile_inventory,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    stock_quantity: int
    warehouse_location: str
    base_price_usd: float
    is_active: bool


class InventoryManifestItem(BaseModel):
    sku: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
    ]
    stock_quantity: int = Field(ge=0)


class InventoryPage(BaseModel):
    items: list[ProductResponse]
    total: int
    limit: int
    offset: int


@router.get("")
async def get_paginated_inventory(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_stock: int | None = Query(default=None, ge=0),
    is_active: bool | None = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> InventoryPage:
    filters = []
    if min_stock is not None:
        filters.append(Product.stock_quantity >= min_stock)
    if is_active is not None:
        filters.append(Product.is_active.is_(is_active))

    total = await db.scalar(select(func.count()).select_from(Product).where(*filters))
    products = await db.scalars(
        select(Product)
        .where(*filters)
        .order_by(Product.sku)
        .offset(offset)
        .limit(limit)
    )
    return InventoryPage(
        items=[ProductResponse.model_validate(product) for product in products],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.post("/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def trigger_bulk_reconciliation(
    background_tasks: BackgroundTasks,
    manifest: list[InventoryManifestItem],
) -> dict[str, str | int]:
    reconciliation_id = str(uuid4())
    worker_manifest = [
        WorkerManifestItem(sku=item.sku, stock_quantity=item.stock_quantity)
        for item in manifest
    ]
    background_tasks.add_task(
        reconcile_inventory,
        worker_manifest,
        reconciliation_id,
    )
    return {
        "reconciliation_id": reconciliation_id,
        "status": "accepted",
        "items_queued": len(worker_manifest),
    }
