"""Reporting helpers for dashboard and monitoring pages."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Category, Customer, Product, Sale, StockBatch
from app.services.credit_service import get_credit_sales_query
from app.services.inventory_service import (
    get_expired_batches,
    get_low_stock_products,
    get_near_expiry_batches,
)
from app.services.sales_service import money


def day_bounds(target_date=None):
    """Return start and end datetimes for the given day."""

    base_date = target_date or datetime.utcnow().date()
    return datetime.combine(base_date, time.min), datetime.combine(base_date, time.max)


def get_owner_dashboard_metrics(business_id: str, *, near_expiry_days: int = 7) -> dict:
    """Return real business metrics for the owner dashboard."""

    today_start, today_end = day_bounds()
    today_sales = Sale.query.filter(
        Sale.business_id == business_id,
        Sale.sale_datetime >= today_start,
        Sale.sale_datetime <= today_end,
    )

    def sum_column(query, column):
        return money(query.with_entities(func.coalesce(func.sum(column), 0)).scalar())

    metrics = {
        "total_products": Product.query.filter_by(business_id=business_id).count(),
        "total_categories": Category.query.filter_by(business_id=business_id, is_active=True).count(),
        "total_customers": Customer.query.filter_by(business_id=business_id).count(),
        "total_stock_batches": StockBatch.query.filter_by(business_id=business_id).count(),
        "today_revenue": sum_column(today_sales, Sale.total_revenue),
        "today_gross_profit": sum_column(today_sales, Sale.total_gross_profit),
        "today_realized_profit": sum_column(today_sales, Sale.total_realized_profit),
        "today_unrealized_profit": sum_column(today_sales, Sale.total_unrealized_profit),
        "outstanding_credit_amount": sum_column(
            Sale.query.filter_by(business_id=business_id).filter(Sale.amount_due > 0),
            Sale.amount_due,
        ),
        "low_stock_count": len(get_low_stock_products(business_id)),
        "near_expiry_count": len(get_near_expiry_batches(business_id, days=near_expiry_days)),
        "expired_stock_count": len(get_expired_batches(business_id)),
    }
    return metrics


def get_operational_summary(business_id: str) -> dict:
    """Return simple staff-facing operational metrics."""

    return {
        "available_products": Product.query.filter_by(business_id=business_id, is_active=True).count(),
        "total_customers": Customer.query.filter_by(business_id=business_id).count(),
        "sales_recorded": Sale.query.filter_by(business_id=business_id).count(),
    }


def get_credit_summary(business_id: str) -> dict:
    """Return summary values for credit pages."""

    credit_query = get_credit_sales_query(business_id)
    return {
        "open_credit_sales": credit_query.count(),
        "outstanding_credit_amount": money(
            credit_query.with_entities(func.coalesce(func.sum(Sale.amount_due), 0)).scalar()
        ),
    }
