"""Subscription payment model for manual SaaS renewals."""

from __future__ import annotations

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class SubscriptionPayment(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Track owner-submitted and company-approved subscription payments."""

    __tablename__ = "subscription_payments"
    __table_args__ = (
        db.CheckConstraint(
            "payment_method IN ('esewa', 'khalti', 'bank_transfer', 'cash')",
            name="ck_subscription_payment_method",
        ),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_subscription_payment_status",
        ),
    )

    business_id = db.Column(
        db.String(36),
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submitted_by_user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_by_user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False, index=True)
    transaction_id = db.Column(db.String(120))
    payment_date = db.Column(db.DateTime, nullable=False, default=utc_now)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    approved_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    months_covered = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.Text)
    proof_path = db.Column(db.String(255))

    business = db.relationship("Business", back_populates="subscription_payments")
    submitted_by = db.relationship(
        "User",
        foreign_keys=[submitted_by_user_id],
        back_populates="submitted_subscription_payments",
    )
    approved_by = db.relationship(
        "User",
        foreign_keys=[approved_by_user_id],
        back_populates="approved_subscription_payments",
    )

    def __repr__(self) -> str:
        return f"<SubscriptionPayment {self.business_id} {self.status}>"
