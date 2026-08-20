"""Sale line item model."""

from __future__ import annotations

from app.extensions import db
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SaleItem(TenantScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Individual sale item tied to a sale transaction."""

    __tablename__ = "sale_items"

    sale_id = db.Column(
        db.String(36),
        db.ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.String(36),
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stock_batch_id = db.Column(
        db.String(36),
        db.ForeignKey("stock_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    actual_selling_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    item_profit = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    sale = db.relationship("Sale", back_populates="items")
    product = db.relationship("Product", back_populates="sale_items")
    stock_batch = db.relationship("StockBatch", back_populates="sale_items")

    def __repr__(self) -> str:
        return f"<SaleItem {self.id}>"
