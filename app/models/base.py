"""Shared model utilities and mixins."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.extensions import db


def generate_uuid() -> str:
    """Generate a string UUID suitable for primary keys."""

    return str(uuid4())


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.utcnow()


class UUIDPrimaryKeyMixin:
    """Provide a UUID primary key column named `id`."""

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)


class TimestampMixin:
    """Provide created/updated timestamp columns."""

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class TenantScopedMixin:
    """Provide a required tenant foreign key."""

    business_id = db.Column(
        db.String(36),
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
