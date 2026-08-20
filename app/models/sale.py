"""Sales transaction model."""

from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models.base import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class Sale(TenantScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Tenant-scoped sale transaction."""

    __tablename__ = "sales"
    __table_args__ = (
        db.CheckConstraint(
            "payment_mode IN ('cash', 'credit', 'partial')",
            name="ck_sales_payment_mode",
        ),
        db.CheckConstraint(
            "payment_status IN ('paid', 'partial', 'unpaid', 'overdue')",
            name="ck_sales_payment_status",
        ),
    )

    customer_id = db.Column(
        db.String(36),
        db.ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sale_datetime = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    payment_mode = db.Column(db.String(20), nullable=False, default="cash")
    payment_status = db.Column(db.String(20), nullable=False, default="paid")
    total_revenue = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_gross_profit = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_realized_profit = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_unrealized_profit = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_due = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text)

    business = db.relationship("Business", back_populates="sales")
    customer = db.relationship("Customer", back_populates="sales")
    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_user_id],
        back_populates="created_sales",
    )
    items = db.relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy=True,
    )
    repayments = db.relationship(
        "Repayment",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def cash_collected(self) -> Decimal:
        """Return the amount of money collected so far."""

        return self.amount_paid or Decimal("0")

    def refresh_payment_status(self) -> None:
        """Keep payment state aligned with amounts paid and due."""

        revenue = self.total_revenue or Decimal("0")
        amount_paid = self.amount_paid or Decimal("0")
        amount_due = revenue - amount_paid

        self.amount_due = amount_due if amount_due > 0 else Decimal("0")

        if self.amount_due == 0:
            self.payment_status = "paid"
        elif amount_paid == 0:
            self.payment_status = "unpaid"
        else:
            self.payment_status = "partial"

    def __repr__(self) -> str:
        return f"<Sale {self.id}>"
