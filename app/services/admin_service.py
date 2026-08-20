"""Platform-wide Super Admin services and analytics."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import desc, func, or_

from app.extensions import db
from app.models import (
    AuditLog,
    Business,
    Customer,
    LoginAttempt,
    Product,
    Sale,
    SaleItem,
    StockBatch,
    SubscriptionPayment,
    User,
)
from app.models.base import utc_now
from app.services.analytics_service import apply_sale_date_filters, resolve_period_range
from app.services.auth_service import record_audit_event
from app.services.exceptions import BusinessRuleError
from app.services.inventory_service import get_expired_batches, get_low_stock_products, get_near_expiry_batches
from app.services.sales_service import money
from app.services.subscription_service import (
    FULL_PLAN_NAME,
    get_effective_subscription_status,
    get_platform_subscription_overview,
    get_subscription_summary,
    initialize_business_subscription,
)


def create_business_with_owner(
    *,
    business_name: str,
    owner_name: str,
    owner_email: str,
    owner_username: str,
    owner_password: str,
    phone: str | None,
    business_email: str | None,
    address: str | None,
    business_type: str | None,
    preferred_language: str,
    status: str,
    plan_name: str,
    monthly_fee,
    subscription_status: str,
    currency_symbol: str,
    preferred_currency: str,
    near_expiry_threshold_days: int,
    receipt_footer_note: str | None,
    actor,
) -> Business:
    """Create a business account and its owner from the Super Admin panel."""

    normalized_owner_email = owner_email.strip().lower()
    normalized_owner_username = owner_username.strip().lower()
    normalized_business_email = (business_email or owner_email).strip().lower()

    if User.query.filter(
        or_(User.email == normalized_owner_email, User.username == normalized_owner_username)
    ).first():
        raise BusinessRuleError("The owner email or username is already in use.")

    if Business.query.filter_by(email=normalized_business_email).first():
        raise BusinessRuleError("A business with that email already exists.")

    business = Business(
        business_name=business_name.strip(),
        owner_name=owner_name.strip(),
        phone=(phone or "").strip() or None,
        email=normalized_business_email,
        address=(address or "").strip() or None,
        business_type=(business_type or "").strip() or None,
        preferred_language=preferred_language,
        status=status,
        plan_name=(plan_name or FULL_PLAN_NAME).strip() or FULL_PLAN_NAME,
        subscription_plan=(plan_name or FULL_PLAN_NAME).strip() or FULL_PLAN_NAME,
        monthly_fee=money(monthly_fee or 500),
        currency_symbol=(currency_symbol or "Rs.").strip() or "Rs.",
        preferred_currency=(preferred_currency or "NPR").strip() or "NPR",
        near_expiry_threshold_days=near_expiry_threshold_days,
        receipt_footer_note=(receipt_footer_note or "").strip() or None,
    )
    initialize_business_subscription(
        business,
        status=subscription_status or ("trial" if status != "suspended" else "suspended"),
    )
    owner = User(
        business=business,
        full_name=owner_name.strip(),
        username=normalized_owner_username,
        email=normalized_owner_email,
        role="owner",
        status="active",
        preferred_language=preferred_language,
        is_primary_owner=True,
    )
    owner.set_password(owner_password)

    db.session.add_all([business, owner])
    db.session.flush()

    record_audit_event(
        action="admin_business_onboarded",
        description=f"Super Admin onboarded business '{business.business_name}'.",
        entity_type="business",
        entity_id=business.id,
        user=actor,
        business=business,
    )
    return business


def set_business_status(business: Business, *, status: str, actor) -> Business:
    """Suspend or reactivate a business account."""

    if business.status == status:
        return business

    previous_status = business.status
    business.status = status
    record_audit_event(
        action="business_status_changed",
        description=(
            f"Super Admin changed business '{business.business_name}' status "
            f"from '{previous_status}' to '{status}'."
        ),
        entity_type="business",
        entity_id=business.id,
        user=actor,
        business=business,
        severity="warning" if status == "suspended" else "info",
    )
    return business


def _filtered_business_query(*, search: str = "", status: str = "all", business_type: str = "all"):
    """Return a filtered business query for admin pages."""

    query = Business.query.order_by(Business.created_at.desc())
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Business.business_name.ilike(pattern),
                Business.owner_name.ilike(pattern),
                Business.email.ilike(pattern),
                Business.phone.ilike(pattern),
            )
        )
    if status != "all":
        query = query.filter_by(status=status)
    if business_type != "all":
        query = query.filter_by(business_type=business_type)
    return query


def _business_sales_totals(business_id: str) -> dict:
    """Summarize sales and credit state for a business."""

    sales = Sale.query.filter_by(business_id=business_id)
    return {
        "sales_count": sales.count(),
        "revenue": money(sales.with_entities(func.coalesce(func.sum(Sale.total_revenue), 0)).scalar()),
        "gross_profit": money(
            sales.with_entities(func.coalesce(func.sum(Sale.total_gross_profit), 0)).scalar()
        ),
        "realized_profit": money(
            sales.with_entities(func.coalesce(func.sum(Sale.total_realized_profit), 0)).scalar()
        ),
        "unrealized_profit": money(
            sales.with_entities(func.coalesce(func.sum(Sale.total_unrealized_profit), 0)).scalar()
        ),
        "credit_outstanding": money(sales.with_entities(func.coalesce(func.sum(Sale.amount_due), 0)).scalar()),
    }


def _business_health_metrics(business: Business) -> dict:
    """Return tenant alert counts for admin views."""

    return {
        "low_stock_count": len(get_low_stock_products(business.id)),
        "near_expiry_count": len(
            get_near_expiry_batches(business.id, days=business.near_expiry_threshold_days or 7)
        ),
        "expired_stock_count": len(get_expired_batches(business.id)),
    }


def get_business_list_rows(*, search: str = "", status: str = "all", business_type: str = "all") -> list[dict]:
    """Return business list rows with summary metrics for admin management."""

    rows = []
    for business in _filtered_business_query(search=search, status=status, business_type=business_type).all():
        sales_totals = _business_sales_totals(business.id)
        health = _business_health_metrics(business)
        rows.append(
            {
                "business": business,
                "subscription_summary": get_subscription_summary(business),
                "owner_count": User.query.filter_by(business_id=business.id, role="owner").count(),
                "staff_count": User.query.filter_by(business_id=business.id, role="staff").count(),
                **sales_totals,
                **health,
            }
        )
    return rows


def get_platform_user_rows(
    *,
    search: str = "",
    role: str = "all",
    business_id: str = "all",
) -> list[User]:
    """Return filtered platform users for the admin user monitor."""

    query = User.query.order_by(User.created_at.desc())
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                User.username.ilike(pattern),
            )
        )
    if role != "all":
        query = query.filter_by(role=role)
    if business_id != "all":
        query = query.filter_by(business_id=business_id)
    return query.all()


def get_business_detail_data(business_id: str) -> dict:
    """Return business detail analytics for a Super Admin detail page."""

    business = db.session.get(Business, business_id)
    if business is None:
        raise BusinessRuleError("Business not found.")

    sales_totals = _business_sales_totals(business.id)
    health = _business_health_metrics(business)
    owners = (
        User.query.filter_by(business_id=business.id, role="owner")
        .order_by(User.created_at.asc())
        .all()
    )
    recent_logs = (
        AuditLog.query.filter_by(business_id=business.id)
        .order_by(AuditLog.created_at.desc())
        .limit(12)
        .all()
    )
    recent_sales = (
        Sale.query.filter_by(business_id=business.id)
        .order_by(Sale.sale_datetime.desc())
        .limit(10)
        .all()
    )

    return {
        "business": business,
        "subscription_summary": get_subscription_summary(business),
        "owners": owners,
        "staff_count": User.query.filter_by(business_id=business.id, role="staff").count(),
        "metrics": {
            "total_users": User.query.filter_by(business_id=business.id).count(),
            "total_customers": Customer.query.filter_by(business_id=business.id).count(),
            "total_products": Product.query.filter_by(business_id=business.id).count(),
            "total_stock_batches": StockBatch.query.filter_by(business_id=business.id).count(),
            "total_subscription_payments": SubscriptionPayment.query.filter_by(business_id=business.id).count(),
            **sales_totals,
            **health,
        },
        "recent_logs": recent_logs,
        "recent_sales": recent_sales,
        "recent_payments": (
            SubscriptionPayment.query.filter_by(business_id=business.id)
            .order_by(SubscriptionPayment.submitted_at.desc())
            .limit(8)
            .all()
        ),
    }


def get_activity_logs(*, business_id: str = "all", severity: str = "all", limit: int = 100) -> list[AuditLog]:
    """Return filtered audit log rows for admin monitoring."""

    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    if business_id != "all":
        query = query.filter_by(business_id=business_id)
    if severity != "all":
        query = query.filter_by(severity=severity)
    return query.limit(limit).all()


def get_login_attempt_rows(
    *,
    business_id: str = "all",
    outcome: str = "all",
    limit: int = 100,
) -> list[LoginAttempt]:
    """Return filtered login attempt rows for admin monitoring."""

    query = LoginAttempt.query.order_by(LoginAttempt.attempted_at.desc())
    if business_id != "all":
        query = query.filter_by(business_id=business_id)
    if outcome == "success":
        query = query.filter_by(success=True)
    elif outcome == "failed":
        query = query.filter_by(success=False)
    return query.limit(limit).all()


def get_platform_dashboard_data(*, period: str = "month") -> dict:
    """Return platform-wide metrics, charts, and monitoring signals."""

    date_range = resolve_period_range(period)
    all_sales = Sale.query
    filtered_sales = apply_sale_date_filters(all_sales, date_range)
    businesses = Business.query.order_by(Business.created_at.desc()).all()
    subscription_overview = get_platform_subscription_overview()

    low_stock_total = 0
    near_expiry_total = 0
    expired_total = 0
    for business in businesses:
        low_stock_total += len(get_low_stock_products(business.id))
        near_expiry_total += len(get_near_expiry_batches(business.id, days=business.near_expiry_threshold_days or 7))
        expired_total += len(get_expired_batches(business.id))

    metrics = {
        "total_businesses": len(businesses),
        "active_businesses": Business.query.filter_by(status="active").count(),
        "suspended_businesses": Business.query.filter_by(status="suspended").count(),
        "total_users": User.query.count(),
        "total_ops_admins": User.query.filter_by(role="ops_admin").count(),
        "total_biz_admins": User.query.filter_by(role="biz_admin").count(),
        "total_owners": User.query.filter_by(role="owner").count(),
        "total_staff": User.query.filter_by(role="staff").count(),
        "low_stock_issues": low_stock_total,
        "near_expiry_count": near_expiry_total,
        "expired_stock_count": expired_total,
    }
    metrics.update(subscription_overview)

    tenant_quantity_query = (
        db.session.query(func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
    )
    tenant_activity = {
        "total_products": Product.query.count(),
        "total_tenant_sales": apply_sale_date_filters(tenant_quantity_query, date_range).scalar() or 0,
        "total_tenant_revenue": money(
            filtered_sales.with_entities(func.coalesce(func.sum(Sale.total_revenue), 0)).scalar()
        ),
        "total_tenant_transactions": filtered_sales.count(),
        "total_tenant_credit_outstanding": money(
            all_sales.with_entities(func.coalesce(func.sum(Sale.amount_due), 0)).scalar()
        ),
    }

    business_growth_rows = (
        Business.query.with_entities(
            func.date(Business.registration_date).label("day"),
            func.count(Business.id).label("business_count"),
        )
        .group_by(func.date(Business.registration_date))
        .order_by(func.date(Business.registration_date))
        .all()
    )

    subscription_revenue_query = SubscriptionPayment.query.filter_by(status="approved")
    if date_range["start_datetime"] is not None:
        subscription_revenue_query = subscription_revenue_query.filter(
            SubscriptionPayment.approved_at >= date_range["start_datetime"]
        )
    if date_range["end_datetime"] is not None:
        subscription_revenue_query = subscription_revenue_query.filter(
            SubscriptionPayment.approved_at <= date_range["end_datetime"]
        )
    subscription_revenue_rows = (
        subscription_revenue_query.with_entities(
            func.date(SubscriptionPayment.approved_at).label("day"),
            func.coalesce(func.sum(SubscriptionPayment.amount_paid), 0).label("amount_paid"),
            func.count(SubscriptionPayment.id).label("payment_count"),
        )
        .group_by(func.date(SubscriptionPayment.approved_at))
        .order_by(func.date(SubscriptionPayment.approved_at))
        .all()
    )

    tenant_activity_rows = (
        filtered_sales.with_entities(
            func.date(Sale.sale_datetime).label("day"),
            func.coalesce(func.sum(Sale.total_revenue), 0).label("revenue"),
            func.count(Sale.id).label("transaction_count"),
            func.coalesce(func.sum(Sale.amount_due), 0).label("credit_due"),
        )
        .group_by(func.date(Sale.sale_datetime))
        .order_by(func.date(Sale.sale_datetime))
        .all()
    )

    top_business_rows = (
        db.session.query(
            Business.business_name,
            func.coalesce(func.sum(Sale.total_revenue), 0).label("revenue"),
            func.coalesce(func.sum(Sale.amount_due), 0).label("credit_due"),
            func.count(Sale.id).label("sales_count"),
        )
        .outerjoin(Sale, Sale.business_id == Business.id)
    )
    top_business_rows = (
        apply_sale_date_filters(top_business_rows, date_range)
        .group_by(Business.id, Business.business_name)
        .order_by(desc(func.coalesce(func.sum(Sale.total_revenue), 0)))
        .limit(6)
        .all()
    )

    failed_window = utc_now() - timedelta(hours=24)
    suspicious_summary = {
        "failed_logins_24h": LoginAttempt.query.filter(
            LoginAttempt.success.is_(False),
            LoginAttempt.attempted_at >= failed_window,
        ).count(),
        "suspended_login_blocks": AuditLog.query.filter_by(action="blocked_suspended_business_login").count(),
    }

    return {
        "period": date_range,
        "metrics": metrics,
        "tenant_activity": tenant_activity,
        "charts": {
            "business_growth": {
                "labels": [row.day for row in business_growth_rows],
                "datasets": [
                    {
                        "label": "Businesses",
                        "data": [row.business_count for row in business_growth_rows],
                        "borderColor": "#1d4ed8",
                        "backgroundColor": "rgba(29, 78, 216, 0.12)",
                        "fill": True,
                    }
                ],
            },
            "subscription_revenue": {
                "labels": [row.day for row in subscription_revenue_rows],
                "datasets": [
                    {
                        "label": "Subscription Revenue",
                        "data": [float(money(row.amount_paid)) for row in subscription_revenue_rows],
                        "borderColor": "#0f766e",
                        "backgroundColor": "rgba(15, 118, 110, 0.16)",
                        "fill": True,
                    },
                    {
                        "label": "Approved Payments",
                        "data": [row.payment_count for row in subscription_revenue_rows],
                        "borderColor": "#1d4ed8",
                        "backgroundColor": "rgba(29, 78, 216, 0.10)",
                    },
                ],
            },
            "tenant_activity_trend": {
                "labels": [row.day for row in tenant_activity_rows],
                "datasets": [
                    {
                        "label": "Tenant Revenue",
                        "data": [float(money(row.revenue)) for row in tenant_activity_rows],
                        "borderColor": "#7c3aed",
                        "backgroundColor": "rgba(124, 58, 237, 0.10)",
                        "fill": True,
                    },
                    {
                        "label": "Tenant Transactions",
                        "data": [row.transaction_count for row in tenant_activity_rows],
                        "borderColor": "#0f172a",
                        "backgroundColor": "rgba(15, 23, 42, 0.10)",
                    },
                    {
                        "label": "Outstanding Credit",
                        "data": [float(money(row.credit_due)) for row in tenant_activity_rows],
                        "borderColor": "#ea580c",
                        "backgroundColor": "rgba(234, 88, 12, 0.10)",
                    },
                ],
            },
            "top_businesses": {
                "labels": [row.business_name for row in top_business_rows],
                "datasets": [
                    {
                        "label": "Tenant Revenue",
                        "data": [float(money(row.revenue)) for row in top_business_rows],
                        "backgroundColor": ["#0f766e", "#1d4ed8", "#7c3aed", "#ea580c", "#0f172a", "#dc2626"],
                    }
                ],
            },
        },
        "top_business_rows": top_business_rows,
        "recent_logs": get_activity_logs(limit=8),
        "recent_login_attempts": get_login_attempt_rows(limit=8),
        "suspicious_summary": suspicious_summary,
    }


def get_ops_dashboard_data() -> dict:
    """Return operational monitoring data for ops admin routes."""

    businesses = Business.query.order_by(Business.created_at.desc()).all()
    recent_login_failures = (
        LoginAttempt.query.filter_by(success=False)
        .order_by(LoginAttempt.attempted_at.desc())
        .limit(8)
        .all()
    )
    status_breakdown = {"active": 0, "suspended": 0, "inactive": 0, "pending": 0}
    for business in businesses:
        status_breakdown[business.status] = status_breakdown.get(business.status, 0) + 1

    return {
        "metrics": {
            "total_businesses": len(businesses),
            "active_businesses": Business.query.filter_by(status="active").count(),
            "suspended_businesses": Business.query.filter_by(status="suspended").count(),
            "total_users": User.query.count(),
            "owners_count": User.query.filter_by(role="owner").count(),
            "staff_count": User.query.filter_by(role="staff").count(),
            "failed_logins_24h": LoginAttempt.query.filter(
                LoginAttempt.success.is_(False),
                LoginAttempt.attempted_at >= utc_now() - timedelta(hours=24),
            ).count(),
        },
        "recent_logs": get_activity_logs(limit=8),
        "recent_login_failures": recent_login_failures,
        "charts": {
            "business_statuses": {
                "labels": ["Active", "Suspended", "Inactive", "Pending"],
                "datasets": [
                    {
                        "label": "Businesses",
                        "data": [
                            status_breakdown.get("active", 0),
                            status_breakdown.get("suspended", 0),
                            status_breakdown.get("inactive", 0),
                            status_breakdown.get("pending", 0),
                        ],
                        "backgroundColor": ["#0f766e", "#dc2626", "#475569", "#ea580c"],
                    }
                ],
            }
        },
    }


def get_platform_report_data(*, period: str = "all", start_date=None, end_date=None) -> dict:
    """Return platform report rows suitable for admin HTML and CSV export."""

    date_range = resolve_period_range(period, start_date=start_date, end_date=end_date)
    rows = []
    for business in Business.query.order_by(Business.business_name.asc()).all():
        sales_query = Sale.query.filter_by(business_id=business.id)
        filtered_sales = apply_sale_date_filters(sales_query, date_range)
        rows.append(
            {
                "business": business,
                "user_count": User.query.filter_by(business_id=business.id).count(),
                "sales_count": filtered_sales.count(),
                "revenue": money(
                    filtered_sales.with_entities(func.coalesce(func.sum(Sale.total_revenue), 0)).scalar()
                ),
                "gross_profit": money(
                    filtered_sales.with_entities(func.coalesce(func.sum(Sale.total_gross_profit), 0)).scalar()
                ),
                "credit_outstanding": money(
                    sales_query.with_entities(func.coalesce(func.sum(Sale.amount_due), 0)).scalar()
                ),
            }
        )
    return {
        "period": date_range,
        "rows": rows,
        "summary": {
            "business_count": len(rows),
            "revenue": money(sum((row["revenue"] for row in rows), Decimal("0.00"))),
            "gross_profit": money(sum((row["gross_profit"] for row in rows), Decimal("0.00"))),
            "credit_outstanding": money(sum((row["credit_outstanding"] for row in rows), Decimal("0.00"))),
        },
    }
