"""Analytics and reporting helpers for owner, staff, and admin dashboards."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import desc, func

from app.extensions import db
from app.models import Customer, Product, Sale, SaleItem
from app.models.base import utc_now
from app.services.credit_service import get_credit_sales_query
from app.services.inventory_service import (
    get_expired_batches,
    get_inventory_overview,
    get_low_stock_products,
    get_near_expiry_batches,
    get_total_remaining_stock_value,
)
from app.services.sales_service import money


DEFAULT_DASHBOARD_PERIOD = "month"
SUPPORTED_PERIODS = {"today", "month", "year", "all", "custom"}


def parse_optional_date(value: str | None) -> date | None:
    """Parse a YYYY-MM-DD string into a date object."""

    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def resolve_period_range(
    period: str | None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Resolve a friendly dashboard/report period into concrete date bounds."""

    today = utc_now().date()
    selected_period = (period or DEFAULT_DASHBOARD_PERIOD).lower()

    if start_date or end_date:
        selected_period = "custom"
        start_date = start_date or end_date or today
        end_date = end_date or today
    elif selected_period == "today":
        start_date = today
        end_date = today
    elif selected_period == "month":
        start_date = today.replace(day=1)
        end_date = today
    elif selected_period == "year":
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif selected_period == "all":
        start_date = None
        end_date = None
    else:
        selected_period = DEFAULT_DASHBOARD_PERIOD
        start_date = today.replace(day=1)
        end_date = today

    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    if selected_period == "today":
        label = "Today"
    elif selected_period == "month":
        label = today.strftime("%B %Y")
    elif selected_period == "year":
        label = str(today.year)
    elif selected_period == "all":
        label = "All Time"
    else:
        label = f"{start_date.isoformat()} to {end_date.isoformat()}"

    return {
        "period": selected_period,
        "start_date": start_date,
        "end_date": end_date,
        "start_datetime": datetime.combine(start_date, time.min) if start_date else None,
        "end_datetime": datetime.combine(end_date, time.max) if end_date else None,
        "label": label,
    }


def apply_sale_date_filters(query, date_range: dict):
    """Apply date constraints to a Sale-based query."""

    if date_range["start_datetime"] is not None:
        query = query.filter(Sale.sale_datetime >= date_range["start_datetime"])
    if date_range["end_datetime"] is not None:
        query = query.filter(Sale.sale_datetime <= date_range["end_datetime"])
    return query


def sum_query_column(query, column) -> Decimal:
    """Safely sum a numeric column."""

    return money(query.with_entities(func.coalesce(func.sum(column), 0)).scalar())


def _chart(labels: list[str], datasets: list[dict]) -> dict:
    """Normalize chart payloads for templates."""

    normalized = []
    for dataset in datasets:
        normalized.append(
            {
                "label": dataset["label"],
                "data": [float(money(value)) for value in dataset["data"]],
                "borderColor": dataset.get("borderColor"),
                "backgroundColor": dataset.get("backgroundColor"),
                "tension": dataset.get("tension", 0.35),
                "fill": dataset.get("fill", False),
            }
        )
    return {"labels": labels, "datasets": normalized}


def _build_sales_trend_chart(base_query, date_range: dict) -> dict:
    """Build daily revenue and cash-collected trend data."""

    rows = (
        apply_sale_date_filters(base_query, date_range)
        .with_entities(
            func.date(Sale.sale_datetime).label("day"),
            func.coalesce(func.sum(Sale.total_revenue), 0).label("revenue"),
            func.coalesce(func.sum(Sale.amount_paid), 0).label("cash_collected"),
        )
        .group_by(func.date(Sale.sale_datetime))
        .order_by(func.date(Sale.sale_datetime))
        .all()
    )
    labels = [row.day for row in rows]
    return _chart(
        labels,
        [
            {
                "label": "Revenue",
                "data": [row.revenue for row in rows],
                "borderColor": "#0f766e",
                "backgroundColor": "rgba(15, 118, 110, 0.14)",
                "fill": True,
            },
            {
                "label": "Cash Collected",
                "data": [row.cash_collected for row in rows],
                "borderColor": "#0f172a",
                "backgroundColor": "rgba(15, 23, 42, 0.10)",
            },
        ],
    )


def _build_profit_trend_chart(base_query, date_range: dict) -> dict:
    """Build daily profit trend data."""

    rows = (
        apply_sale_date_filters(base_query, date_range)
        .with_entities(
            func.date(Sale.sale_datetime).label("day"),
            func.coalesce(func.sum(Sale.total_gross_profit), 0).label("gross_profit"),
            func.coalesce(func.sum(Sale.total_realized_profit), 0).label("realized_profit"),
            func.coalesce(func.sum(Sale.total_unrealized_profit), 0).label("unrealized_profit"),
        )
        .group_by(func.date(Sale.sale_datetime))
        .order_by(func.date(Sale.sale_datetime))
        .all()
    )
    labels = [row.day for row in rows]
    return _chart(
        labels,
        [
            {
                "label": "Gross Profit",
                "data": [row.gross_profit for row in rows],
                "borderColor": "#1d4ed8",
                "backgroundColor": "rgba(29, 78, 216, 0.10)",
            },
            {
                "label": "Realized Profit",
                "data": [row.realized_profit for row in rows],
                "borderColor": "#7c3aed",
                "backgroundColor": "rgba(124, 58, 237, 0.12)",
            },
            {
                "label": "Unrealized Profit",
                "data": [row.unrealized_profit for row in rows],
                "borderColor": "#ea580c",
                "backgroundColor": "rgba(234, 88, 12, 0.12)",
            },
        ],
    )


