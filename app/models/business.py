"""Business model."""

from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class Business(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Tenant business account."""

    __tablename__ = "businesses"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'suspended', 'inactive', 'pending')",
            name="ck_business_status",
        ),
        db.CheckConstraint(
            "subscription_status IN ('active', 'expired', 'pending_approval', 'suspended', 'trial')",
            name="ck_business_subscription_status",
        ),
    )

    business_name = db.Column(db.String(120), nullable=False, index=True)
    owner_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(255), unique=True, index=True)
    address = db.Column(db.Text)
    business_type = db.Column(db.String(120))
    registration_date = db.Column(db.DateTime, nullable=False, default=utc_now)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    subscription_plan = db.Column(db.String(50))
    plan_name = db.Column(db.String(120), nullable=False, default="Full Plan")
    monthly_fee = db.Column(db.Numeric(12, 2), nullable=False, default=500)
    subscription_status = db.Column(db.String(20), nullable=False, default="trial", index=True)
    subscription_start = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)
    last_payment_date = db.Column(db.DateTime)
    amount_due = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_notes = db.Column(db.Text)
    logo = db.Column(db.String(255))
    preferred_language = db.Column(db.String(10), nullable=False, default="en")
    preferred_currency = db.Column(db.String(10), nullable=False, default="NPR")
    near_expiry_threshold_days = db.Column(db.Integer, nullable=False, default=7)
    currency_symbol = db.Column(db.String(12), nullable=False, default="Rs.")
    receipt_footer_note = db.Column(db.Text)
    trial_start_date = db.Column(db.DateTime)
    trial_end_date = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)
    support_note = db.Column(db.Text)
    account_notes = db.Column(db.Text)

    users = db.relationship(
        "User",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    categories = db.relationship(
        "Category",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    products = db.relationship(
        "Product",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    stock_batches = db.relationship(
        "StockBatch",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    customers = db.relationship(
        "Customer",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    sales = db.relationship(
        "Sale",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    repayments = db.relationship(
        "Repayment",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    audit_logs = db.relationship(
        "AuditLog",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
    )
    subscription_payments = db.relationship(
        "SubscriptionPayment",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="SubscriptionPayment.created_at.desc()",
    )

    @property
    def is_active(self) -> bool:
        """Return whether the business is currently active."""

        return self.status == "active"

    @property
    def is_subscription_active(self) -> bool:
        """Return whether the tenant currently has usable subscription access."""

        return self.subscription_status in {"active", "trial", "pending_approval"}

    @property
    def subscription_days_remaining(self) -> int | None:
        """Return remaining subscription days, negative when expired."""

        if self.subscription_end is None:
            return None

        delta = self.subscription_end.date() - utc_now().date()
        return delta.days

    @property
    def subscription_is_expired(self) -> bool:
        """Return True when the subscription has passed its end date."""

        remaining = self.subscription_days_remaining
        return self.subscription_status == "expired" or (remaining is not None and remaining < 0)

    def should_auto_expire(self, reference_time: datetime | None = None) -> bool:
        """Return True when an active or trial subscription should now expire."""

        if self.subscription_status not in {"active", "trial"} or self.subscription_end is None:
            return False

        current_time = reference_time or utc_now()
        return self.subscription_end < current_time

    def __repr__(self) -> str:
        return f"<Business {self.business_name}>"
