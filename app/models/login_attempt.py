"""Login attempt model for security monitoring."""

from __future__ import annotations

from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utc_now


class LoginAttempt(UUIDPrimaryKeyMixin, db.Model):
    """Track successful and failed login attempts."""

    __tablename__ = "login_attempts"
    __table_args__ = (
        db.CheckConstraint(
            "attempt_scope IN ('admin', 'ops', 'biz', 'tenant')",
            name="ck_login_attempts_scope",
        ),
        db.CheckConstraint(
            (
                "role_attempted IN "
                "('super_admin', 'ops_admin', 'biz_admin', 'owner', 'staff') "
                "OR role_attempted IS NULL"
            ),
            name="ck_login_attempts_role_attempted",
        ),
    )

    business_id = db.Column(
        db.String(36),
        db.ForeignKey("businesses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attempt_scope = db.Column(db.String(20), nullable=False, index=True)
    attempted_identifier = db.Column(db.String(255), nullable=False)
    role_attempted = db.Column(db.String(20))
    success = db.Column(db.Boolean, nullable=False, default=False)
    failure_reason = db.Column(db.String(255))
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    attempted_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    business = db.relationship("Business")
    user = db.relationship("User", back_populates="login_attempts")

    def __repr__(self) -> str:
        return f"<LoginAttempt {self.attempted_identifier}>"
