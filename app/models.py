from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warehouse_location: Mapped[str] = mapped_column(String(255), nullable=False)
    base_price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ReconciliationAuditLog(Base):
    __tablename__ = "reconciliation_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCESS', 'RETRY_FALLBACK', 'FAILED')",
            name="ck_reconciliation_audit_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    skus_processed: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)