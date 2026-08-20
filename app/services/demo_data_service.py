"""Demo-ready seed data and smoke-flow helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from werkzeug.datastructures import MultiDict

from app.extensions import db
from app.models import (
    Business,
    Category,
    Customer,
    Product,
    Repayment,
    Sale,
    StockBatch,
    SubscriptionPayment,
    User,
)
from app.models.base import utc_now
from app.services.auth_service import create_seed_users, record_audit_event, register_business_owner
from app.services.credit_service import record_repayment, sync_customer_outstanding_balance
from app.services.inventory_service import create_category, create_product, create_stock_batch
from app.services.sales_service import create_sale
from app.services.subscription_service import (
    approve_subscription_payment,
    initialize_business_subscription,
    submit_subscription_payment,
)
from config import TestingConfig


class _Field:
    """Simple stand-in for a WTForms field object."""

    def __init__(self, data):
        self.data = data


class _SaleItemEntry:
    """Simple stand-in for a nested sale item form entry."""

    def __init__(self, product_id: str, quantity, actual_selling_price):
        self.form = SimpleNamespace(
            product_id=_Field(product_id),
            quantity=_Field(quantity),
            actual_selling_price=_Field(actual_selling_price),
        )


class _SaleFormStub:
    """Minimal form-like object compatible with the sale service."""

    def __init__(self, *, customer_id: str, payment_mode: str, amount_paid, note: str, items: list[dict]):
        self.customer_id = _Field(customer_id)
        self.sale_datetime = _Field(utc_now())
        self.payment_mode = _Field(payment_mode)
        self.amount_paid = _Field(amount_paid)
        self.notes = _Field(note)
        self.items = SimpleNamespace(
            entries=[
                _SaleItemEntry(item["product_id"], item["quantity"], item["actual_selling_price"])
                for item in items
            ]
        )


def _ensure_customer(*, business_id: str, name: str, phone: str, actor) -> Customer:
    """Return an existing demo customer or create one."""

    customer = Customer.query.filter_by(business_id=business_id, phone=phone).first()
    if customer is not None:
        return customer

    customer = Customer(
        business_id=business_id,
        name=name,
        phone=phone,
        address="Kathmandu",
        notes="Demo customer profile",
        is_active=True,
    )
    db.session.add(customer)
    db.session.flush()
    record_audit_event(
        action="customer_create",
        description=f"Customer '{customer.name}' created.",
        entity_type="customer",
        entity_id=customer.id,
        user=actor,
        business=actor.business,
    )
    return customer


def _ensure_category(*, business_id: str, name: str, description: str, actor) -> Category:
    category = Category.query.filter_by(business_id=business_id, name=name).first()
    if category is not None:
        return category
    return create_category(
        business_id=business_id,
        name=name,
        description=description,
        is_active=True,
        actor=actor,
    )


def _ensure_product(
    *,
    business_id: str,
    category_id: str | None,
    name: str,
    sku: str,
    unit_type: str,
    default_selling_price,
    min_stock_level,
    shelf_life_days: int | None,
    actor,
) -> Product:
    product = Product.query.filter_by(business_id=business_id, sku=sku).first()
    if product is not None:
        return product
    return create_product(
        business_id=business_id,
        category_id=category_id,
        name=name,
        sku=sku,
        unit_type=unit_type,
        default_selling_price=default_selling_price,
        min_stock_level=min_stock_level,
        shelf_life_days=shelf_life_days,
        description=f"Demo product for {name}",
        image_path=None,
        is_active=True,
        actor=actor,
    )


def _ensure_batch(
    *,
    business_id: str,
    product: Product,
    batch_code: str,
    quantity_added,
    cost_price,
    intended_selling_price,
    supplier_name: str,
    restock_days_ago: int,
    expiry_days_from_now: int | None,
    actor,
) -> StockBatch:
    batch = StockBatch.query.filter_by(business_id=business_id, batch_code=batch_code).first()
    if batch is not None:
        return batch

    restock_date = utc_now().date() - timedelta(days=restock_days_ago)
    expiry_date = None
    if expiry_days_from_now is not None:
        expiry_date = utc_now().date() + timedelta(days=expiry_days_from_now)

    return create_stock_batch(
        business_id=business_id,
        product=product,
        batch_code=batch_code,
        quantity_added=quantity_added,
        cost_price=cost_price,
        intended_selling_price=intended_selling_price,
        restock_date=restock_date,
        expiry_date=expiry_date,
        supplier_name=supplier_name,
        supplier_contact="+9779800001111",
        notes="Demo restock batch",
        actor=actor,
    )


def create_demo_seed_data() -> dict[str, int]:
    """Populate the default development tenant with demo-ready business data."""

    create_seed_users()
    biz_admin = User.query.filter_by(email="biz@example.com").first()
    owner = User.query.filter_by(email="owner@example.com").first()
    staff = User.query.filter_by(email="staff@example.com").first()
    business = Business.query.filter_by(email="owner@example.com").first()

    if not owner or not staff or not business or not biz_admin:
        raise RuntimeError("Base seed accounts could not be created.")

    business.business_name = "My Business Demo Store"
    business.owner_name = owner.full_name
    business.business_type = "Retail Grocery"
    business.preferred_language = "en"
    business.near_expiry_threshold_days = 10
    business.currency_symbol = "Rs."
    business.preferred_currency = "NPR"
    business.receipt_footer_note = "Thank you for using My Business."
    initialize_business_subscription(business, status="active")
    business.subscription_status = "active"
    business.amount_due = 0

    staples = _ensure_category(
        business_id=business.id,
        name="Staples",
        description="Daily staple goods",
        actor=owner,
    )
    dairy = _ensure_category(
        business_id=business.id,
        name="Dairy",
        description="Milk and dairy items",
        actor=owner,
    )
    snacks = _ensure_category(
        business_id=business.id,
        name="Snacks",
        description="Fast-moving snack items",
        actor=owner,
    )

    rice = _ensure_product(
        business_id=business.id,
        category_id=staples.id,
        name="Basmati Rice 5kg",
        sku="RICE-5KG",
        unit_type="pack",
        default_selling_price="720",
        min_stock_level="6",
        shelf_life_days=180,
        actor=owner,
    )
    milk = _ensure_product(
        business_id=business.id,
        category_id=dairy.id,
        name="Fresh Milk 1L",
        sku="MILK-1L",
        unit_type="pack",
        default_selling_price="95",
        min_stock_level="12",
        shelf_life_days=7,
        actor=owner,
    )
    noodles = _ensure_product(
        business_id=business.id,
        category_id=snacks.id,
        name="Instant Noodles",
        sku="NOODLE-01",
        unit_type="pack",
        default_selling_price="25",
        min_stock_level="25",
        shelf_life_days=120,
        actor=owner,
    )

    _ensure_batch(
        business_id=business.id,
        product=rice,
        batch_code="DEMO-RICE-01",
        quantity_added="24",
        cost_price="590",
        intended_selling_price="720",
        supplier_name="Everest Suppliers",
        restock_days_ago=10,
        expiry_days_from_now=120,
        actor=owner,
    )
    _ensure_batch(
        business_id=business.id,
        product=milk,
        batch_code="DEMO-MILK-01",
        quantity_added="40",
        cost_price="70",
        intended_selling_price="95",
        supplier_name="Kathmandu Dairy",
        restock_days_ago=1,
        expiry_days_from_now=5,
        actor=owner,
    )
    _ensure_batch(
        business_id=business.id,
        product=noodles,
        batch_code="DEMO-NOODLE-01",
        quantity_added="100",
        cost_price="17",
        intended_selling_price="25",
        supplier_name="Snack Distributors",
        restock_days_ago=15,
        expiry_days_from_now=90,
        actor=owner,
    )

    customer_one = _ensure_customer(
        business_id=business.id,
        name="Anita Sharma",
        phone="+9779800002001",
        actor=owner,
    )
    customer_two = _ensure_customer(
        business_id=business.id,
        name="Bikash Karki",
        phone="+9779800002002",
        actor=owner,
    )

    cash_sale = Sale.query.filter_by(business_id=business.id, notes="DEMO: cash sale").first()
    if cash_sale is None:
        cash_sale = create_sale(
            form=_SaleFormStub(
                customer_id="",
                payment_mode="cash",
                amount_paid="0",
                note="DEMO: cash sale",
                items=[
                    {"product_id": noodles.id, "quantity": "3", "actual_selling_price": "25"},
                    {"product_id": milk.id, "quantity": "2", "actual_selling_price": "95"},
                ],
            ),
            business_id=business.id,
            actor=staff,
        )

    credit_sale = Sale.query.filter_by(business_id=business.id, notes="DEMO: credit sale").first()
    if credit_sale is None:
        credit_sale = create_sale(
            form=_SaleFormStub(
                customer_id=customer_one.id,
                payment_mode="credit",
                amount_paid="0",
                note="DEMO: credit sale",
                items=[
                    {"product_id": rice.id, "quantity": "1", "actual_selling_price": "720"},
                    {"product_id": noodles.id, "quantity": "5", "actual_selling_price": "25"},
                ],
            ),
            business_id=business.id,
            actor=owner,
        )

    partial_sale = Sale.query.filter_by(business_id=business.id, notes="DEMO: partial sale").first()
    if partial_sale is None:
        partial_sale = create_sale(
            form=_SaleFormStub(
                customer_id=customer_two.id,
                payment_mode="partial",
                amount_paid="120",
                note="DEMO: partial sale",
                items=[
                    {"product_id": milk.id, "quantity": "3", "actual_selling_price": "95"},
                ],
            ),
            business_id=business.id,
            actor=staff,
        )

    repayment = Repayment.query.filter(
        Repayment.business_id == business.id,
        Repayment.note == "DEMO: first repayment",
    ).first()
    if repayment is None and credit_sale.amount_due > 0:
        record_repayment(
            sale=credit_sale,
            amount_paid="300",
            payment_date=utc_now().date(),
            note="DEMO: first repayment",
            actor=owner,
        )

    approved_subscription_payment = SubscriptionPayment.query.filter(
        SubscriptionPayment.business_id == business.id,
        SubscriptionPayment.note == "DEMO: approved subscription payment",
    ).first()
    if approved_subscription_payment is None:
        approved_subscription_payment = submit_subscription_payment(
            business=business,
            submitted_by=owner,
            amount_paid="500",
            payment_method="esewa",
            transaction_id="DEMO-RENEW-001",
            payment_date=utc_now().date(),
            months_covered=1,
            note="DEMO: approved subscription payment",
            proof_path="proofs/demo-renewal.png",
        )
        approve_subscription_payment(approved_subscription_payment, actor=biz_admin)

    sync_customer_outstanding_balance(customer_one)
    sync_customer_outstanding_balance(customer_two)
    db.session.commit()

    return {
        "businesses": Business.query.count(),
        "users": User.query.count(),
        "products": Product.query.filter_by(business_id=business.id).count(),
        "stock_batches": StockBatch.query.filter_by(business_id=business.id).count(),
        "customers": Customer.query.filter_by(business_id=business.id).count(),
        "sales": Sale.query.filter_by(business_id=business.id).count(),
        "repayments": Repayment.query.filter_by(business_id=business.id).count(),
        "subscription_payments": SubscriptionPayment.query.filter_by(business_id=business.id).count(),
    }


@dataclass
class SmokeResult:
    """Single smoke-check result entry."""

    step: str
    ok: bool
    detail: str


def run_demo_smoke_flow() -> list[SmokeResult]:
    """Execute the thesis demo flow against a temporary test app."""

    temp_dir = Path.cwd() / "instance" / "smoke"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_db = temp_dir / "smoke.sqlite3"
    if temp_db.exists():
        temp_db.unlink()
    temp_db.touch()
    from app import create_app

    class SmokeConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{temp_db.resolve().as_posix()}"
        WTF_CSRF_ENABLED = False

    smoke_app = create_app(SmokeConfig)
    results: list[SmokeResult] = []

    def check(condition: bool, step: str, detail: str):
        results.append(SmokeResult(step=step, ok=condition, detail=detail))
        if not condition:
            raise AssertionError(f"{step}: {detail}")

    with smoke_app.app_context():
        db.drop_all()
        db.create_all()
        create_seed_users()
        client = smoke_app.test_client()

        register_response = client.post(
            "/register",
            data={
                "business_name": "Viva Demo Store",
                "owner_full_name": "Demo Owner",
                "email": "viva-owner@example.com",
                "username": "vivaowner",
                "phone": "+9779800003000",
                "business_type": "Grocery",
                "preferred_language": "en",
                "password": "Owner123!",
                "confirm_password": "Owner123!",
                "submit": "Create business account",
            },
            follow_redirects=True,
        )
        check(register_response.status_code == 200, "register_business", "Owner registration page completed.")
        check(
            Business.query.filter_by(email="viva-owner@example.com").first() is not None,
            "register_business",
            "Business and owner record created.",
        )

        owner_login = client.post(
            "/login",
            data={
                "identifier": "vivaowner",
                "password": "Owner123!",
                "remember_me": "y",
                "submit": "Log in",
            },
            follow_redirects=True,
        )
        check(owner_login.status_code == 200, "owner_login", "Owner login succeeded.")

        owner = User.query.filter_by(email="viva-owner@example.com").first()
        owner_business = owner.business

        category = Category(
            business_id=owner_business.id,
            name="Manual Entry Category",
            description="Created during smoke flow",
            is_active=True,
        )
        db.session.add(category)
        db.session.commit()

        product_response = client.post(
            "/owner/products/new",
            data={
                "category_id": category.id,
                "name": "Smoke Test Product",
                "sku": "SMOKE-01",
                "unit_type": "pack",
                "default_selling_price": "150",
                "min_stock_level": "2",
                "shelf_life_days": "30",
                "description": "Created in smoke flow",
                "image_path": "",
                "is_active": "y",
                "submit": "Save product",
            },
            follow_redirects=True,
        )
        check(product_response.status_code == 200, "add_product", "Product creation page succeeded.")
        product = Product.query.filter_by(business_id=owner_business.id, sku="SMOKE-01").first()
        check(product is not None, "add_product", "Product stored successfully.")

        restock_response = client.post(
            "/owner/inventory/restock",
            data={
                "product_id": product.id,
                "batch_code": "SMOKE-BATCH-01",
                "quantity_added": "10",
                "cost_price": "100",
                "intended_selling_price": "150",
                "restock_date": utc_now().date().isoformat(),
                "expiry_date": (utc_now().date() + timedelta(days=14)).isoformat(),
                "supplier_name": "Smoke Supplier",
                "supplier_contact": "+9779800003001",
                "notes": "Restock from smoke flow",
                "submit": "Save batch",
            },
            follow_redirects=True,
        )
        check(restock_response.status_code == 200, "restock_inventory", "Restock form completed.")
        batch = StockBatch.query.filter_by(business_id=owner_business.id, batch_code="SMOKE-BATCH-01").first()
        check(batch is not None and float(batch.quantity_remaining) == 10.0, "restock_inventory", "Stock batch created.")

        customer_response = client.post(
            "/owner/customers/new",
            data={
                "name": "Smoke Customer",
                "phone": "+9779800003002",
                "address": "Kathmandu",
                "notes": "Created in smoke flow",
                "is_active": "y",
                "submit": "Save customer",
            },
            follow_redirects=True,
        )
        check(customer_response.status_code == 200, "create_customer", "Customer creation page succeeded.")
        customer = Customer.query.filter_by(business_id=owner_business.id, phone="+9779800003002").first()
        check(customer is not None, "create_customer", "Customer stored successfully.")

        cash_sale_response = client.post(
            "/owner/sales/new",
            data=MultiDict(
                [
                    ("customer_id", ""),
                    ("sale_datetime", utc_now().strftime("%Y-%m-%dT%H:%M")),
                    ("payment_mode", "cash"),
                    ("amount_paid", "0"),
                    ("notes", "SMOKE: cash"),
                    ("items-0-product_id", product.id),
                    ("items-0-quantity", "2"),
                    ("items-0-actual_selling_price", "150"),
                    ("submit", "Save sale"),
                ]
            ),
            follow_redirects=True,
        )
        check(cash_sale_response.status_code == 200, "cash_sale", "Cash sale submission succeeded.")
        cash_sale = Sale.query.filter_by(business_id=owner_business.id, notes="SMOKE: cash").first()
        check(cash_sale is not None and float(cash_sale.amount_due) == 0.0, "cash_sale", "Cash sale stored.")

        credit_sale_response = client.post(
            "/owner/sales/new",
            data=MultiDict(
                [
                    ("customer_id", customer.id),
                    ("sale_datetime", utc_now().strftime("%Y-%m-%dT%H:%M")),
                    ("payment_mode", "credit"),
                    ("amount_paid", "0"),
                    ("notes", "SMOKE: credit"),
                    ("items-0-product_id", product.id),
                    ("items-0-quantity", "3"),
                    ("items-0-actual_selling_price", "150"),
                    ("submit", "Save sale"),
                ]
            ),
            follow_redirects=True,
        )
        check(credit_sale_response.status_code == 200, "credit_sale", "Credit sale submission succeeded.")
        credit_sale = Sale.query.filter_by(business_id=owner_business.id, notes="SMOKE: credit").first()
        check(credit_sale is not None and float(credit_sale.amount_due) > 0.0, "credit_sale", "Credit sale stored.")

        repayment_response = client.post(
            f"/owner/repayments/new/{credit_sale.id}",
            data={
                "sale_id": credit_sale.id,
                "amount_paid": "150",
                "payment_date": utc_now().date().isoformat(),
                "note": "SMOKE repayment",
                "submit": "Record repayment",
            },
            follow_redirects=True,
        )
        check(repayment_response.status_code == 200, "record_repayment", "Repayment form completed.")
        db.session.refresh(credit_sale)
        check(float(credit_sale.amount_paid) == 150.0, "record_repayment", "Repayment updated the sale balance.")

        owner_dashboard = client.get("/owner/dashboard")
        sales_report = client.get("/owner/reports/sales")
        subscription_page = client.get("/owner/subscription")
        payment_submit = client.post(
            "/owner/subscription/submit-payment",
            data={
                "amount_paid": "500",
                "payment_method": "khalti",
                "transaction_id": "SMOKE-SUB-001",
                "payment_date": utc_now().date().isoformat(),
                "months_covered": "1",
                "proof_path": "proofs/smoke-renewal.png",
                "note": "SMOKE renewal payment",
                "submit": "Submit payment for approval",
            },
            follow_redirects=True,
        )
        owner_logout = client.post("/logout", data={"submit": "Log out"}, follow_redirects=True)

        admin_client = smoke_app.test_client()
        admin_login = admin_client.post(
            "/admin/login",
            data={
                "identifier": "admin@example.com",
                "password": "Admin123!",
                "submit": "Sign in to admin",
            },
            follow_redirects=True,
        )

        check(owner_dashboard.status_code == 200, "dashboard_updates", "Owner dashboard loads after sales and repayment.")
        check(sales_report.status_code == 200, "check_reports", "Owner reports page loads.")
        check(subscription_page.status_code == 200, "subscription_page", "Owner subscription page loads.")
        check(payment_submit.status_code == 200, "subscription_submit", "Owner can submit a renewal payment.")
        smoke_payment = SubscriptionPayment.query.filter_by(
            business_id=owner_business.id,
            transaction_id="SMOKE-SUB-001",
        ).first()
        check(smoke_payment is not None, "subscription_submit", "Renewal payment record stored.")
        check(owner_logout.status_code == 200, "logout_owner", "Owner logout completed.")
        check(
            admin_login.status_code == 200,
            "admin_login",
            "Admin login request completed successfully.",
        )
        check(
            b"/admin/businesses" in admin_login.data and b"Total Businesses" in admin_login.data,
            "admin_visibility",
            "Admin dashboard renders platform-level visibility widgets.",
        )

        biz_client = smoke_app.test_client()
        biz_login = biz_client.post(
            "/biz/login",
            data={
                "identifier": "biz@example.com",
                "password": "Biz12345!",
                "submit": "Sign in to business admin",
            },
            follow_redirects=True,
        )
        check(biz_login.status_code == 200, "biz_login", "Business Admin login request completed successfully.")
        payment_approve = biz_client.post(
            f"/biz/payments/{smoke_payment.id}/approve",
            data={"submit": "Submit"},
            follow_redirects=True,
        )
        check(payment_approve.status_code == 200, "biz_payment_approve", "Business Admin can approve a renewal payment.")
        db.session.refresh(smoke_payment)
        check(smoke_payment.status == "approved", "biz_payment_approve", "Renewal payment becomes approved.")

        ops_client = smoke_app.test_client()
        ops_login = ops_client.post(
            "/ops/login",
            data={
                "identifier": "ops@example.com",
                "password": "Ops12345!",
                "submit": "Sign in to ops",
            },
            follow_redirects=True,
        )
        check(ops_login.status_code == 200, "ops_login", "Operational Admin login request completed successfully.")
        check(
            b"/ops/businesses" in ops_login.data or b"Operational Admin" in ops_login.data,
            "ops_visibility",
            "Operational Admin dashboard renders correctly.",
        )

    return results
