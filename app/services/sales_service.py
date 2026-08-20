"""Sales and POS business logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models import Customer, Product, Sale, SaleItem
from app.services.auth_service import record_audit_event
from app.services.exceptions import BusinessRuleError, InsufficientStockError
from app.services.inventory_service import as_decimal, get_available_batches_for_product


MONEY_QUANTUM = Decimal("0.01")


def money(value) -> Decimal:
    """Normalize values to two decimal places."""

    return as_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass
class PreparedSaleLine:
    """Normalized sale input line before FIFO allocation."""

    product: Product
    quantity: Decimal
    actual_selling_price: Decimal


def calculate_profit_realization(total_revenue, gross_profit, amount_paid) -> tuple[Decimal, Decimal]:
    """Split profit into realized and unrealized portions.

    This prototype uses proportional realization for partial payments:
    realized profit = gross profit * (amount_paid / total_revenue)
    unrealized profit = gross profit - realized profit
    """

    total_revenue = money(total_revenue)
    gross_profit = money(gross_profit)
    amount_paid = money(amount_paid)

    if total_revenue <= 0 or gross_profit <= 0:
        return money(Decimal("0")), gross_profit

    if amount_paid <= 0:
        return money(Decimal("0")), gross_profit

    paid_ratio = min(amount_paid / total_revenue, Decimal("1"))
    realized = money(gross_profit * paid_ratio)
    unrealized = money(gross_profit - realized)
    return realized, unrealized


def prepare_sale_lines(form, business_id: str) -> list[PreparedSaleLine]:
    """Validate and normalize sale line items."""

    prepared_lines: list[PreparedSaleLine] = []

    for entry in form.items.entries:
        product_id = (entry.form.product_id.data or "").strip()
        quantity = entry.form.quantity.data
        selling_price = entry.form.actual_selling_price.data

        if not product_id and quantity in (None, "", 0) and selling_price in (None, "", 0):
            continue

        if not product_id or quantity in (None, "") or selling_price in (None, ""):
            raise BusinessRuleError("Each sale line must include product, quantity, and selling price.")

        product = Product.query.filter_by(id=product_id, business_id=business_id).first()
        if product is None or not product.is_active:
            raise BusinessRuleError("One or more selected products are unavailable.")

        quantity_decimal = money(quantity)
        selling_price_decimal = money(selling_price)

        if quantity_decimal <= 0:
            raise BusinessRuleError(f"Quantity for '{product.name}' must be greater than zero.")

        prepared_lines.append(
            PreparedSaleLine(
                product=product,
                quantity=quantity_decimal,
                actual_selling_price=selling_price_decimal,
            )
        )

    if not prepared_lines:
        raise BusinessRuleError("Add at least one valid sale item before saving the sale.")

    return prepared_lines


def allocate_fifo_stock(product: Product, business_id: str, required_quantity: Decimal):
    """Allocate stock batches using FIFO order for a product."""

    batches = get_available_batches_for_product(product.id, business_id)
    available_quantity = sum((money(batch.quantity_remaining) for batch in batches), Decimal("0.00"))

    if available_quantity < required_quantity:
        raise InsufficientStockError(
            f"Not enough stock for '{product.name}'. Available: {available_quantity}, required: {required_quantity}."
        )

    quantity_left = required_quantity
    allocations = []

    for batch in batches:
        if quantity_left <= 0:
            break

        batch_available = money(batch.quantity_remaining)
        if batch_available <= 0:
            continue

        allocated_quantity = min(batch_available, quantity_left)
        allocations.append({"batch": batch, "quantity": allocated_quantity})
        quantity_left = money(quantity_left - allocated_quantity)

    if quantity_left > 0:
        raise InsufficientStockError(f"Could not fully allocate stock for '{product.name}'.")

    return allocations


def determine_sale_payment(payment_mode: str, total_revenue: Decimal, entered_amount_paid) -> Decimal:
    """Normalize payment behavior by selected mode."""

    entered_amount = money(entered_amount_paid or 0)

    if payment_mode == "cash":
        return total_revenue

    if payment_mode == "credit":
        if entered_amount > 0:
            raise BusinessRuleError("Credit sales must start with zero payment. Use partial mode for upfront cash.")
        return Decimal("0.00")

    if payment_mode == "partial":
        if entered_amount <= 0 or entered_amount >= total_revenue:
            raise BusinessRuleError("Partial payment must be greater than zero and less than the sale total.")
        return entered_amount

    raise BusinessRuleError("Unsupported payment mode.")


def create_sale(*, form, business_id: str, actor) -> Sale:
    """Create a sale, deduct stock, and compute profit figures in one transaction."""

    customer_id = (form.customer_id.data or "").strip()
    customer = None
    if customer_id:
        customer = Customer.query.filter_by(id=customer_id, business_id=business_id).first()
        if customer is None:
            raise BusinessRuleError("Selected customer does not belong to this business.")

    prepared_lines = prepare_sale_lines(form, business_id)

    if form.payment_mode.data in {"credit", "partial"} and customer is None:
        raise BusinessRuleError("Customer selection is required for credit or partial sales.")

    sale = Sale(
        business_id=business_id,
        customer=customer,
        created_by=actor,
        sale_datetime=form.sale_datetime.data or datetime.utcnow(),
        payment_mode=form.payment_mode.data,
        notes=(form.notes.data or "").strip() or None,
    )
    db.session.add(sale)
    db.session.flush()

    total_revenue = Decimal("0.00")
    total_cost = Decimal("0.00")

    for line in prepared_lines:
        allocations = allocate_fifo_stock(line.product, business_id, line.quantity)

        # One user-entered sale line may be split into multiple FIFO-backed SaleItem rows.
        for allocation in allocations:
            batch = allocation["batch"]
            quantity = money(allocation["quantity"])
            subtotal = money(line.actual_selling_price * quantity)
            item_cost_total = money(batch.cost_price * quantity)
            item_profit = money(subtotal - item_cost_total)

            sale_item = SaleItem(
                sale=sale,
                business_id=business_id,
                product=line.product,
                stock_batch=batch,
                quantity=quantity,
                cost_price=money(batch.cost_price),
                actual_selling_price=money(line.actual_selling_price),
                subtotal=subtotal,
                item_profit=item_profit,
            )
            db.session.add(sale_item)
            batch.quantity_remaining = money(batch.quantity_remaining - quantity)

            total_revenue += subtotal
            total_cost += item_cost_total

    sale.total_revenue = money(total_revenue)
    sale.total_cost = money(total_cost)
    sale.total_gross_profit = money(sale.total_revenue - sale.total_cost)
    sale.amount_paid = determine_sale_payment(
        sale.payment_mode,
        sale.total_revenue,
        form.amount_paid.data,
    )
    sale.refresh_payment_status()
    sale.total_realized_profit, sale.total_unrealized_profit = calculate_profit_realization(
        sale.total_revenue,
        sale.total_gross_profit,
        sale.amount_paid,
    )
    if customer is not None:
        from app.services.credit_service import sync_customer_outstanding_balance

        sync_customer_outstanding_balance(customer)

    record_audit_event(
        action="sale_create",
        description=f"Sale '{sale.id}' created with total revenue {sale.total_revenue}.",
        entity_type="sale",
        entity_id=sale.id,
        user=actor,
        business=actor.business,
    )
    return sale
