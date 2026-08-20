"""Product category model."""

from __future__ import annotations

from app.extensions import db
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Category(TenantScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Tenant-specific product category."""

    __tablename__ = "categories"
    __table_args__ = (
        db.UniqueConstraint("business_id", "name", name="uq_categories_business_name"),
    )

    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    business = db.relationship("Business", back_populates="categories")
    products = db.relationship("Product", back_populates="category", lazy=True)

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
