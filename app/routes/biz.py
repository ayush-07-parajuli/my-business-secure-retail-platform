"""Business Admin routes for subscriptions, renewals, and company revenue."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import ActionForm
from app.models import Business, SubscriptionPayment
from app.services import (
    BusinessRuleError,
    approve_subscription_payment,
    build_csv_response,
    get_biz_dashboard_data,
    get_biz_revenue_report_data,
    get_subscription_business_rows,
    get_subscription_payment_rows,
    get_subscription_summary,
    parse_optional_date,
    reject_subscription_payment,
)
from app.utils import biz_admin_required


biz_bp = Blueprint("biz", __name__, url_prefix="/biz")


def _payment_or_404(payment_id: str) -> SubscriptionPayment:
    payment = db.session.get(SubscriptionPayment, payment_id)
    if payment is None:
        abort(404)
    return payment


def _business_or_404(business_id: str) -> Business:
    business = db.session.get(Business, business_id)
    if business is None:
        abort(404)
    return business


@biz_bp.get("/dashboard")
@biz_admin_required
def dashboard():
    """Render the business-admin subscription dashboard."""

    period = request.args.get("period", "month")
    return render_template("biz/dashboard.html", dashboard_data=get_biz_dashboard_data(period=period))


@biz_bp.get("/subscriptions")
@biz_admin_required
def subscriptions():
    """List businesses by subscription status."""

    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    rows = get_subscription_business_rows(search=search, status=status)
    return render_template("biz/subscriptions_list.html", rows=rows, search=search, status=status)


@biz_bp.get("/subscriptions/<business_id>")
@biz_admin_required
def subscription_detail(business_id: str):
    """View subscription detail for one business."""

    business = _business_or_404(business_id)
    recent_payments = get_subscription_payment_rows(business_id=business.id)
    return render_template(
        "biz/subscription_detail.html",
        business=business,
        subscription_summary=get_subscription_summary(business),
        payments=recent_payments,
        action_form=ActionForm(),
    )


@biz_bp.get("/payments")
@biz_admin_required
def payments():
    """List submitted subscription payments."""

    status = request.args.get("status", "all")
    business_id = request.args.get("business_id", "all")
    payments_list = get_subscription_payment_rows(status=status, business_id=business_id)
    businesses = Business.query.order_by(Business.business_name.asc()).all()
    return render_template(
        "biz/payments_list.html",
        payments=payments_list,
        businesses=businesses,
        status=status,
        business_id=business_id,
    )


@biz_bp.get("/payments/<payment_id>")
@biz_admin_required
def payment_detail(payment_id: str):
    """View a submitted subscription payment."""

    return render_template(
        "biz/payment_detail.html",
        payment=_payment_or_404(payment_id),
        action_form=ActionForm(),
    )


@biz_bp.post("/payments/<payment_id>/approve")
@biz_admin_required
def payment_approve(payment_id: str):
    """Approve a submitted subscription payment."""

    form = ActionForm()
    payment = _payment_or_404(payment_id)
    if form.validate_on_submit():
        try:
            approve_subscription_payment(payment, actor=current_user)
            db.session.commit()
            flash("Subscription payment approved successfully.", "success")
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return redirect(url_for("biz.payment_detail", payment_id=payment.id))


@biz_bp.post("/payments/<payment_id>/reject")
@biz_admin_required
def payment_reject(payment_id: str):
    """Reject a submitted subscription payment."""

    form = ActionForm()
    payment = _payment_or_404(payment_id)
    if form.validate_on_submit():
        try:
            reject_subscription_payment(payment, actor=current_user, reason="Rejected by Business Admin.")
            db.session.commit()
            flash("Subscription payment rejected.", "warning")
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return redirect(url_for("biz.payment_detail", payment_id=payment.id))


@biz_bp.get("/revenue")
@biz_admin_required
def revenue():
    """Render the company revenue view or export approved payments."""

    period = request.args.get("period", "all")
    start_date = parse_optional_date(request.args.get("start_date"))
    end_date = parse_optional_date(request.args.get("end_date"))
    report_data = get_biz_revenue_report_data(period=period, start_date=start_date, end_date=end_date)

    if request.args.get("format") == "csv":
        rows = [
            [
                payment.business.business_name,
                payment.amount_paid,
                payment.payment_method,
                payment.payment_date.strftime("%Y-%m-%d"),
                payment.approved_at.strftime("%Y-%m-%d %H:%M") if payment.approved_at else "",
                payment.months_covered,
                payment.transaction_id or "",
            ]
            for payment in report_data["payments"]
        ]
        return build_csv_response(
            filename="subscription-revenue-report.csv",
            headers=[
                "Business",
                "Amount Paid",
                "Payment Method",
                "Payment Date",
                "Approved At",
                "Months Covered",
                "Transaction ID",
            ],
            rows=rows,
        )

    return render_template("biz/revenue.html", report_data=report_data)


@biz_bp.get("/reports")
@biz_admin_required
def reports():
    """Show the business-admin reporting hub."""

    return render_template("biz/reports.html", report_data=get_biz_revenue_report_data(period="year"))
