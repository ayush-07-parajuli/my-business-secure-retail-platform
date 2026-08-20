"""Subscription lifecycle, payment approval, and company revenue services."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy import desc, func, or_

from app.extensions import db
from app.models import Business, SubscriptionPayment, User
from app.models.base import utc_now
from app.services.analytics_service import resolve_period_range
from app.services.auth_service import record_audit_event
from app.services.exceptions import BusinessRuleError
from app.services.sales_service import money


FULL_PLAN_NAME = "Full Plan"
DEFAULT_MONTHLY_FEE = Decimal("500.00")
SUBSCRIPTION_FEATURES = [
    "Sales and POS",
    "Inventory and batch tracking",
    "Customer ledger and credit management",
    "Reports and dashboards",
    "Multi-user access",
]
PAYMENT_METHOD_LABELS = {
    "esewa": "eSewa",
    "khalti": "Khalti",
    "bank_transfer": "Bank Transfer",
    "cash": "Cash",
}


def _payment_datetime(value) -> datetime:
    """Normalize form dates into datetimes for storage."""

    if value is None:
        return utc_now()
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min)


def initialize_business_subscription(
    business: Business,
    *,
    status: str = "trial",
    start_at: datetime | None = None,
    months_covered: int = 1,
) -> Business:
    """Populate default SaaS subscription values for a business."""

    anchor = start_at or utc_now()
    business.plan_name = business.plan_name or FULL_PLAN_NAME
    business.subscription_plan = business.plan_name
    business.monthly_fee = money(business.monthly_fee or DEFAULT_MONTHLY_FEE)
    business.preferred_currency = business.preferred_currency or "NPR"
    business.subscription_status = status

    if status in {"trial", "active"}:
        business.subscription_start = business.subscription_start or anchor
        business.subscription_end = business.subscription_end or (
            anchor + timedelta(days=30 * max(months_covered, 1))
        )
        business.amount_due = money(Decimal("0.00"))
    else:
        business.subscription_start = business.subscription_start or anchor
        business.subscription_end = business.subscription_end or anchor
        business.amount_due = money(business.monthly_fee * max(months_covered, 1))

    return business


def get_effective_subscription_status(
    business: Business | None,
    *,
    reference_time: datetime | None = None,
) -> str:
    """Return the current subscription state, auto-expiring stale active plans."""

    if business is None:
        return "active"

    current_time = reference_time or utc_now()
    stored_status = business.subscription_status or "trial"

    if stored_status in {"active", "trial"} and business.subscription_end and business.subscription_end < current_time:
        return "expired"
    return stored_status


def sync_business_subscription_state(business: Business) -> Business:
    """Persist automatic expiry when the subscription date has elapsed."""

    effective_status = get_effective_subscription_status(business)
    if effective_status == "expired" and business.subscription_status != "expired":
        business.subscription_status = "expired"
        business.amount_due = money(business.monthly_fee or DEFAULT_MONTHLY_FEE)
    return business


def get_subscription_summary(business: Business | None) -> dict | None:
    """Return owner-facing subscription metadata and renewal guidance."""

    if business is None:
        return None

    effective_status = get_effective_subscription_status(business)
    days_remaining = None
    if business.subscription_end:
        days_remaining = (business.subscription_end.date() - utc_now().date()).days

    amount_due = money(business.amount_due or Decimal("0.00"))
    if effective_status == "expired" and amount_due <= 0:
        amount_due = money(business.monthly_fee or DEFAULT_MONTHLY_FEE)

    if effective_status == "active":
        status_message = "Your subscription is active and all features are available."
        severity = "success"
    elif effective_status == "trial":
        status_message = "Your trial is active. Renew before the end date to avoid restrictions."
        severity = "info"
    elif effective_status == "pending_approval":
        status_message = "Your payment submission is pending company approval."
        severity = "warning"
    elif effective_status == "expired":
        status_message = "Your subscription has expired. Renew to continue sales, restocking, and reports."
        severity = "danger"
    else:
        status_message = "Your subscription is suspended. Renew and contact support for reactivation."
        severity = "danger"

    return {
        "plan_name": business.plan_name or FULL_PLAN_NAME,
        "monthly_fee": money(business.monthly_fee or DEFAULT_MONTHLY_FEE),
        "status": effective_status,
        "status_message": status_message,
        "severity": severity,
        "start_date": business.subscription_start,
        "end_date": business.subscription_end,
        "days_remaining": days_remaining,
        "amount_due": amount_due,
        "payment_notes": business.payment_notes,
        "preferred_currency": business.preferred_currency or "NPR",
        "features": SUBSCRIPTION_FEATURES,
        "payment_methods": list(PAYMENT_METHOD_LABELS.values()),
    }


def get_subscription_notice_for_user(user) -> dict | None:
    """Return a lightweight subscription banner context for tenant users."""

    if not getattr(user, "is_authenticated", False) or not getattr(user, "business", None):
        return None

    summary = get_subscription_summary(user.business)
    if summary is None or summary["status"] == "active":
        return None
    return summary


def subscription_allows_feature(business: Business | None, *, feature: str = "operations") -> tuple[bool, str]:
    """Return whether a tenant subscription should allow a protected feature."""

    if business is None:
        return True, ""

    status = get_effective_subscription_status(business)
    if status in {"active", "trial"}:
        return True, ""
    if status == "pending_approval":
        return True, ""
    if status == "expired":
        return False, (
            f"Your subscription has expired. Renew it before using {feature}. "
            "You can still review the subscription page and submit payment."
        )
    return False, (
        f"Your subscription is suspended. {feature.title()} are disabled until the company reactivates the account."
    )


def submit_subscription_payment(
    *,
    business: Business,
    submitted_by: User,
    amount_paid,
    payment_method: str,
    transaction_id: str | None,
    payment_date,
    months_covered: int,
    note: str | None,
    proof_path: str | None,
) -> SubscriptionPayment:
    """Create a manual renewal submission for Business Admin review."""

    if money(amount_paid) <= 0:
        raise BusinessRuleError("Payment amount must be greater than zero.")
    if months_covered < 1:
        raise BusinessRuleError("Months covered must be at least 1.")
    existing_pending = SubscriptionPayment.query.filter_by(business_id=business.id, status="pending").first()
    if existing_pending is not None:
        raise BusinessRuleError("A payment is already pending approval for this business.")

    payment = SubscriptionPayment(
        business=business,
        submitted_by=submitted_by,
        amount_paid=money(amount_paid),
        payment_method=payment_method,
        transaction_id=(transaction_id or "").strip() or None,
        payment_date=_payment_datetime(payment_date),
        submitted_at=utc_now(),
        status="pending",
        months_covered=max(months_covered or 1, 1),
        note=(note or "").strip() or None,
        proof_path=(proof_path or "").strip() or None,
    )
    business.subscription_status = "pending_approval"
    business.plan_name = business.plan_name or FULL_PLAN_NAME
    business.subscription_plan = business.plan_name
    business.monthly_fee = money(business.monthly_fee or DEFAULT_MONTHLY_FEE)
    business.amount_due = money(business.monthly_fee * payment.months_covered)
    business.payment_notes = "Renewal submitted and waiting for company approval."

    db.session.add(payment)
    db.session.flush()

    record_audit_event(
        action="subscription_payment_submitted",
        description=f"Subscription payment submitted for business '{business.business_name}'.",
        entity_type="subscription_payment",
        entity_id=payment.id,
        user=submitted_by,
        business=business,
    )
    return payment


def approve_subscription_payment(payment: SubscriptionPayment, *, actor: User) -> SubscriptionPayment:
    """Approve a pending subscription payment and activate the tenant."""

    if payment.status != "pending":
        raise BusinessRuleError("Only pending subscription payments can be approved.")

    business = payment.business
    sync_business_subscription_state(business)
    current_time = utc_now()
    anchor = current_time
    if business.subscription_end and business.subscription_end > current_time:
        anchor = business.subscription_end

    business.plan_name = FULL_PLAN_NAME
    business.subscription_plan = FULL_PLAN_NAME
    business.monthly_fee = money(business.monthly_fee or DEFAULT_MONTHLY_FEE)
    business.subscription_status = "active"
    if business.subscription_start is None or get_effective_subscription_status(business) == "expired":
        business.subscription_start = current_time
    business.subscription_end = anchor + timedelta(days=30 * max(payment.months_covered, 1))
    business.last_payment_date = payment.payment_date
    business.amount_due = money(Decimal("0.00"))
    business.payment_notes = (
        f"Approved {PAYMENT_METHOD_LABELS.get(payment.payment_method, payment.payment_method)} payment "
        f"for {payment.months_covered} month(s)."
    )

    payment.status = "approved"
    payment.approved_at = current_time
    payment.approved_by = actor

    record_audit_event(
        action="subscription_payment_approved",
        description=f"Subscription payment approved for business '{business.business_name}'.",
        entity_type="subscription_payment",
        entity_id=payment.id,
        user=actor,
        business=business,
    )
    return payment


def reject_subscription_payment(
    payment: SubscriptionPayment,
    *,
    actor: User,
    reason: str | None = None,
) -> SubscriptionPayment:
    """Reject a pending payment and restore the business subscription state."""

    if payment.status != "pending":
        raise BusinessRuleError("Only pending subscription payments can be rejected.")

    business = payment.business
    payment.status = "rejected"
    payment.approved_at = utc_now()
    payment.approved_by = actor
    if reason:
        payment.note = f"{payment.note or ''}\nRejected: {reason}".strip()

    if business.subscription_end and business.subscription_end >= utc_now():
        business.subscription_status = "active"
    else:
        business.subscription_status = "expired"
    if business.subscription_status == "expired":
        business.amount_due = money(business.monthly_fee or DEFAULT_MONTHLY_FEE)
    business.payment_notes = reason or "Payment rejected. Please submit a valid renewal proof."

    record_audit_event(
        action="subscription_payment_rejected",
        description=f"Subscription payment rejected for business '{business.business_name}'.",
        entity_type="subscription_payment",
        entity_id=payment.id,
        user=actor,
        business=business,
        severity="warning",
    )
    return payment


def get_business_subscription_payments(business_id: str, *, limit: int | None = None) -> list[SubscriptionPayment]:
    """Return recent subscription payments for a tenant."""

    query = (
        SubscriptionPayment.query.filter_by(business_id=business_id)
        .order_by(SubscriptionPayment.submitted_at.desc())
    )
    if limit:
        query = query.limit(limit)
    return query.all()


def _subscription_rows_for_businesses(query) -> list[dict]:
    rows = []
    for business in query.all():
        sync_business_subscription_state(business)
        recent_payment = (
            SubscriptionPayment.query.filter_by(business_id=business.id)
            .order_by(SubscriptionPayment.submitted_at.desc())
            .first()
        )
        rows.append(
            {
                "business": business,
                "effective_status": get_effective_subscription_status(business),
                "owner_count": User.query.filter_by(business_id=business.id, role="owner").count(),
                "staff_count": User.query.filter_by(business_id=business.id, role="staff").count(),
                "recent_payment": recent_payment,
            }
        )
    return rows


def get_subscription_business_rows(*, search: str = "", status: str = "all") -> list[dict]:
    """Return business rows for the company subscription monitor."""

    query = Business.query.order_by(Business.created_at.desc())
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Business.business_name.ilike(pattern),
                Business.owner_name.ilike(pattern),
                Business.email.ilike(pattern),
            )
        )
    rows = _subscription_rows_for_businesses(query)
    if status != "all":
        rows = [row for row in rows if row["effective_status"] == status]
    return rows


def get_subscription_payment_rows(
    *,
    status: str = "all",
    business_id: str = "all",
) -> list[SubscriptionPayment]:
    """Return company-side subscription payment rows."""

    query = SubscriptionPayment.query.order_by(SubscriptionPayment.submitted_at.desc())
    if status != "all":
        query = query.filter_by(status=status)
    if business_id != "all":
        query = query.filter_by(business_id=business_id)
    return query.all()


def _approved_payments_query(date_range: dict | None = None):
    query = SubscriptionPayment.query.filter_by(status="approved")
    if date_range is not None:
        if date_range["start_datetime"] is not None:
            query = query.filter(SubscriptionPayment.approved_at >= date_range["start_datetime"])
        if date_range["end_datetime"] is not None:
            query = query.filter(SubscriptionPayment.approved_at <= date_range["end_datetime"])
    return query


def get_platform_subscription_overview() -> dict:
    """Return company subscription metrics for the top-level dashboard."""

    businesses = Business.query.order_by(Business.created_at.desc()).all()
    active_count = 0
    pending_count = 0
    expired_count = 0
    suspended_count = 0
    outstanding = Decimal("0.00")
    for business in businesses:
        status = get_effective_subscription_status(business)
        if status == "active" or status == "trial":
            active_count += 1
        elif status == "pending_approval":
            pending_count += 1
        elif status == "expired":
            expired_count += 1
        else:
            suspended_count += 1
        outstanding += money(business.amount_due or Decimal("0.00"))

    current_month = resolve_period_range("month")
    current_year = resolve_period_range("year")
    monthly_revenue = money(
        _approved_payments_query(current_month)
        .with_entities(func.coalesce(func.sum(SubscriptionPayment.amount_paid), 0))
        .scalar()
    )
    yearly_revenue = money(
        _approved_payments_query(current_year)
        .with_entities(func.coalesce(func.sum(SubscriptionPayment.amount_paid), 0))
        .scalar()
    )
    total_revenue = money(
        _approved_payments_query()
        .with_entities(func.coalesce(func.sum(SubscriptionPayment.amount_paid), 0))
        .scalar()
    )
    operating_cost = money(Decimal(str(current_app.config.get("PLATFORM_MONTHLY_OPERATING_COST", "0"))))
    # The cost placeholder is monthly, so the platform profit estimate should
    # compare against monthly subscription collections instead of all-time revenue.
    estimated_platform_profit = money(monthly_revenue - operating_cost)

    return {
        "total_businesses": len(businesses),
        "active_subscriptions": active_count,
        "pending_approvals": pending_count,
        "expired_subscriptions": expired_count,
        "suspended_subscriptions": suspended_count,
        "monthly_subscription_revenue": monthly_revenue,
        "yearly_subscription_revenue": yearly_revenue,
        "total_subscription_revenue": total_revenue,
        "total_collected_subscription_payments": total_revenue,
        "total_outstanding_dues": money(outstanding),
        "total_outstanding_subscription_dues": money(outstanding),
        "estimated_platform_profit": estimated_platform_profit,
        "operating_cost": operating_cost,
    }


def get_biz_dashboard_data(*, period: str = "month") -> dict:
    """Return business-admin dashboard metrics and charts."""

    date_range = resolve_period_range(period)
    overview = get_platform_subscription_overview()
    businesses = Business.query.order_by(Business.created_at.desc()).all()

    revenue_rows = (
        _approved_payments_query(date_range)
        .with_entities(
            func.date(SubscriptionPayment.approved_at).label("day"),
            func.coalesce(func.sum(SubscriptionPayment.amount_paid), 0).label("amount_paid"),
        )
        .group_by(func.date(SubscriptionPayment.approved_at))
        .order_by(func.date(SubscriptionPayment.approved_at))
        .all()
    )
    renewal_rows = (
        SubscriptionPayment.query.filter(SubscriptionPayment.submitted_at.isnot(None))
        .with_entities(
            func.date(SubscriptionPayment.submitted_at).label("day"),
            func.count(SubscriptionPayment.id).label("submission_count"),
        )
    )
    if date_range["start_datetime"] is not None:
        renewal_rows = renewal_rows.filter(SubscriptionPayment.submitted_at >= date_range["start_datetime"])
    if date_range["end_datetime"] is not None:
        renewal_rows = renewal_rows.filter(SubscriptionPayment.submitted_at <= date_range["end_datetime"])
    renewal_rows = (
        renewal_rows.group_by(func.date(SubscriptionPayment.submitted_at))
        .order_by(func.date(SubscriptionPayment.submitted_at))
        .all()
    )

    active_chart = {"active": 0, "expired": 0, "pending_approval": 0, "suspended": 0, "trial": 0}
    for business in businesses:
        active_chart[get_effective_subscription_status(business)] += 1

    monthly_collection_rows = (
        _approved_payments_query()
        .with_entities(
            func.strftime("%Y-%m", SubscriptionPayment.approved_at).label("month"),
            func.coalesce(func.sum(SubscriptionPayment.amount_paid), 0).label("amount_paid"),
        )
        .group_by(func.strftime("%Y-%m", SubscriptionPayment.approved_at))
        .order_by(func.strftime("%Y-%m", SubscriptionPayment.approved_at))
        .all()
    )

    return {
        "period": date_range,
        "metrics": overview,
        "recent_payments": get_subscription_payment_rows(status="approved")[:8],
        "pending_payments": get_subscription_payment_rows(status="pending")[:8],
        "expiring_businesses": [row for row in get_subscription_business_rows(status="expired")[:8]],
        "charts": {
            "subscription_revenue_trend": {
                "labels": [row.day for row in revenue_rows],
                "datasets": [
                    {
                        "label": "Subscription Revenue",
                        "data": [float(money(row.amount_paid)) for row in revenue_rows],
                        "borderColor": "#0f766e",
                        "backgroundColor": "rgba(15, 118, 110, 0.12)",
                        "fill": True,
                    }
                ],
            },
            "renewal_trend": {
                "labels": [row.day for row in renewal_rows],
                "datasets": [
                    {
                        "label": "Renewals Submitted",
                        "data": [row.submission_count for row in renewal_rows],
                        "borderColor": "#1d4ed8",
                        "backgroundColor": "rgba(29, 78, 216, 0.12)",
                        "fill": True,
                    }
                ],
            },
            "status_breakdown": {
                "labels": ["Active", "Expired", "Pending Approval", "Suspended", "Trial"],
                "datasets": [
                    {
                        "label": "Businesses",
                        "data": [
                            active_chart["active"],
                            active_chart["expired"],
                            active_chart["pending_approval"],
                            active_chart["suspended"],
                            active_chart["trial"],
                        ],
                        "backgroundColor": ["#0f766e", "#dc2626", "#ea580c", "#475569", "#1d4ed8"],
                    }
                ],
            },
            "monthly_collections": {
                "labels": [row.month for row in monthly_collection_rows],
                "datasets": [
                    {
                        "label": "Collections",
                        "data": [float(money(row.amount_paid)) for row in monthly_collection_rows],
                        "backgroundColor": "#7c3aed",
                    }
                ],
            },
        },
    }


def get_biz_revenue_report_data(*, period: str = "all", start_date=None, end_date=None) -> dict:
    """Return company-side revenue rows for HTML and CSV export."""

    date_range = resolve_period_range(period, start_date=start_date, end_date=end_date)
    payments_query = _approved_payments_query(date_range).order_by(SubscriptionPayment.approved_at.desc())
    payments = payments_query.all()

    summary = {
        "payments_count": len(payments),
        "revenue": money(sum((payment.amount_paid for payment in payments), Decimal("0.00"))),
        "outstanding_dues": money(
            sum((money(business.amount_due or Decimal("0.00")) for business in Business.query.all()), Decimal("0.00"))
        ),
    }
    return {
        "period": date_range,
        "payments": payments,
        "summary": summary,
    }
