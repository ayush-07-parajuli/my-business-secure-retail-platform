"""Inventory, category, and product business logic."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, or_

from app.extensions import db
from app.models import Category, Product, StockBatch
from app.models.base import utc_now
from app.services.auth_service import record_audit_event
from app.services.exceptions import BusinessRuleError


DECIMAL_ZERO = Decimal("0.00")


def as_decimal(value) -> Decimal:
    """Normalize numeric input to Decimal."""

    if value is None:
        return DECIMAL_ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def generate_batch_code(product_name: str) -> str:
    """Generate a readable batch code when none is provided."""

    timestamp = utc_now().strftime("%Y%m%d")
    product_token = "".join(ch for ch in product_name.upper() if ch.isalnum())[:4] or "ITEM"
    return f"{product_token}-{timestamp}-{uuid4().hex[:6].upper()}"


def normalize_date_input(value):
    """Convert DateField values into datetimes for DateTime model columns."""

    if value is None or isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min)


def get_category_query(business_id: str, *, include_inactive: bool = True):
    """Return a tenant-scoped category query."""

    query = Category.query.filter_by(business_id=business_id).order_by(Category.name.asc())
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return query


def get_product_query(business_id: str, *, include_inactive: bool = True):
    """Return a tenant-scoped product query."""

    query = Product.query.filter_by(business_id=business_id).order_by(Product.name.asc())
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return query


def create_category(*, business_id: str, name: str, description: str | None, is_active: bool, actor) -> Category:
    """Create a new category for a business."""

    category = Category(
        business_id=business_id,
        name=name.strip(),
        description=(description or "").strip() or None,
        is_active=is_active,
    )
    db.session.add(category)
    db.session.flush()
    record_audit_event(
        action="category_create",
        description=f"Category '{category.name}' created.",
        entity_type="category",
        entity_id=category.id,
        user=actor,
        business=actor.business,
    )
    return category


def update_category(category: Category, *, name: str, description: str | None, is_active: bool, actor) -> Category:
    """Update an existing category."""

    category.name = name.strip()
    category.description = (description or "").strip() or None
    category.is_active = is_active
    record_audit_event(
        action="category_update",
        description=f"Category '{category.name}' updated.",
        entity_type="category",
        entity_id=category.id,
        user=actor,
        business=actor.business,
    )
    return category


def create_product(
    *,
    business_id: str,
    category_id: str | None,
    name: str,
    sku: str | None,
    unit_type: str,
    default_selling_price,
    min_stock_level,
    shelf_life_days: int | None,
    description: str | None,
    image_path: str | None,
    is_active: bool,
    actor,
) -> Product:
    """Create a product."""

    product = Product(
        business_id=business_id,
        category_id=category_id or None,
        name=name.strip(),
        sku=(sku or "").strip() or None,
        unit_type=unit_type,
        default_selling_price=as_decimal(default_selling_price),
        min_stock_level=as_decimal(min_stock_level),
        shelf_life_days=shelf_life_days or None,
        description=(description or "").strip() or None,
        image_path=(image_path or "").strip() or None,
        is_active=is_active,
    )
    db.session.add(product)
    db.session.flush()
    record_audit_event(
        action="product_create",
        description=f"Product '{product.name}' created.",
        entity_type="product",
        entity_id=product.id,
        user=actor,
        business=actor.business,
    )
    return product


def update_product(
    product: Product,
    *,
    category_id: str | None,
    name: str,
    sku: str | None,
    unit_type: str,
    default_selling_price,
    min_stock_level,
    shelf_life_days: int | None,
    description: str | None,
    image_path: str | None,
    is_active: bool,
    actor,
) -> Product:
    """Update a product."""

    product.category_id = category_id or None
    product.name = name.strip()
    product.sku = (sku or "").strip() or None
    product.unit_type = unit_type
    product.default_selling_price = as_decimal(default_selling_price)
    product.min_stock_level = as_decimal(min_stock_level)
    product.shelf_life_days = shelf_life_days or None
    product.description = (description or "").strip() or None
    product.image_path = (image_path or "").strip() or None
    product.is_active = is_active
    record_audit_event(
        action="product_update",
        description=f"Product '{product.name}' updated.",
        entity_type="product",
        entity_id=product.id,
        user=actor,
        business=actor.business,
    )
    return product


def create_stock_batch(
    *,
    business_id: str,
    product: Product,
    batch_code: str | None,
    quantity_added,
    cost_price,
    intended_selling_price,
    restock_date,
    expiry_date,
    supplier_name: str,
    supplier_contact: str | None,
    notes: str | None,
    actor,
) -> StockBatch:
    """Create a restock batch."""

    normalized_quantity = as_decimal(quantity_added)
    normalized_cost = as_decimal(cost_price)
    normalized_selling_price = as_decimal(intended_selling_price)
    if normalized_quantity <= 0:
        raise BusinessRuleError("Quantity added must be greater than zero.")
    if normalized_cost < 0 or normalized_selling_price < 0:
        raise BusinessRuleError("Cost and selling prices cannot be negative.")

    batch = StockBatch(
        business_id=business_id,
        product=product,
        batch_code=(batch_code or "").strip() or generate_batch_code(product.name),
        quantity_added=normalized_quantity,
        quantity_remaining=normalized_quantity,
        cost_price=normalized_cost,
        intended_selling_price=normalized_selling_price,
        restock_date=normalize_date_input(restock_date),
        expiry_date=normalize_date_input(expiry_date),
        supplier_name=supplier_name.strip(),
        supplier_contact=(supplier_contact or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    db.session.add(batch)
    db.session.flush()
    record_audit_event(
        action="stock_restock",
        description=f"Restocked '{product.name}' with batch '{batch.batch_code}'.",
        entity_type="stock_batch",
        entity_id=batch.id,
        user=actor,
        business=actor.business,
    )
    return batch


def update_stock_batch(
    batch: StockBatch,
    *,
    product: Product,
    batch_code: str | None,
    quantity_added,
    quantity_remaining,
    cost_price,
    intended_selling_price,
    restock_date,
    expiry_date,
    supplier_name: str,
    supplier_contact: str | None,
    notes: str | None,
    actor,
) -> StockBatch:
    """Update a stock batch carefully without violating remaining quantity rules."""

    normalized_quantity_added = as_decimal(quantity_added)
    normalized_quantity_remaining = as_decimal(quantity_remaining)
    normalized_cost = as_decimal(cost_price)
    normalized_selling_price = as_decimal(intended_selling_price)
    if normalized_quantity_added <= 0:
        raise BusinessRuleError("Quantity added must be greater than zero.")
    if normalized_quantity_remaining < 0:
        raise BusinessRuleError("Quantity remaining cannot be negative.")
    if normalized_quantity_remaining > normalized_quantity_added:
        raise BusinessRuleError("Quantity remaining cannot exceed quantity added.")
    if normalized_cost < 0 or normalized_selling_price < 0:
        raise BusinessRuleError("Cost and selling prices cannot be negative.")

    batch.product = product
    batch.batch_code = (batch_code or "").strip() or batch.batch_code or generate_batch_code(product.name)
    batch.quantity_added = normalized_quantity_added
    batch.quantity_remaining = normalized_quantity_remaining
    batch.cost_price = normalized_cost
    batch.intended_selling_price = normalized_selling_price
    batch.restock_date = normalize_date_input(restock_date)
    batch.expiry_date = normalize_date_input(expiry_date)
    batch.supplier_name = supplier_name.strip()
    batch.supplier_contact = (supplier_contact or "").strip() or None
    batch.notes = (notes or "").strip() or None
    record_audit_event(
        action="stock_batch_update",
        description=f"Updated batch '{batch.batch_code}' for '{product.name}'.",
        entity_type="stock_batch",
        entity_id=batch.id,
        user=actor,
        business=actor.business,
    )
    return batch


def get_available_batches_for_product(product_id: str, business_id: str, *, include_expired: bool = False):
    """Return sale-eligible FIFO batches for a product."""

    query = StockBatch.query.filter_by(
        business_id=business_id,
        product_id=product_id,
    ).filter(StockBatch.quantity_remaining > 0).order_by(
        StockBatch.restock_date.asc(),
        StockBatch.created_at.asc(),
    )

    if not include_expired:
        today = utc_now().date()
        query = query.filter(
            or_(
                StockBatch.expiry_date.is_(None),
                func.date(StockBatch.expiry_date) >= today,
            )
        )

    return query.all()


def get_product_stock_summary(product: Product) -> dict:
    """Return aggregate stock metrics for a product."""

    total_quantity = sum((as_decimal(batch.quantity_remaining) for batch in product.stock_batches), DECIMAL_ZERO)
    stock_value = sum(
        (as_decimal(batch.quantity_remaining) * as_decimal(batch.cost_price) for batch in product.stock_batches),
        DECIMAL_ZERO,
    )
    near_expiry_count = sum(1 for batch in product.stock_batches if batch.is_near_expiry())
    expired_count = sum(1 for batch in product.stock_batches if batch.is_expired)
    return {
        "total_quantity": total_quantity,
        "stock_value": stock_value,
        "near_expiry_count": near_expiry_count,
        "expired_count": expired_count,
        "low_stock": total_quantity <= as_decimal(product.min_stock_level),
    }


def get_inventory_overview(business_id: str, *, search: str | None = None):
    """Return products with aggregate stock data for overview tables."""

    query = Product.query.filter_by(business_id=business_id).order_by(Product.name.asc())
    if search:
        like_term = f"%{search.strip()}%"
        query = query.filter(
            or_(Product.name.ilike(like_term), Product.sku.ilike(like_term))
        )

    rows = []
    for product in query.all():
        summary = get_product_stock_summary(product)
        rows.append({"product": product, **summary})
    return rows


def get_low_stock_products(business_id: str):
    """Return products at or below minimum stock levels."""

    return [row for row in get_inventory_overview(business_id) if row["low_stock"]]


def get_near_expiry_batches(business_id: str, *, days: int = 7):
    """Return near-expiry stock batches for reporting."""

    batches = (
        StockBatch.query.filter_by(business_id=business_id)
        .filter(StockBatch.quantity_remaining > 0)
        .order_by(StockBatch.expiry_date.asc())
        .all()
    )
    return [batch for batch in batches if batch.is_near_expiry(days)]


def get_expired_batches(business_id: str):
    """Return expired stock batches that still hold quantity."""

    batches = (
        StockBatch.query.filter_by(business_id=business_id)
        .filter(StockBatch.quantity_remaining > 0)
        .order_by(StockBatch.expiry_date.asc())
        .all()
    )
    return [batch for batch in batches if batch.is_expired]


def get_total_remaining_stock_value(business_id: str) -> Decimal:
    """Return the remaining inventory valuation at cost."""

    return sum(
        (
            as_decimal(batch.quantity_remaining) * as_decimal(batch.cost_price)
            for batch in StockBatch.query.filter_by(business_id=business_id).all()
        ),
        DECIMAL_ZERO,
    )
