"""User model with Flask-Login support."""

from __future__ import annotations

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class User(UserMixin, UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Platform user for company-side or tenant-side access."""

    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('super_admin', 'ops_admin', 'biz_admin', 'owner', 'staff')",
            name="ck_user_role",
        ),
        db.CheckConstraint(
            "status IN ('active', 'suspended', 'inactive')",
            name="ck_user_status",
        ),
        db.CheckConstraint(
            "(role IN ('super_admin', 'ops_admin', 'biz_admin') AND business_id IS NULL) "
            "OR (role IN ('owner', 'staff') AND business_id IS NOT NULL)",
            name="ck_user_scope",
        ),
    )

    business_id = db.Column(
        db.String(36),
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff", index=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    preferred_language = db.Column(db.String(10), nullable=False, default="en")
    is_primary_owner = db.Column(db.Boolean, nullable=False, default=False)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    last_login_at = db.Column(db.DateTime)
    last_password_reset_at = db.Column(db.DateTime)

    business = db.relationship("Business", back_populates="users")
    created_sales = db.relationship(
        "Sale",
        foreign_keys="Sale.created_by_user_id",
        back_populates="created_by",
        lazy=True,
    )
    received_repayments = db.relationship(
        "Repayment",
        foreign_keys="Repayment.received_by_user_id",
        back_populates="received_by",
        lazy=True,
    )
    audit_logs = db.relationship("AuditLog", back_populates="user", lazy=True)
    login_attempts = db.relationship("LoginAttempt", back_populates="user", lazy=True)
    submitted_subscription_payments = db.relationship(
        "SubscriptionPayment",
        foreign_keys="SubscriptionPayment.submitted_by_user_id",
        back_populates="submitted_by",
        lazy=True,
    )
    approved_subscription_payments = db.relationship(
        "SubscriptionPayment",
        foreign_keys="SubscriptionPayment.approved_by_user_id",
        back_populates="approved_by",
        lazy=True,
    )

    def set_password(self, raw_password: str) -> None:
        """Hash and store a password securely."""

        self.password_hash = generate_password_hash(raw_password)
        self.last_password_reset_at = utc_now()

    def check_password(self, raw_password: str) -> bool:
        """Validate a password against the stored hash."""

        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_active(self) -> bool:
        """Flask-Login active check."""

        business_is_usable = self.business is None or self.business.status == "active"
        return self.status == "active" and business_is_usable

    def is_super_admin(self) -> bool:
        """Return True when the user is a Super Admin."""

        return self.role == "super_admin"

    def is_ops_admin(self) -> bool:
        """Return True when the user is an Operational Admin."""

        return self.role == "ops_admin"

    def is_biz_admin(self) -> bool:
        """Return True when the user is a Business Admin."""

        return self.role == "biz_admin"

    def is_owner(self) -> bool:
        """Return True when the user is a business owner."""

        return self.role == "owner"

    def is_staff(self) -> bool:
        """Return True when the user is a staff user."""

        return self.role == "staff"

    def has_role(self, *roles: str) -> bool:
        """Check if the user has one of the provided roles."""

        return self.role in roles

    def is_company_admin(self) -> bool:
        """Return True for company-side admin accounts."""

        return self.role in {"super_admin", "ops_admin", "biz_admin"}

    def belongs_to_business(self, business_id: str | None) -> bool:
        """Return True when the user belongs to the given business."""

        return business_id is not None and self.business_id == business_id

    def __repr__(self) -> str:
        return f"<User {self.email}>"
