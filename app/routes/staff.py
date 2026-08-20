"""Staff routes for operational access."""

from __future__ import annotations

from flask import Blueprint, flash, render_template, request, redirect, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import SaleForm
from app.models import Customer, Product, Sale
from app.services import (
    BusinessRuleError,
    create_sale,
    get_inventory_overview,
    get_subscription_summary,
    get_staff_dashboard_analytics,
)
from app.utils import get_tenant_record_or_404, staff_required, subscription_operation_required


staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


def _current_business_id() -> str:
    return current_user.business_id


def _customer_choices():
    customers = (
        Customer.query.filter_by(business_id=_current_business_id(), is_active=True)
        .order_by(Customer.name.asc())
        .all()
    )
    return [("", "Walk-in customer")] + [(customer.id, customer.name) for customer in customers]


def _product_choices():
    products = (
        Product.query.filter_by(business_id=_current_business_id(), is_active=True)
        .order_by(Product.name.asc())
        .all()
    )
    return [
        (
            product.id,
            f"{product.name} ({product.current_stock_quantity} {product.unit_type})",
        )
        for product in products
    ]


def _prepare_sale_form(form: SaleForm) -> None:
    form.customer_id.choices = _customer_choices()
    product_choices = [("", "Select product")] + _product_choices()
    for entry in form.items:
        entry.form.product_id.choices = product_choices


@staff_bp.get("/dashboard")
@staff_required
def dashboard():
    """Render the improved staff dashboard."""

    dashboard_data = get_staff_dashboard_analytics(_current_business_id())
    return render_template(
        "staff/dashboard.html",
        business=current_user.business,
        dashboard_data=dashboard_data,
        subscription_summary=get_subscription_summary(current_user.business),
    )


@staff_bp.get("/products")
@staff_required
def products():
    """List active products for operational reference."""

    search = request.args.get("q", "").strip()
    rows = [
        row for row in get_inventory_overview(_current_business_id(), search=search or None)
        if row["product"].is_active
    ]
    return render_template("staff/products_list.html", rows=rows, search=search)


@staff_bp.get("/customers")
@staff_required
def customers():
    """List active customers for operational lookup."""

    search = request.args.get("q", "").strip()
    query = Customer.query.filter_by(business_id=_current_business_id(), is_active=True).order_by(Customer.name.asc())
    if search:
        query = query.filter(Customer.name.ilike(f"%{search}%"))
    return render_template("staff/customers_list.html", customers=query.all(), search=search)


@staff_bp.route("/sales")
@staff_required
def sales():
    """List sales created within the tenant."""

    payment_status = request.args.get("payment_status", "all")
    query = Sale.query.filter_by(business_id=_current_business_id()).order_by(Sale.sale_datetime.desc())
    if payment_status != "all":
        query = query.filter_by(payment_status=payment_status)
    return render_template(
        "owner/sales_list.html",
        sales=query.all(),
        payment_status=payment_status,
        panel_prefix="staff",
    )


@staff_bp.route("/sales/new", methods=["GET", "POST"])
@staff_required
@subscription_operation_required("new sales")
def sale_new():
    """Create a sale as staff."""

    form = SaleForm()
    _prepare_sale_form(form)
    if form.validate_on_submit():
        try:
            sale = create_sale(form=form, business_id=_current_business_id(), actor=current_user)
            db.session.commit()
            flash("Sale recorded successfully.", "success")
            return redirect(url_for("staff.sale_detail", sale_id=sale.id))
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception:
            db.session.rollback()
            raise
    return render_template("owner/sale_form.html", form=form, panel_prefix="staff", page_title="New Sale")


@staff_bp.route("/sales/<sale_id>")
@staff_required
def sale_detail(sale_id: str):
    """View sale details as staff."""

    sale = get_tenant_record_or_404(Sale, sale_id)
    return render_template("owner/sale_detail.html", sale=sale, panel_prefix="staff")
