"""Audit log model."""

from __future__ import annotations

from app.extensions import db
from app.models.base import UUIDPrimaryKeyMixin, utc_now


class AuditLog(UUIDPrimaryKeyMixin, db.Model):
    """Platform and tenant audit log entries."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        db.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_audit_logs_severity",
        ),
    )

    business_id = db.Column(
        db.String(36),
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = db.Column(db.String(120), nullable=False, index=True)
    entity_type = db.Column(db.String(120), nullable=False, index=True)
    entity_id = db.Column(db.String(36), index=True)
    description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="info")
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    business = db.relationship("Business", back_populates="audit_logs")
    user = db.relationship("User", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action}>"
