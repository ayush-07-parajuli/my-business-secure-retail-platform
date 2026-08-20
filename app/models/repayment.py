"""Credit repayment model."""

from __future__ import annotations

from app.extensions import db
from app.models.base import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class Repayment(TenantScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Repayment recorded against a credit sale."""

    __tablename__ = "repayments"

    sale_id = db.Column(
        db.String(36),
        db.ForeignKey("sales.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_id = db.Column(
        db.String(36),
        db.ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    received_by_user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_date = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    note = db.Column(db.Text)

    business = db.relationship("Business", back_populates="repayments")
    sale = db.relationship("Sale", back_populates="repayments")
    customer = db.relationship("Customer", back_populates="repayments")
    received_by = db.relationship(
        "User",
        foreign_keys=[received_by_user_id],
        back_populates="received_repayments",
    )

    def __repr__(self) -> str:
        return f"<Repayment {self.id}>"
