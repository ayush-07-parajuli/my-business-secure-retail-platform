"""Business owner routes for core POS modules."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from app.extensions import db
from app.forms import (
    BusinessSettingsForm,
    CategoryForm,
    CustomerForm,
    ProductForm,
    RepaymentForm,
    RestockForm,
    SaleForm,
    SubscriptionPaymentForm,
)
from app.models import Category, Customer, Product, Repayment, Sale, SaleItem, StockBatch
from app.services import (
    BusinessRuleError,
    build_csv_response,
    create_category,
    create_product,
    create_sale,
    create_stock_batch,
    get_credit_report_data,
    get_credit_sales_query,
    get_credit_summary,
    get_customer_ledgers_report_data,
    get_customer_credit_sales,
    get_customer_repayments,
    get_expired_batches,
    get_inventory_overview,
    get_inventory_report_data,
    get_low_stock_products,
    get_near_expiry_batches,
    get_owner_dashboard_analytics,
    get_profit_report_data,
    get_product_query,
    get_product_stock_summary,
    get_sales_report_data,
    get_business_subscription_payments,
    get_subscription_summary,
    get_total_remaining_stock_value,
    parse_optional_date,
    record_audit_event,
    record_repayment,
    submit_subscription_payment,
    update_category,
    update_product,
    update_stock_batch,
)
from app.utils import get_tenant_record_or_404, owner_required, subscription_operation_required


owner_bp = Blueprint("owner", __name__, url_prefix="/owner")


def _current_business_id() -> str:
    return current_user.business_id


def _current_business():
    return current_user.business


def _near_expiry_days() -> int:
    business = _current_business()
    return business.near_expiry_threshold_days if business and business.near_expiry_threshold_days else 7


def _report_dates():
    return (
        request.args.get("period", "all"),
        parse_optional_date(request.args.get("start_date")),
        parse_optional_date(request.args.get("end_date")),
    )


def _category_choices(*, include_blank: bool = True, include_inactive: bool = False):
    query = Category.query.filter_by(business_id=_current_business_id()).order_by(Category.name.asc())
    if not include_inactive:
        query = query.filter_by(is_active=True)
    categories = query.all()
    choices = [("", "Uncategorized")] if include_blank else []
    choices.extend((category.id, category.name) for category in categories)
    return choices


def _product_choices(*, include_inactive: bool = False):
    products = get_product_query(_current_business_id(), include_inactive=include_inactive).all()
    return [
        (
            product.id,
            f"{product.name} ({product.current_stock_quantity} {product.unit_type})",
        )
        for product in products
    ]


def _customer_choices():
    customers = (
        Customer.query.filter_by(business_id=_current_business_id(), is_active=True)
        .order_by(Customer.name.asc())
        .all()
    )
    return [("", "Walk-in customer")] + [(customer.id, customer.name) for customer in customers]


def _prepare_product_form(form: ProductForm, *, include_inactive_categories: bool = False) -> None:
    form.category_id.choices = _category_choices(include_inactive=include_inactive_categories)


def _prepare_restock_form(form: RestockForm, *, include_inactive_products: bool = False) -> None:
    form.product_id.choices = _product_choices(include_inactive=include_inactive_products)


def _prepare_sale_form(form: SaleForm) -> None:
    product_choices = [("", "Select product")] + _product_choices(include_inactive=False)
    form.customer_id.choices = _customer_choices()
    for entry in form.items:
        entry.form.product_id.choices = product_choices


def _ensure_unique_category_name(name: str, *, category_id: str | None = None) -> bool:
    query = Category.query.filter_by(business_id=_current_business_id(), name=name.strip())
    if category_id:
        query = query.filter(Category.id != category_id)
    return not db.session.query(query.exists()).scalar()


def _ensure_unique_product_sku(sku: str | None, *, product_id: str | None = None) -> bool:
    if not sku:
        return True
    query = Product.query.filter_by(business_id=_current_business_id(), sku=sku.strip())
    if product_id:
        query = query.filter(Product.id != product_id)
    return not db.session.query(query.exists()).scalar()


@owner_bp.get("/dashboard")
@owner_required
def dashboard():
    """Render the upgraded owner dashboard."""

    period = request.args.get("period", "month")
    subscription_summary = get_subscription_summary(_current_business())
    dashboard_data = get_owner_dashboard_analytics(
        _current_business_id(),
        period=period,
        near_expiry_days=_near_expiry_days(),
    )
    return render_template(
        "owner/dashboard.html",
        business=_current_business(),
        dashboard_data=dashboard_data,
        subscription_summary=subscription_summary,
    )


@owner_bp.route("/categories")
@owner_required
def categories():
    """List categories for the current tenant."""

    search = request.args.get("q", "").strip()
    query = Category.query.filter_by(business_id=_current_business_id()).order_by(Category.name.asc())
    if search:
        query = query.filter(Category.name.ilike(f"%{search}%"))
    return render_template(
        "owner/categories_list.html",
        categories=query.all(),
        search=search,
    )


@owner_bp.route("/categories/new", methods=["GET", "POST"])
@owner_required
def category_new():
    """Create a category."""

    form = CategoryForm()
    if form.validate_on_submit():
        if not _ensure_unique_category_name(form.name.data):
            form.name.errors.append("This category name already exists in your business.")
        else:
            try:
                create_category(
                    business_id=_current_business_id(),
                    name=form.name.data,
                    description=form.description.data,
                    is_active=form.is_active.data,
                    actor=current_user,
                )
                db.session.commit()
                flash("Category created successfully.", "success")
                return redirect(url_for("owner.categories"))
            except Exception:
                db.session.rollback()
                raise
    return render_template("owner/category_form.html", form=form, page_title="Add Category")


@owner_bp.route("/categories/<category_id>/edit", methods=["GET", "POST"])
@owner_required
def category_edit(category_id: str):
    """Edit a category."""

    category = get_tenant_record_or_404(Category, category_id)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        if not _ensure_unique_category_name(form.name.data, category_id=category.id):
            form.name.errors.append("This category name already exists in your business.")
        else:
            try:
                update_category(
                    category,
                    name=form.name.data,
                    description=form.description.data,
                    is_active=form.is_active.data,
                    actor=current_user,
                )
                db.session.commit()
                flash("Category updated successfully.", "success")
                return redirect(url_for("owner.categories"))
            except Exception:
                db.session.rollback()
                raise
    return render_template("owner/category_form.html", form=form, page_title="Edit Category", category=category)


@owner_bp.route("/products")
@owner_required
def products():
    """List products with stock summaries."""

    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    rows = get_inventory_overview(_current_business_id(), search=search or None)
    if status == "active":
        rows = [row for row in rows if row["product"].is_active]
    elif status == "inactive":
        rows = [row for row in rows if not row["product"].is_active]

    return render_template(
        "owner/products_list.html",
        rows=rows,
        search=search,
        status=status,
    )


@owner_bp.route("/products/new", methods=["GET", "POST"])
@owner_required
def product_new():
    """Create a product."""

    form = ProductForm()
    _prepare_product_form(form, include_inactive_categories=False)
    if form.validate_on_submit():
        if not _ensure_unique_product_sku(form.sku.data):
            form.sku.errors.append("This SKU already exists in your business.")
        else:
            try:
                create_product(
                    business_id=_current_business_id(),
                    category_id=form.category_id.data,
                    name=form.name.data,
                    sku=form.sku.data,
                    unit_type=form.unit_type.data,
                    default_selling_price=form.default_selling_price.data,
                    min_stock_level=form.min_stock_level.data,
                    shelf_life_days=form.shelf_life_days.data,
                    description=form.description.data,
                    image_path=form.image_path.data,
                    is_active=form.is_active.data,
                    actor=current_user,
                )
                db.session.commit()
                flash("Product created successfully.", "success")
                return redirect(url_for("owner.products"))
            except Exception:
                db.session.rollback()
                raise
    return render_template("owner/product_form.html", form=form, page_title="Add Product")


@owner_bp.route("/products/<product_id>")
@owner_required
def product_detail(product_id: str):
    """View a product and its stock/sales summary."""

    product = get_tenant_record_or_404(Product, product_id)
    summary = get_product_stock_summary(product)
    batches = (
        StockBatch.query.filter_by(business_id=_current_business_id(), product_id=product.id)
        .order_by(StockBatch.restock_date.desc())
        .all()
    )
    recent_sale_items = (
        SaleItem.query.filter_by(business_id=_current_business_id(), product_id=product.id)
        .order_by(SaleItem.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "owner/product_detail.html",
        product=product,
        summary=summary,
        batches=batches,
        recent_sale_items=recent_sale_items,
    )


@owner_bp.route("/products/<product_id>/edit", methods=["GET", "POST"])
@owner_required
def product_edit(product_id: str):
    """Edit a product."""

    product = get_tenant_record_or_404(Product, product_id)
    form = ProductForm(obj=product)
    _prepare_product_form(form, include_inactive_categories=True)
    if request.method == "GET":
        form.category_id.data = product.category_id or ""
    if form.validate_on_submit():
        if not _ensure_unique_product_sku(form.sku.data, product_id=product.id):
            form.sku.errors.append("This SKU already exists in your business.")
        else:
            try:
                update_product(
                    product,
                    category_id=form.category_id.data,
                    name=form.name.data,
                    sku=form.sku.data,
                    unit_type=form.unit_type.data,
                    default_selling_price=form.default_selling_price.data,
                    min_stock_level=form.min_stock_level.data,
                    shelf_life_days=form.shelf_life_days.data,
                    description=form.description.data,
                    image_path=form.image_path.data,
                    is_active=form.is_active.data,
                    actor=current_user,
                )
                db.session.commit()
                flash("Product updated successfully.", "success")
                return redirect(url_for("owner.product_detail", product_id=product.id))
            except Exception:
                db.session.rollback()
                raise
    return render_template("owner/product_form.html", form=form, page_title="Edit Product", product=product)


@owner_bp.route("/products/<product_id>/batches")
@owner_required
def product_batches(product_id: str):
    """List stock batches for a single product."""

    product = get_tenant_record_or_404(Product, product_id)
    batches = (
        StockBatch.query.filter_by(business_id=_current_business_id(), product_id=product.id)
        .order_by(StockBatch.restock_date.desc())
        .all()
    )
    return render_template("owner/product_batches.html", product=product, batches=batches)


@owner_bp.route("/inventory")
@owner_required
def inventory():
    """Inventory overview with product stock summaries."""

    search = request.args.get("q", "").strip()
    rows = get_inventory_overview(_current_business_id(), search=search or None)
    recent_batches = (
        StockBatch.query.filter_by(business_id=_current_business_id())
        .order_by(StockBatch.restock_date.desc())
        .limit(12)
        .all()
    )
    return render_template(
        "owner/inventory_overview.html",
        rows=rows,
        recent_batches=recent_batches,
        search=search,
        total_stock_value=get_total_remaining_stock_value(_current_business_id()),
    )


@owner_bp.route("/inventory/restock", methods=["GET", "POST"])
@owner_required
@subscription_operation_required("restocking inventory")
def inventory_restock():
    """Create a stock batch."""

    form = RestockForm()
    _prepare_restock_form(form, include_inactive_products=False)
    if form.validate_on_submit():
        product = get_tenant_record_or_404(Product, form.product_id.data)
        try:
            batch = create_stock_batch(
                business_id=_current_business_id(),
                product=product,
                batch_code=form.batch_code.data,
                quantity_added=form.quantity_added.data,
                cost_price=form.cost_price.data,
                intended_selling_price=form.intended_selling_price.data,
                restock_date=form.restock_date.data,
                expiry_date=form.expiry_date.data,
                supplier_name=form.supplier_name.data,
                supplier_contact=form.supplier_contact.data,
                notes=form.notes.data,
                actor=current_user,
            )
            db.session.commit()
            flash("Stock batch added successfully.", "success")
            return redirect(url_for("owner.batch_detail", batch_id=batch.id))
        except Exception:
            db.session.rollback()
            raise
    return render_template("owner/restock_form.html", form=form, page_title="Add Stock Batch")


@owner_bp.route("/inventory/batches/<batch_id>")
@owner_required
def batch_detail(batch_id: str):
    """View a stock batch."""

    batch = get_tenant_record_or_404(StockBatch, batch_id)
    return render_template("owner/batch_detail.html", batch=batch)


@owner_bp.route("/inventory/batches/<batch_id>/edit", methods=["GET", "POST"])
@owner_required
def batch_edit(batch_id: str):
    """Edit a stock batch."""

    batch = get_tenant_record_or_404(StockBatch, batch_id)
    form = RestockForm(obj=batch)
    _prepare_restock_form(form, include_inactive_products=True)
    if request.method == "GET":
        form.product_id.data = batch.product_id
        form.restock_date.data = batch.restock_date.date() if batch.restock_date else None
        form.expiry_date.data = batch.expiry_date.date() if batch.expiry_date else None
    if form.validate_on_submit():
        if batch.quantity_remaining != batch.quantity_added and form.quantity_added.data != batch.quantity_added:
            flash(
                "Quantity added cannot be changed after stock from this batch has already been sold.",
                "warning",
            )
            return render_template(
                "owner/restock_form.html",
                form=form,
                page_title="Edit Stock Batch",
                batch=batch,
            )
        try:
            new_quantity_remaining = (
                form.quantity_added.data
                if batch.quantity_added == batch.quantity_remaining
                else batch.quantity_remaining
            )
            update_stock_batch(
                batch,
                product=get_tenant_record_or_404(Product, form.product_id.data),
                batch_code=form.batch_code.data,
                quantity_added=form.quantity_added.data,
                quantity_remaining=new_quantity_remaining,
                cost_price=form.cost_price.data,
                intended_selling_price=form.intended_selling_price.data,
                restock_date=form.restock_date.data,
                expiry_date=form.expiry_date.data,
                supplier_name=form.supplier_name.data,
                supplier_contact=form.supplier_contact.data,
                notes=form.notes.data,
                actor=current_user,
            )
            db.session.commit()
            flash("Stock batch updated successfully.", "success")
            return redirect(url_for("owner.batch_detail", batch_id=batch.id))
        except Exception:
            db.session.rollback()
            raise
    return render_template("owner/restock_form.html", form=form, page_title="Edit Stock Batch", batch=batch)


@owner_bp.route("/customers")
@owner_required
def customers():
    """List customers."""

    search = request.args.get("q", "").strip()
    query = Customer.query.filter_by(business_id=_current_business_id()).order_by(Customer.name.asc())
    if search:
        query = query.filter(
            or_(
                Customer.name.ilike(f"%{search}%"),
                Customer.phone.ilike(f"%{search}%"),
            )
        )
    return render_template(
        "owner/customers_list.html",
        customers=query.all(),
        search=search,
    )


@owner_bp.route("/customers/new", methods=["GET", "POST"])
@owner_required
def customer_new():
    """Create a customer."""

    form = CustomerForm()
    if form.validate_on_submit():
        customer = Customer(
            business_id=_current_business_id(),
            name=form.name.data.strip(),
            phone=(form.phone.data or "").strip() or None,
            address=(form.address.data or "").strip() or None,
            notes=(form.notes.data or "").strip() or None,
            is_active=form.is_active.data,
        )
        try:
            db.session.add(customer)
            db.session.flush()
            record_audit_event(
                action="customer_create",
                description=f"Customer '{customer.name}' created.",
                entity_type="customer",
                entity_id=customer.id,
                user=current_user,
                business=current_user.business,
            )
            db.session.commit()
            flash("Customer created successfully.", "success")
            return redirect(url_for("owner.customer_detail", customer_id=customer.id))
        except Exception:
            db.session.rollback()
            raise
    return render_template("owner/customer_form.html", form=form, page_title="Add Customer")


@owner_bp.route("/customers/<customer_id>")
@owner_required
def customer_detail(customer_id: str):
    """View customer ledger details."""

    customer = get_tenant_record_or_404(Customer, customer_id)
    credit_sales = get_customer_credit_sales(customer)
    repayments = get_customer_repayments(customer)
    customer_sales = (
        Sale.query.filter_by(business_id=_current_business_id(), customer_id=customer.id)
        .order_by(Sale.sale_datetime.desc())
        .all()
    )
    recent_sales = customer_sales[:10]
    if request.args.get("format") == "csv":
        rows = [
            [
                "sale",
                sale.sale_datetime.strftime("%Y-%m-%d %H:%M"),
                sale.total_revenue,
                sale.amount_paid,
                sale.amount_due,
                sale.payment_status,
            ]
            for sale in customer_sales
        ]
        rows.extend(
            [
                "repayment",
                repayment.payment_date.strftime("%Y-%m-%d %H:%M"),
                repayment.amount_paid,
                "",
                "",
                repayment.note or "",
            ]
            for repayment in repayments
        )
        return build_csv_response(
            filename=f"{customer.name.lower().replace(' ', '-')}-ledger.csv",
            headers=["Entry Type", "Date", "Amount", "Paid", "Due", "Notes / Status"],
            rows=rows,
        )
    return render_template(
        "owner/customer_detail.html",
        customer=customer,
        credit_sales=credit_sales,
        recent_sales=recent_sales,
        repayments=repayments,
    )


@owner_bp.route("/customers/<customer_id>/ledger")
@owner_required
def customer_ledger(customer_id: str):
    """Customer ledger route alias."""

    return redirect(url_for("owner.customer_detail", customer_id=customer_id))


@owner_bp.route("/customers/<customer_id>/edit", methods=["GET", "POST"])
@owner_required
def customer_edit(customer_id: str):
    """Edit a customer."""

    customer = get_tenant_record_or_404(Customer, customer_id)
    form = CustomerForm(obj=customer)
    if form.validate_on_submit():
        customer.name = form.name.data.strip()
        customer.phone = (form.phone.data or "").strip() or None
        customer.address = (form.address.data or "").strip() or None
        customer.notes = (form.notes.data or "").strip() or None
        customer.is_active = form.is_active.data
        try:
            record_audit_event(
                action="customer_update",
                description=f"Customer '{customer.name}' updated.",
                entity_type="customer",
                entity_id=customer.id,
                user=current_user,
                business=current_user.business,
            )
            db.session.commit()
            flash("Customer updated successfully.", "success")
            return redirect(url_for("owner.customer_detail", customer_id=customer.id))
        except Exception:
            db.session.rollback()
            raise
    return render_template("owner/customer_form.html", form=form, page_title="Edit Customer", customer=customer)


@owner_bp.route("/sales")
@owner_required
def sales():
    """List sales."""

    payment_status = request.args.get("payment_status", "all")
    query = Sale.query.filter_by(business_id=_current_business_id()).order_by(Sale.sale_datetime.desc())
    if payment_status != "all":
        query = query.filter_by(payment_status=payment_status)
    return render_template("owner/sales_list.html", sales=query.all(), payment_status=payment_status, panel_prefix="owner")


@owner_bp.route("/sales/new", methods=["GET", "POST"])
@owner_required
@subscription_operation_required("new sales")
def sale_new():
    """Create a sale."""

    form = SaleForm()
    _prepare_sale_form(form)
    if form.validate_on_submit():
        try:
            sale = create_sale(form=form, business_id=_current_business_id(), actor=current_user)
            db.session.commit()
            flash("Sale recorded successfully.", "success")
            return redirect(url_for("owner.sale_detail", sale_id=sale.id))
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception:
            db.session.rollback()
            raise
    return render_template("owner/sale_form.html", form=form, panel_prefix="owner", page_title="New Sale")


@owner_bp.route("/sales/<sale_id>")
@owner_required
def sale_detail(sale_id: str):
    """View sale details."""

    sale = get_tenant_record_or_404(Sale, sale_id)
    return render_template("owner/sale_detail.html", sale=sale, panel_prefix="owner")


@owner_bp.route("/credits")
@owner_required
def credits():
    """List outstanding credit sales."""

    credit_sales = get_credit_sales_query(_current_business_id()).all()
    summary = get_credit_summary(_current_business_id())
    return render_template("owner/credits_list.html", credit_sales=credit_sales, summary=summary)


@owner_bp.route("/credits/<sale_id>")
@owner_required
def credit_detail(sale_id: str):
    """View details for an outstanding credit sale."""

    sale = get_tenant_record_or_404(Sale, sale_id)
    return render_template("owner/credit_detail.html", sale=sale)


@owner_bp.route("/repayments")
@owner_required
def repayments():
    """List repayments."""

    repayments_query = (
        Repayment.query.filter_by(business_id=_current_business_id())
        .order_by(Repayment.payment_date.desc())
        .all()
    )
    return render_template("owner/repayments_list.html", repayments=repayments_query)


@owner_bp.route("/repayments/new/<sale_id>", methods=["GET", "POST"])
@owner_required
def repayment_new(sale_id: str):
    """Record a repayment."""

    sale = get_tenant_record_or_404(Sale, sale_id)
    form = RepaymentForm()
    if request.method == "GET":
        form.sale_id.data = sale.id
    if form.validate_on_submit():
        if form.sale_id.data != sale.id:
            flash("Repayment request did not match the selected sale.", "danger")
            return redirect(url_for("owner.sale_detail", sale_id=sale.id))
        try:
            repayment = record_repayment(
                sale=sale,
                amount_paid=form.amount_paid.data,
                payment_date=form.payment_date.data,
                note=form.note.data,
                actor=current_user,
            )
            db.session.commit()
            flash("Repayment recorded successfully.", "success")
            return redirect(url_for("owner.repayment_detail", repayment_id=repayment.id))
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("owner/repayment_form.html", form=form, sale=sale)


@owner_bp.route("/repayments/<repayment_id>")
@owner_required
def repayment_detail(repayment_id: str):
    """View a repayment."""

    repayment = get_tenant_record_or_404(Repayment, repayment_id)
    return render_template("owner/repayment_detail.html", repayment=repayment)


@owner_bp.route("/reports/sales")
@owner_required
@subscription_operation_required("sales reports")
def sales_report():
    """Render the owner sales report or export it as CSV."""

    period, start_date, end_date = _report_dates()
    payment_status = request.args.get("payment_status", "all")
    report_data = get_sales_report_data(
        _current_business_id(),
        period=period,
        start_date=start_date,
        end_date=end_date,
        payment_status=payment_status,
    )
    if request.args.get("format") == "csv":
        rows = [
            [
                sale.sale_datetime.strftime("%Y-%m-%d %H:%M"),
                sale.customer.name if sale.customer else "Walk-in",
                sale.payment_mode,
                sale.payment_status,
                sale.total_revenue,
                sale.amount_paid,
                sale.amount_due,
            ]
            for sale in report_data["sales"]
        ]
        return build_csv_response(
            filename="sales-report.csv",
            headers=["Date", "Customer", "Payment Mode", "Payment Status", "Revenue", "Paid", "Due"],
            rows=rows,
        )
    return render_template(
        "owner/report_sales.html",
        report_data=report_data,
        payment_status=payment_status,
    )


@owner_bp.route("/reports/profit")
@owner_required
@subscription_operation_required("profit reports")
def profit_report():
    """Render the owner profit report or export it as CSV."""

    period, start_date, end_date = _report_dates()
    report_data = get_profit_report_data(
        _current_business_id(),
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    if request.args.get("format") == "csv":
        rows = [
            [
                sale.sale_datetime.strftime("%Y-%m-%d %H:%M"),
                sale.customer.name if sale.customer else "Walk-in",
                sale.total_revenue,
                sale.total_gross_profit,
                sale.total_realized_profit,
                sale.total_unrealized_profit,
            ]
            for sale in report_data["sales"]
        ]
        return build_csv_response(
            filename="profit-report.csv",
            headers=[
                "Date",
                "Customer",
                "Revenue",
                "Gross Profit",
                "Realized Profit",
                "Unrealized Profit",
            ],
            rows=rows,
        )
    return render_template("owner/report_profit.html", report_data=report_data)


@owner_bp.route("/reports/credits")
@owner_required
@subscription_operation_required("credit reports")
def credit_report():
    """Render the owner credit report or export it as CSV."""

    customer_id = request.args.get("customer_id")
    report_data = get_credit_report_data(_current_business_id(), customer_id=customer_id or None)
    if request.args.get("format") == "csv":
        rows = [
            [
                sale.sale_datetime.strftime("%Y-%m-%d %H:%M"),
                sale.customer.name if sale.customer else "Walk-in",
                sale.total_revenue,
                sale.amount_paid,
                sale.amount_due,
                sale.payment_status,
            ]
            for sale in report_data["credit_sales"]
        ]
        return build_csv_response(
            filename="credit-report.csv",
            headers=["Date", "Customer", "Revenue", "Paid", "Due", "Status"],
            rows=rows,
        )
    return render_template(
        "owner/report_credits.html",
        report_data=report_data,
        customers=Customer.query.filter_by(business_id=_current_business_id()).order_by(Customer.name.asc()).all(),
        selected_customer_id=customer_id or "",
    )


@owner_bp.route("/reports/inventory")
@owner_required
@subscription_operation_required("inventory reports")
def inventory_report():
    """Render the owner inventory report or export it as CSV."""

    search = request.args.get("q", "").strip()
    report_data = get_inventory_report_data(
        _current_business_id(),
        search=search or None,
        near_expiry_days=_near_expiry_days(),
    )
    if request.args.get("format") == "csv":
        rows = [
            [
                row["product"].name,
                row["product"].category.name if row["product"].category else "",
                row["total_quantity"],
                row["product"].unit_type,
                row["product"].min_stock_level,
                row["stock_value"],
                "low_stock" if row["low_stock"] else "healthy",
            ]
            for row in report_data["rows"]
        ]
        return build_csv_response(
            filename="inventory-report.csv",
            headers=["Product", "Category", "Stock", "Unit", "Min Stock", "Stock Value", "Status"],
            rows=rows,
        )
    return render_template(
        "owner/report_inventory.html",
        report_data=report_data,
        search=search,
    )


@owner_bp.route("/reports/customer-ledgers")
@owner_required
@subscription_operation_required("customer ledger reports")
def customer_ledgers_report():
    """Render a customer ledger summary report or export it as CSV."""

    report_data = get_customer_ledgers_report_data(_current_business_id())
    if request.args.get("format") == "csv":
        rows = [
            [
                customer.name,
                customer.phone or "",
                customer.outstanding_balance,
                "active" if customer.is_active else "inactive",
            ]
            for customer in report_data["customers"]
        ]
        return build_csv_response(
            filename="customer-ledgers.csv",
            headers=["Customer", "Phone", "Outstanding Balance", "Status"],
            rows=rows,
        )
    return render_template("owner/report_customer_ledgers.html", report_data=report_data)


@owner_bp.route("/reports/low-stock")
@owner_required
@subscription_operation_required("low-stock reports")
def report_low_stock():
    """List low-stock products."""

    rows = get_low_stock_products(_current_business_id())
    if request.args.get("format") == "csv":
        return build_csv_response(
            filename="low-stock-report.csv",
            headers=["Product", "Current Stock", "Unit", "Minimum Stock"],
            rows=[
                [
                    row["product"].name,
                    row["total_quantity"],
                    row["product"].unit_type,
                    row["product"].min_stock_level,
                ]
                for row in rows
            ],
        )
    return render_template("owner/report_low_stock.html", rows=rows)


@owner_bp.route("/reports/near-expiry")
@owner_required
@subscription_operation_required("near-expiry reports")
def report_near_expiry():
    """List near-expiry batches."""

    batches = get_near_expiry_batches(_current_business_id(), days=_near_expiry_days())
    if request.args.get("format") == "csv":
        return build_csv_response(
            filename="near-expiry-report.csv",
            headers=["Batch", "Product", "Expiry Date", "Remaining Quantity", "Supplier"],
            rows=[
                [
                    batch.batch_code or batch.id,
                    batch.product.name,
                    batch.expiry_date.strftime("%Y-%m-%d") if batch.expiry_date else "",
                    batch.quantity_remaining,
                    batch.supplier_name or "",
                ]
                for batch in batches
            ],
        )
    return render_template("owner/report_near_expiry.html", batches=batches)


@owner_bp.route("/reports/expired")
@owner_required
@subscription_operation_required("expired-stock reports")
def report_expired():
    """List expired batches."""

    batches = get_expired_batches(_current_business_id())
    if request.args.get("format") == "csv":
        return build_csv_response(
            filename="expired-stock-report.csv",
            headers=["Batch", "Product", "Expiry Date", "Remaining Quantity", "Supplier"],
            rows=[
                [
                    batch.batch_code or batch.id,
                    batch.product.name,
                    batch.expiry_date.strftime("%Y-%m-%d") if batch.expiry_date else "",
                    batch.quantity_remaining,
                    batch.supplier_name or "",
                ]
                for batch in batches
            ],
        )
    return render_template("owner/report_expired.html", batches=batches)


@owner_bp.route("/settings", methods=["GET", "POST"])
@owner_required
def settings():
    """Manage business-level tenant settings."""

    business = _current_business()
    form = BusinessSettingsForm(obj=business)
    if form.validate_on_submit():
        normalized_email = (form.email.data or "").strip().lower() or None
        if normalized_email:
            existing_business = (
                business.__class__.query
                .filter(business.__class__.email == normalized_email, business.__class__.id != business.id)
                .first()
            )
            if existing_business is not None:
                form.email.errors.append("Another business already uses that email address.")
                return render_template("owner/settings.html", form=form, business=business)

        business.business_name = form.business_name.data.strip()
        business.owner_name = form.owner_name.data.strip()
        business.phone = (form.phone.data or "").strip() or None
        business.email = normalized_email
        business.address = (form.address.data or "").strip() or None
        business.business_type = (form.business_type.data or "").strip() or None
        business.preferred_language = form.preferred_language.data
        business.near_expiry_threshold_days = form.near_expiry_threshold_days.data
        business.currency_symbol = (form.currency_symbol.data or "Rs.").strip() or "Rs."
        business.receipt_footer_note = (form.receipt_footer_note.data or "").strip() or None
        current_user.preferred_language = form.preferred_language.data
        try:
            record_audit_event(
                action="business_settings_updated",
                description=f"Business settings updated for '{business.business_name}'.",
                entity_type="business",
                entity_id=business.id,
                user=current_user,
                business=business,
            )
            db.session.commit()
            flash("Business settings updated successfully.", "success")
            return redirect(url_for("owner.settings"))
        except Exception:
            db.session.rollback()
            raise
    return render_template("owner/settings.html", form=form, business=business)


@owner_bp.get("/subscription")
@owner_required
def subscription():
    """Show the owner-facing SaaS subscription overview."""

    business = _current_business()
    return render_template(
        "owner/subscription.html",
        business=business,
        subscription_summary=get_subscription_summary(business),
        recent_payments=get_business_subscription_payments(business.id, limit=10),
    )


@owner_bp.get("/subscription/renew")
@owner_required
def subscription_renew():
    """Redirect to the manual payment submission form."""

    flash("Submit your renewal proof and our business admin team will review it.", "info")
    return redirect(url_for("owner.subscription_submit_payment"))


@owner_bp.route("/subscription/submit-payment", methods=["GET", "POST"])
@owner_required
def subscription_submit_payment():
    """Submit a manual subscription payment for company approval."""

    business = _current_business()
    form = SubscriptionPaymentForm()
    if request.method == "GET":
        form.amount_paid.data = business.monthly_fee

    if form.validate_on_submit():
        try:
            submit_subscription_payment(
                business=business,
                submitted_by=current_user,
                amount_paid=form.amount_paid.data,
                payment_method=form.payment_method.data,
                transaction_id=form.transaction_id.data,
                payment_date=form.payment_date.data,
                months_covered=form.months_covered.data,
                note=form.note.data,
                proof_path=form.proof_path.data,
            )
            db.session.commit()
            flash("Your renewal payment has been submitted for approval.", "success")
            return redirect(url_for("owner.subscription"))
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception:
            db.session.rollback()
            raise

    return render_template(
        "owner/subscription_payment_form.html",
        form=form,
        business=business,
        subscription_summary=get_subscription_summary(business),
    )
