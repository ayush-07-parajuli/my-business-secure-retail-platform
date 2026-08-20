"""Product model."""

from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Product(TenantScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Tenant-scoped product catalog entry."""

    __tablename__ = "products"
    __table_args__ = (
        db.UniqueConstraint("business_id", "sku", name="uq_products_business_sku"),
    )

    category_id = db.Column(db.String(36), db.ForeignKey("categories.id", ondelete="SET NULL"))
    name = db.Column(db.String(160), nullable=False, index=True)
    sku = db.Column(db.String(100), index=True)
    barcode = db.Column(db.String(100), index=True)
    unit_type = db.Column(db.String(40), nullable=False, default="unit")
    default_selling_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    min_stock_level = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    shelf_life_days = db.Column(db.Integer)
    description = db.Column(db.Text)
    image_path = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    business = db.relationship("Business", back_populates="products")
    category = db.relationship("Category", back_populates="products")
    stock_batches = db.relationship(
        "StockBatch",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy=True,
    )
    sale_items = db.relationship("SaleItem", back_populates="product", lazy=True)

    @property
    def current_stock_quantity(self) -> Decimal:
        """Aggregate remaining quantity across stock batches."""

        return sum(
            (batch.quantity_remaining or Decimal("0") for batch in self.stock_batches),
            Decimal("0"),
        )

    @property
    def is_low_stock(self) -> bool:
        """Return True when the product is at or below its minimum stock level."""

        return self.current_stock_quantity <= (self.min_stock_level or Decimal("0"))

    def __repr__(self) -> str:
        return f"<Product {self.name}>"
