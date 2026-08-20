"""Customer model."""

from __future__ import annotations

from app.extensions import db
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Customer(TenantScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Tenant-scoped customer record."""

    __tablename__ = "customers"

    name = db.Column(db.String(160), nullable=False, index=True)
    phone = db.Column(db.String(30), index=True)
    email = db.Column(db.String(255))
    address = db.Column(db.Text)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    credit_limit = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    outstanding_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    business = db.relationship("Business", back_populates="customers")
    sales = db.relationship("Sale", back_populates="customer", lazy=True)
    repayments = db.relationship("Repayment", back_populates="customer", lazy=True)

    def __repr__(self) -> str:
        return f"<Customer {self.name}>"
