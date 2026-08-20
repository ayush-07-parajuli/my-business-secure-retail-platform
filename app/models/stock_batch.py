"""Inventory stock batch model."""

from __future__ import annotations

from datetime import timedelta

from app.extensions import db
from app.models.base import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class StockBatch(TenantScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Batch-based stock record for a product."""

    __tablename__ = "stock_batches"
    __table_args__ = (
        db.CheckConstraint("quantity_added >= 0", name="ck_stock_batches_quantity_added"),
        db.CheckConstraint(
            "quantity_remaining >= 0",
            name="ck_stock_batches_quantity_remaining",
        ),
        db.UniqueConstraint(
            "business_id",
            "batch_code",
            name="uq_stock_batches_business_batch_code",
        ),
    )

    product_id = db.Column(
        db.String(36),
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_code = db.Column(db.String(100), index=True)
    quantity_added = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    quantity_remaining = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    intended_selling_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    restock_date = db.Column(db.DateTime, nullable=False, default=utc_now)
    expiry_date = db.Column(db.DateTime)
    supplier_name = db.Column(db.String(120))
    supplier_contact = db.Column(db.String(120))
    notes = db.Column(db.Text)

    business = db.relationship("Business", back_populates="stock_batches")
    product = db.relationship("Product", back_populates="stock_batches")
    sale_items = db.relationship("SaleItem", back_populates="stock_batch", lazy=True)

    @property
    def is_expired(self) -> bool:
        """Return True if the batch is expired and still has stock."""

        return bool(
            self.expiry_date
            and self.expiry_date.date() < utc_now().date()
            and self.quantity_remaining > 0
        )

    def is_near_expiry(self, days: int = 30) -> bool:
        """Return True if the batch will expire within the given window."""

        if not self.expiry_date or self.quantity_remaining <= 0:
            return False

        today = utc_now().date()
        threshold = today + timedelta(days=days)
        return today <= self.expiry_date.date() <= threshold

    def __repr__(self) -> str:
        return f"<StockBatch {self.batch_code or self.id}>"
