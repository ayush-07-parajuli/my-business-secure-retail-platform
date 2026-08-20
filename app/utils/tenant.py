"""Helpers for tenant-aware data access."""

from __future__ import annotations

from flask import abort
from flask_login import current_user
from sqlalchemy import false


def get_current_business_id() -> str | None:
    """Return the logged-in user's business identifier if present."""

    if not current_user.is_authenticated:
        return None

    return getattr(current_user, "business_id", None)


def current_user_can_access_business(business_id: str | None) -> bool:
    """Check if the current user may access the given business."""

    if not current_user.is_authenticated:
        return False

    if current_user.is_super_admin():
        return True

    return business_id is not None and current_user.business_id == business_id


def instance_belongs_to_current_tenant(instance) -> bool:
    """Check whether an instance belongs to the current tenant."""

    if not current_user.is_authenticated:
        return False

    if current_user.is_super_admin():
        return True

    return getattr(instance, "business_id", None) == current_user.business_id


def scope_query_to_tenant(query, model, business_id: str | None = None, *, allow_super_admin: bool = False):
    """Apply a safe tenant filter to a SQLAlchemy query."""

    active_business_id = business_id or get_current_business_id()

    if active_business_id is not None:
        return query.filter(model.business_id == active_business_id)

    if current_user.is_authenticated and current_user.is_super_admin() and allow_super_admin:
        return query

    return query.filter(false())


def get_tenant_record_or_none(model, object_id: str, business_id: str | None = None):
    """Safely fetch a single tenant-scoped record by id."""

    scoped_query = scope_query_to_tenant(
        model.query,
        model,
        business_id=business_id,
    )
    return scoped_query.filter(model.id == object_id).first()


def require_instance_tenant_access(instance) -> None:
    """Abort with 403 when an instance does not belong to the active tenant."""

    if not instance_belongs_to_current_tenant(instance):
        abort(403)


def get_tenant_record_or_404(model, object_id: str, business_id: str | None = None):
    """Fetch a tenant-scoped record or abort if it is not accessible."""

    record = get_tenant_record_or_none(model, object_id, business_id=business_id)
    if record is None:
        abort(404)
    require_instance_tenant_access(record)
    return record
