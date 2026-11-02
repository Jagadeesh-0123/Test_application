import asyncio
import logging

from sqlalchemy import select

from app.database import AsyncSessionLocal, Base, engine
from app.models import Product

logger = logging.getLogger(__name__)

SEED_PRODUCTS = (
    Product(
        sku="SKU-1001",
        name="Wireless Mouse",
        stock_quantity=42,
        warehouse_location="WH-A",
        base_price_usd=24.99,
        is_active=True,
    ),
    Product(
        sku="SKU-1002",
        name="USB-C Hub",
        stock_quantity=18,
        warehouse_location="WH-B",
        base_price_usd=49.50,
        is_active=True,
    ),
    Product(
        sku="SKU-1003",
        name="Legacy Keyboard",
        stock_quantity=0,
        warehouse_location="WH-A",
        base_price_usd=35.00,
        is_active=False,
    ),
)


async def seed_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            existing_skus = set(
                (await session.scalars(select(Product.sku))).all()
            )
            session.add_all(
                product
                for product in SEED_PRODUCTS
                if product.sku not in existing_skus
            )

    logger.info("Database schema is ready and seed products are present.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
