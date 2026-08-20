"""Operational Admin routes for platform monitoring and tenant control."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import ActionForm
from app.models import Business
from app.services import (
    get_activity_logs,
    get_business_detail_data,
    get_business_list_rows,
    get_login_attempt_rows,
    get_ops_dashboard_data,
    get_platform_user_rows,
    set_business_status,
)
from app.utils import ops_admin_required


ops_bp = Blueprint("ops", __name__, url_prefix="/ops")


def _business_or_404(business_id: str) -> Business:
    business = db.session.get(Business, business_id)
    if business is None:
        abort(404)
    return business


@ops_bp.get("/dashboard")
@ops_admin_required
def dashboard():
    """Render the operational admin dashboard."""

    return render_template("ops/dashboard.html", dashboard_data=get_ops_dashboard_data())


@ops_bp.get("/businesses")
@ops_admin_required
def businesses():
    """List businesses with operational monitoring filters."""

    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    business_type = request.args.get("business_type", "all")
    rows = get_business_list_rows(search=search, status=status, business_type=business_type)
    business_types = [
        value[0]
        for value in db.session.query(Business.business_type)
        .filter(Business.business_type.isnot(None))
        .distinct()
        .order_by(Business.business_type.asc())
        .all()
    ]
    return render_template(
        "ops/businesses_list.html",
        rows=rows,
        search=search,
        status=status,
        business_type=business_type,
        business_types=business_types,
        action_form=ActionForm(),
    )


@ops_bp.get("/businesses/<business_id>")
@ops_admin_required
def business_detail(business_id: str):
    """View operational details for a single business."""

    _business_or_404(business_id)
    return render_template(
        "ops/business_detail.html",
        detail_data=get_business_detail_data(business_id),
        action_form=ActionForm(),
    )


@ops_bp.post("/businesses/<business_id>/suspend")
@ops_admin_required
def business_suspend(business_id: str):
    """Suspend a business account operationally."""

    form = ActionForm()
    business = _business_or_404(business_id)
    if form.validate_on_submit():
        set_business_status(business, status="suspended", actor=current_user)
        db.session.commit()
        flash("Business suspended successfully.", "warning")
    return redirect(url_for("ops.business_detail", business_id=business.id))


@ops_bp.post("/businesses/<business_id>/reactivate")
@ops_admin_required
def business_reactivate(business_id: str):
    """Reactivate a business account operationally."""

    form = ActionForm()
    business = _business_or_404(business_id)
    if form.validate_on_submit():
        set_business_status(business, status="active", actor=current_user)
        db.session.commit()
        flash("Business reactivated successfully.", "success")
    return redirect(url_for("ops.business_detail", business_id=business.id))


@ops_bp.get("/users")
@ops_admin_required
def users():
    """Monitor platform users from the operational admin area."""

    search = request.args.get("q", "").strip()
    role = request.args.get("role", "all")
    business_id = request.args.get("business_id", "all")
    users_list = get_platform_user_rows(search=search, role=role, business_id=business_id)
    businesses = Business.query.order_by(Business.business_name.asc()).all()
    return render_template(
        "ops/users_list.html",
        users=users_list,
        businesses=businesses,
        search=search,
        role=role,
        business_id=business_id,
    )


@ops_bp.get("/activity-logs")
@ops_admin_required
def activity_logs():
    """Review audit logs from the operational admin area."""

    business_id = request.args.get("business_id", "all")
    severity = request.args.get("severity", "all")
    logs = get_activity_logs(business_id=business_id, severity=severity)
    businesses = Business.query.order_by(Business.business_name.asc()).all()
    return render_template(
        "ops/activity_logs.html",
        logs=logs,
        businesses=businesses,
        business_id=business_id,
        severity=severity,
    )


@ops_bp.get("/login-attempts")
@ops_admin_required
def login_attempts():
    """Review login attempts from the operational admin area."""

    business_id = request.args.get("business_id", "all")
    outcome = request.args.get("outcome", "all")
    attempts = get_login_attempt_rows(business_id=business_id, outcome=outcome)
    businesses = Business.query.order_by(Business.business_name.asc()).all()
    return render_template(
        "ops/login_attempts.html",
        attempts=attempts,
        businesses=businesses,
        business_id=business_id,
        outcome=outcome,
    )
