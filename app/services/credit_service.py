"""Credit sale and repayment logic."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Customer, Repayment, Sale
from app.services.auth_service import record_audit_event
from app.services.exceptions import BusinessRuleError
from app.services.sales_service import calculate_profit_realization, money


def sync_customer_outstanding_balance(customer: Customer | None) -> Decimal:
    """Recalculate and store a customer's outstanding balance from sales."""

    if customer is None:
        return Decimal("0.00")

    outstanding = (
        db.session.query(func.coalesce(func.sum(Sale.amount_due), 0))
        .filter(Sale.business_id == customer.business_id, Sale.customer_id == customer.id)
        .scalar()
    )
    customer.outstanding_balance = money(outstanding)
    return customer.outstanding_balance


def get_credit_sales_query(business_id: str):
    """Return sales that still have outstanding dues."""

    return (
        Sale.query.filter_by(business_id=business_id)
        .filter(Sale.amount_due > 0)
        .order_by(Sale.sale_datetime.desc())
    )


def record_repayment(*, sale: Sale, amount_paid, payment_date, note: str | None, actor) -> Repayment:
    """Apply a repayment to a sale and refresh payment/profit state."""

    if sale.customer is None:
        raise BusinessRuleError("Repayments can only be recorded for sales linked to a customer.")

    if sale.amount_due <= 0:
        raise BusinessRuleError("This sale has no outstanding balance.")

    repayment_amount = money(amount_paid)
    if repayment_amount <= 0:
        raise BusinessRuleError("Repayment amount must be greater than zero.")

    if repayment_amount > sale.amount_due:
        raise BusinessRuleError("Repayment amount cannot exceed the outstanding due.")

    payment_timestamp = datetime.combine(payment_date, time.min) if payment_date else datetime.utcnow()
    if payment_timestamp.date() < sale.sale_datetime.date():
        raise BusinessRuleError("Repayment date cannot be earlier than the original sale date.")

    repayment = Repayment(
        business_id=sale.business_id,
        sale=sale,
        customer=sale.customer,
        amount_paid=repayment_amount,
        payment_date=payment_timestamp,
        received_by=actor,
        note=(note or "").strip() or None,
    )
    db.session.add(repayment)
    db.session.flush()

    sale.amount_paid = money(sale.amount_paid + repayment_amount)
    sale.refresh_payment_status()
    sale.total_realized_profit, sale.total_unrealized_profit = calculate_profit_realization(
        sale.total_revenue,
        sale.total_gross_profit,
        sale.amount_paid,
    )
    sync_customer_outstanding_balance(sale.customer)

    record_audit_event(
        action="repayment_create",
        description=f"Repayment of {repayment.amount_paid} recorded for sale '{sale.id}'.",
        entity_type="repayment",
        entity_id=repayment.id,
        user=actor,
        business=actor.business,
    )
    return repayment


def get_customer_credit_sales(customer: Customer):
    """Return the customer's credit-related sales."""

    return (
        Sale.query.filter_by(business_id=customer.business_id, customer_id=customer.id)
        .filter(Sale.amount_due > 0)
        .order_by(Sale.sale_datetime.desc())
        .all()
    )


def get_customer_repayments(customer: Customer):
    """Return repayments for a customer ledger."""

    return (
        Repayment.query.filter_by(business_id=customer.business_id, customer_id=customer.id)
        .order_by(Repayment.payment_date.desc())
        .all()
    )
