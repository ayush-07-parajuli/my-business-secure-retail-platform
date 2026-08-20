"""Expanded Super Admin routes."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import ActionForm, AdminBusinessCreateForm, PlatformAdminUserForm
from app.models import Business
from app.services import (
    BusinessRuleError,
    build_csv_response,
    create_business_with_owner,
    create_platform_admin_user,
    get_activity_logs,
    get_business_detail_data,
    get_business_list_rows,
    get_login_attempt_rows,
    get_platform_dashboard_data,
    get_platform_report_data,
    get_platform_user_rows,
    parse_optional_date,
    set_business_status,
)
from app.utils import super_admin_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _business_or_404(business_id: str) -> Business:
    business = db.session.get(Business, business_id)
    if business is None:
        abort(404)
    return business


@admin_bp.get("/dashboard")
@super_admin_required
def dashboard():
    """Render the full Super Admin dashboard."""

    period = request.args.get("period", "month")
    dashboard_data = get_platform_dashboard_data(period=period)
    return render_template(
        "admin/dashboard.html",
        dashboard_data=dashboard_data,
    )


@admin_bp.route("/businesses")
@super_admin_required
def businesses():
    """List and filter platform businesses."""

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
        "admin/businesses_list.html",
        rows=rows,
        search=search,
        status=status,
        business_type=business_type,
        business_types=business_types,
        action_form=ActionForm(),
    )


@admin_bp.route("/businesses/new", methods=["GET", "POST"])
@super_admin_required
def business_new():
    """Create a business manually from the Super Admin panel."""

    form = AdminBusinessCreateForm()
    if form.validate_on_submit():
        try:
            business = create_business_with_owner(
                business_name=form.business_name.data,
                owner_name=form.owner_name.data,
                owner_email=form.owner_email.data,
                owner_username=form.owner_username.data,
                owner_password=form.owner_password.data,
                phone=form.phone.data,
                business_email=form.business_email.data,
                address=form.address.data,
                business_type=form.business_type.data,
                preferred_language=form.preferred_language.data,
                status=form.status.data,
                plan_name=form.plan_name.data,
                monthly_fee=form.monthly_fee.data,
                subscription_status=form.subscription_status.data,
                currency_symbol=form.currency_symbol.data,
                preferred_currency=form.preferred_currency.data,
                near_expiry_threshold_days=form.near_expiry_threshold_days.data,
                receipt_footer_note=form.receipt_footer_note.data,
                actor=current_user,
            )
            db.session.commit()
            flash("Business account created successfully.", "success")
            return redirect(url_for("admin.business_detail", business_id=business.id))
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception:
            db.session.rollback()
            raise
    return render_template("admin/business_form.html", form=form)


@admin_bp.get("/businesses/<business_id>")
@super_admin_required
def business_detail(business_id: str):
    """View business-level analytics and recent activity."""

    _business_or_404(business_id)
    detail_data = get_business_detail_data(business_id)
    return render_template(
        "admin/business_detail.html",
        detail_data=detail_data,
        action_form=ActionForm(),
    )


@admin_bp.post("/businesses/<business_id>/suspend")
@super_admin_required
def business_suspend(business_id: str):
    """Suspend a business account."""

    form = ActionForm()
    business = _business_or_404(business_id)
    if form.validate_on_submit():
        try:
            set_business_status(business, status="suspended", actor=current_user)
            db.session.commit()
            flash("Business suspended successfully.", "warning")
        except Exception:
            db.session.rollback()
            raise
    return redirect(url_for("admin.business_detail", business_id=business.id))


@admin_bp.post("/businesses/<business_id>/reactivate")
@super_admin_required
def business_reactivate(business_id: str):
    """Reactivate a business account."""

    form = ActionForm()
    business = _business_or_404(business_id)
    if form.validate_on_submit():
        try:
            set_business_status(business, status="active", actor=current_user)
            db.session.commit()
            flash("Business reactivated successfully.", "success")
        except Exception:
            db.session.rollback()
            raise
    return redirect(url_for("admin.business_detail", business_id=business.id))


@admin_bp.route("/users")
@super_admin_required
def users():
    """Monitor platform users across all businesses."""

    search = request.args.get("q", "").strip()
    role = request.args.get("role", "all")
    business_id = request.args.get("business_id", "all")
    users_list = get_platform_user_rows(search=search, role=role, business_id=business_id)
    businesses = Business.query.order_by(Business.business_name.asc()).all()
    return render_template(
        "admin/users_list.html",
        users=users_list,
        businesses=businesses,
        search=search,
        role=role,
        business_id=business_id,
    )


@admin_bp.route("/users/new", methods=["GET", "POST"])
@super_admin_required
def user_new():
    """Create company-side ops_admin or biz_admin users."""

    form = PlatformAdminUserForm()
    if form.validate_on_submit():
        try:
            user = create_platform_admin_user(
                full_name=form.full_name.data,
                username=form.username.data,
                email=form.email.data,
                password=form.password.data,
                role=form.role.data,
                preferred_language=form.preferred_language.data,
                actor=current_user,
            )
            db.session.commit()
            flash("Company admin account created successfully.", "success")
            return redirect(url_for("admin.users", q=user.email))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("admin/admin_user_form.html", form=form)


@admin_bp.route("/activity-logs")
@super_admin_required
def activity_logs():
    """Review audit log activity across the platform."""

    business_id = request.args.get("business_id", "all")
    severity = request.args.get("severity", "all")
    logs = get_activity_logs(business_id=business_id, severity=severity)
    businesses = Business.query.order_by(Business.business_name.asc()).all()
    return render_template(
        "admin/activity_logs.html",
        logs=logs,
        businesses=businesses,
        business_id=business_id,
        severity=severity,
    )


@admin_bp.route("/login-attempts")
@super_admin_required
def login_attempts():
    """Review recent login attempts and failures."""

    business_id = request.args.get("business_id", "all")
    outcome = request.args.get("outcome", "all")
    attempts = get_login_attempt_rows(business_id=business_id, outcome=outcome)
    businesses = Business.query.order_by(Business.business_name.asc()).all()
    return render_template(
        "admin/login_attempts.html",
        attempts=attempts,
        businesses=businesses,
        business_id=business_id,
        outcome=outcome,
    )


@admin_bp.route("/reports/platform")
@super_admin_required
def platform_report():
    """Render platform summary reports or export them as CSV."""

    period = request.args.get("period", "all")
    start_date = parse_optional_date(request.args.get("start_date"))
    end_date = parse_optional_date(request.args.get("end_date"))
    report_data = get_platform_report_data(period=period, start_date=start_date, end_date=end_date)

    if request.args.get("format") == "csv":
        rows = [
            [
                row["business"].business_name,
                row["business"].status,
                row["business"].business_type or "",
                row["user_count"],
                row["sales_count"],
                row["revenue"],
                row["gross_profit"],
                row["credit_outstanding"],
            ]
            for row in report_data["rows"]
        ]
        return build_csv_response(
            filename="platform-report.csv",
            headers=[
                "Business",
                "Status",
                "Business Type",
                "Users",
                "Sales",
                "Tenant Revenue",
                "Tenant Gross Profit",
                "Outstanding Credit",
            ],
            rows=rows,
        )

    return render_template(
        "admin/platform_report.html",
        report_data=report_data,
    )
