"""Authentication and authorization helpers."""

from __future__ import annotations

from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, logout_user

from app.services.subscription_service import subscription_allows_feature
from app.utils.tenant import current_user_can_access_business


def is_safe_url(target: str | None) -> bool:
    """Check whether a redirect target stays on this host."""

    if not target:
        return False

    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in {"http", "https"} and ref_url.netloc == test_url.netloc


def resolve_dashboard_endpoint(user=None) -> str:
    """Resolve the correct dashboard endpoint for a user."""

    selected_user = user or current_user

    if selected_user.is_super_admin():
        return "admin.dashboard"
    if selected_user.is_ops_admin():
        return "ops.dashboard"
    if selected_user.is_biz_admin():
        return "biz.dashboard"
    if selected_user.is_owner():
        return "owner.dashboard"
    return "staff.dashboard"


def redirect_to_dashboard(user=None):
    """Redirect the current or supplied user to the correct dashboard."""

    return redirect(url_for(resolve_dashboard_endpoint(user)))


def _role_required(*roles: str, login_endpoint: str):
    """Restrict a view to specific roles with a scoped login redirect."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in to continue.", "warning")
                return redirect(url_for(login_endpoint, next=request.url))

            if not current_user.is_active:
                logout_user()
                flash("Your account is inactive. Please contact support.", "danger")
                return redirect(url_for("auth.login"))

            if not current_user.has_role(*roles):
                flash("You are not authorized to access that page.", "warning")
                return redirect_to_dashboard()

            return view(*args, **kwargs)

        return wrapped

    return decorator


def role_required(*roles: str):
    """Restrict a view to specific roles using the shared tenant login by default."""

    return _role_required(*roles, login_endpoint="auth.login")


def super_admin_required(view):
    """Restrict a view to Super Admin users."""

    return _role_required("super_admin", login_endpoint="auth.login")(view)


def ops_admin_required(view):
    """Restrict a view to Operational Admins and Super Admins."""

    return _role_required("super_admin", "ops_admin", login_endpoint="auth.login")(view)


def biz_admin_required(view):
    """Restrict a view to Business Admins and Super Admins."""

    return _role_required("super_admin", "biz_admin", login_endpoint="auth.login")(view)


def owner_required(view):
    """Restrict a view to business owners."""

    return _role_required("owner", login_endpoint="auth.login")(view)


def staff_required(view):
    """Restrict a view to staff users."""

    return _role_required("staff", login_endpoint="auth.login")(view)


def owner_or_staff_required(view):
    """Restrict a view to owner or staff users."""

    return _role_required("owner", "staff", login_endpoint="auth.login")(view)


def subscription_operation_required(feature_name: str):
    """Restrict tenant actions when a subscription is expired or suspended."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user.is_authenticated and getattr(current_user, "business", None):
                allowed, message = subscription_allows_feature(current_user.business, feature=feature_name)
                if not allowed:
                    flash(message, "warning")
                    if current_user.is_owner():
                        return redirect(url_for("owner.subscription"))
                    return redirect_to_dashboard()
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_business_access(business_id: str | None) -> None:
    """Abort when the current user cannot access the requested business."""

    if not current_user_can_access_business(business_id):
        abort(403)