def _top_product_rows(business_id: str, date_range: dict, *, order_metric, value_label: str) -> dict:
    """Return top product chart data for quantity or profit views."""

    rows = (
        db.session.query(
            Product.name.label("product_name"),
            func.coalesce(func.sum(SaleItem.quantity), 0).label("quantity_sold"),
            func.coalesce(func.sum(SaleItem.item_profit), 0).label("profit"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.business_id == business_id)
    )
    rows = apply_sale_date_filters(rows, date_range)
    rows = (
        rows.group_by(Product.id, Product.name)
        .order_by(desc(order_metric))
        .limit(5)
        .all()
    )
    return {
        "labels": [row.product_name for row in rows],
        "datasets": [
            {
                "label": value_label,
                "data": [
                    float(money(row.quantity_sold if value_label == "Quantity Sold" else row.profit))
                    for row in rows
                ],
                "backgroundColor": [
                    "#0f766e",
                    "#1d4ed8",
                    "#7c3aed",
                    "#ea580c",
                    "#dc2626",
                ],
            }
        ],
    }


def _payment_mode_breakdown(base_query, date_range: dict) -> dict:
    """Return payment mode counts and revenue totals for charts."""

    rows = (
        apply_sale_date_filters(base_query, date_range)
        .with_entities(
            Sale.payment_mode,
            func.count(Sale.id).label("transaction_count"),
            func.coalesce(func.sum(Sale.total_revenue), 0).label("revenue"),
        )
        .group_by(Sale.payment_mode)
        .order_by(Sale.payment_mode)
        .all()
    )
    return {
        "labels": [row.payment_mode.title() for row in rows],
        "datasets": [
            {
                "label": "Revenue",
                "data": [float(money(row.revenue)) for row in rows],
                "backgroundColor": ["#0f766e", "#ea580c", "#1d4ed8"],
            }
        ],
        "meta": {
            row.payment_mode: {
                "count": row.transaction_count,
                "revenue": money(row.revenue),
            }
            for row in rows
        },
    }


def get_owner_dashboard_analytics(
    business_id: str,
    *,
    period: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    near_expiry_days: int = 7,
) -> dict:
    """Return owner dashboard metrics, charts, and supporting data."""

    date_range = resolve_period_range(period, start_date=start_date, end_date=end_date)
    sales_query = Sale.query.filter_by(business_id=business_id)
    filtered_sales = apply_sale_date_filters(sales_query, date_range)

    total_quantity_sold = (
        db.session.query(func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.business_id == business_id)
    )
    total_quantity_sold = apply_sale_date_filters(total_quantity_sold, date_range).scalar()

    metrics = {
        "total_revenue": sum_query_column(filtered_sales, Sale.total_revenue),
        "gross_profit": sum_query_column(filtered_sales, Sale.total_gross_profit),
        "realized_profit": sum_query_column(filtered_sales, Sale.total_realized_profit),
        "unrealized_profit": sum_query_column(filtered_sales, Sale.total_unrealized_profit),
        "cash_collected": sum_query_column(filtered_sales, Sale.amount_paid),
        "credit_outstanding": sum_query_column(
            Sale.query.filter_by(business_id=business_id).filter(Sale.amount_due > 0),
            Sale.amount_due,
        ),
        "total_transactions": filtered_sales.count(),
        "total_quantity_sold": money(total_quantity_sold),
        "total_products": Product.query.filter_by(business_id=business_id).count(),
        "total_customers": Customer.query.filter_by(business_id=business_id).count(),
        "low_stock_count": len(get_low_stock_products(business_id)),
        "near_expiry_count": len(get_near_expiry_batches(business_id, days=near_expiry_days)),
        "expired_stock_count": len(get_expired_batches(business_id)),
        "stock_value_remaining": get_total_remaining_stock_value(business_id),
    }

    recent_sales = (
        sales_query.order_by(Sale.sale_datetime.desc()).limit(8).all()
    )

    top_quantity_metric = func.coalesce(func.sum(SaleItem.quantity), 0)
    top_profit_metric = func.coalesce(func.sum(SaleItem.item_profit), 0)

    return {
        "period": date_range,
        "metrics": metrics,
        "recent_sales": recent_sales,
        "low_stock_preview": get_low_stock_products(business_id)[:6],
        "charts": {
            "revenue_trend": _build_sales_trend_chart(sales_query, date_range),
            "profit_trend": _build_profit_trend_chart(sales_query, date_range),
            "top_products": _top_product_rows(
                business_id,
                date_range,
                order_metric=top_quantity_metric,
                value_label="Quantity Sold",
            ),
            "profitable_products": _top_product_rows(
                business_id,
                date_range,
                order_metric=top_profit_metric,
                value_label="Profit",
            ),
            "payment_modes": _payment_mode_breakdown(sales_query, date_range),
        },
    }


def get_staff_dashboard_analytics(business_id: str) -> dict:
    """Return staff-safe operational dashboard data."""

    date_range = resolve_period_range("today")
    sales_query = Sale.query.filter_by(business_id=business_id)
    today_sales = apply_sale_date_filters(sales_query, date_range)
    today_items = (
        db.session.query(func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.business_id == business_id)
    )
    today_items = apply_sale_date_filters(today_items, date_range).scalar()

    inventory_rows = [row for row in get_inventory_overview(business_id) if row["product"].is_active]

    return {
        "today_transactions": today_sales.count(),
        "today_products_sold": money(today_items),
        "available_products": Product.query.filter_by(business_id=business_id, is_active=True).count(),
        "low_stock_count": len(get_low_stock_products(business_id)),
        "recent_sales": sales_query.order_by(Sale.sale_datetime.desc()).limit(6).all(),
        "product_snapshot": inventory_rows[:6],
    }


def get_sales_report_data(
    business_id: str,
    *,
    period: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    payment_status: str = "all",
) -> dict:
    """Return tenant sales report rows and summary."""

    date_range = resolve_period_range(period or "all", start_date=start_date, end_date=end_date)
    query = Sale.query.filter_by(business_id=business_id).order_by(Sale.sale_datetime.desc())
    query = apply_sale_date_filters(query, date_range)
    if payment_status != "all":
        query = query.filter_by(payment_status=payment_status)

    sales = query.all()
    return {
        "period": date_range,
        "sales": sales,
        "summary": {
            "transactions": len(sales),
            "revenue": money(sum((sale.total_revenue for sale in sales), Decimal("0.00"))),
            "cash_collected": money(sum((sale.amount_paid for sale in sales), Decimal("0.00"))),
            "due": money(sum((sale.amount_due for sale in sales), Decimal("0.00"))),
        },
    }


def get_profit_report_data(
    business_id: str,
    *,
    period: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Return tenant profit report data."""

    sales_data = get_sales_report_data(
        business_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    sales = sales_data["sales"]
    sales_query = Sale.query.filter_by(business_id=business_id)
    date_range = sales_data["period"]
    return {
        "period": date_range,
        "sales": sales,
        "summary": {
            "revenue": money(sum((sale.total_revenue for sale in sales), Decimal("0.00"))),
            "gross_profit": money(sum((sale.total_gross_profit for sale in sales), Decimal("0.00"))),
            "realized_profit": money(sum((sale.total_realized_profit for sale in sales), Decimal("0.00"))),
            "unrealized_profit": money(sum((sale.total_unrealized_profit for sale in sales), Decimal("0.00"))),
        },
        "chart": _build_profit_trend_chart(sales_query, date_range),
    }


def get_credit_report_data(
    business_id: str,
    *,
    customer_id: str | None = None,
) -> dict:
    """Return outstanding credit sales and summary data."""

    query = get_credit_sales_query(business_id)
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    credit_sales = query.all()
    return {
        "credit_sales": credit_sales,
        "summary": {
            "open_credit_sales": len(credit_sales),
            "customers_with_dues": len({sale.customer_id for sale in credit_sales if sale.customer_id}),
            "outstanding_credit": money(sum((sale.amount_due for sale in credit_sales), Decimal("0.00"))),
        },
    }


def get_inventory_report_data(
    business_id: str,
    *,
    search: str | None = None,
    near_expiry_days: int = 7,
) -> dict:
    """Return inventory overview and alert data for reporting pages."""

    rows = get_inventory_overview(business_id, search=search or None)
    return {
        "rows": rows,
        "summary": {
            "total_products": len(rows),
            "low_stock_count": len(get_low_stock_products(business_id)),
            "near_expiry_count": len(get_near_expiry_batches(business_id, days=near_expiry_days)),
            "expired_count": len(get_expired_batches(business_id)),
            "stock_value": get_total_remaining_stock_value(business_id),
        },
    }


def get_customer_ledgers_report_data(business_id: str) -> dict:
    """Return customer balance summary rows."""

    customers = (
        Customer.query.filter_by(business_id=business_id)
        .order_by(desc(Customer.outstanding_balance), Customer.name.asc())
        .all()
    )
    active_dues = [customer for customer in customers if money(customer.outstanding_balance) > 0]
    return {
        "customers": customers,
        "summary": {
            "customers_with_dues": len(active_dues),
            "outstanding_balance": money(
                sum((customer.outstanding_balance for customer in active_dues), Decimal("0.00"))
            ),
        },
    }
