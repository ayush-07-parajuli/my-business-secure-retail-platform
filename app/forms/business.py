"""Business module forms for categories, products, inventory, sales, and repayments."""

from __future__ import annotations

from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DateTimeLocalField,
    DecimalField,
    FieldList,
    Form,
    FormField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, ValidationError

from app.forms.auth import LANGUAGE_CHOICES, validate_strong_password


UNIT_TYPE_CHOICES = [
    ("unit", "Unit"),
    ("kg", "Kilogram"),
    ("g", "Gram"),
    ("ltr", "Litre"),
    ("ml", "Millilitre"),
    ("pack", "Pack"),
    ("box", "Box"),
]

PAYMENT_MODE_CHOICES = [
    ("cash", "Cash"),
    ("credit", "Credit"),
    ("partial", "Partial"),
]

BUSINESS_STATUS_CHOICES = [
    ("active", "Active"),
    ("pending", "Pending"),
    ("suspended", "Suspended"),
]

SUBSCRIPTION_STATUS_CHOICES = [
    ("active", "Active"),
    ("expired", "Expired"),
    ("pending_approval", "Pending Approval"),
    ("suspended", "Suspended"),
    ("trial", "Trial"),
]

SUBSCRIPTION_PAYMENT_METHOD_CHOICES = [
    ("esewa", "eSewa"),
    ("khalti", "Khalti"),
    ("bank_transfer", "Bank Transfer"),
    ("cash", "Cash"),
]


class CategoryForm(FlaskForm):
    """Form for creating and editing product categories."""

    name = StringField("Category name", validators=[DataRequired(), Length(min=2, max=120)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=1000)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save category")


class ProductForm(FlaskForm):
    """Form for creating and editing products."""

    category_id = SelectField("Category", validators=[Optional()], choices=[])
    name = StringField("Product name", validators=[DataRequired(), Length(min=2, max=160)])
    sku = StringField("SKU", validators=[Optional(), Length(max=100)])
    unit_type = SelectField("Unit type", validators=[DataRequired()], choices=UNIT_TYPE_CHOICES)
    default_selling_price = DecimalField(
        "Default selling price",
        validators=[DataRequired(), NumberRange(min=0)],
        places=2,
    )
    min_stock_level = DecimalField(
        "Minimum stock level",
        validators=[DataRequired(), NumberRange(min=0)],
        places=2,
    )
    shelf_life_days = IntegerField(
        "Shelf life (days)",
        validators=[Optional(), NumberRange(min=0)],
    )
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])
    image_path = StringField("Image path", validators=[Optional(), Length(max=255)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save product")

    def validate_sku(self, field) -> None:
        if field.data:
            field.data = field.data.strip()


class RestockForm(FlaskForm):
    """Form for adding or editing a stock batch."""

    product_id = SelectField("Product", validators=[DataRequired()], choices=[])
    batch_code = StringField("Batch code", validators=[Optional(), Length(max=100)])
    quantity_added = DecimalField(
        "Quantity added",
        validators=[DataRequired(), NumberRange(min=0.01)],
        places=2,
    )
    cost_price = DecimalField(
        "Cost price",
        validators=[DataRequired(), NumberRange(min=0)],
        places=2,
    )
    intended_selling_price = DecimalField(
        "Intended selling price",
        validators=[DataRequired(), NumberRange(min=0)],
        places=2,
    )
    restock_date = DateField(
        "Restock date",
        validators=[DataRequired()],
        default=lambda: datetime.utcnow().date(),
    )
    expiry_date = DateField("Expiry date", validators=[Optional()])
    supplier_name = StringField("Supplier name", validators=[DataRequired(), Length(max=120)])
    supplier_contact = StringField("Supplier contact", validators=[Optional(), Length(max=120)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Save batch")

    def validate_expiry_date(self, field) -> None:
        if field.data and self.restock_date.data and field.data < self.restock_date.data:
            raise ValidationError("Expiry date cannot be before the restock date.")


class CustomerForm(FlaskForm):
    """Form for creating and editing customers."""

    name = StringField("Customer name", validators=[DataRequired(), Length(min=2, max=160)])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    address = TextAreaField("Address", validators=[Optional(), Length(max=1000)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1500)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save customer")


class SaleItemEntryForm(Form):
    """Nested form for a single sale line item."""

    product_id = SelectField("Product", validators=[Optional()], choices=[])
    quantity = DecimalField(
        "Quantity",
        validators=[Optional(), NumberRange(min=0.01)],
        places=2,
    )
    actual_selling_price = DecimalField(
        "Selling price",
        validators=[Optional(), NumberRange(min=0)],
        places=2,
    )


class SaleForm(FlaskForm):
    """Form for entering a sale transaction."""

    customer_id = SelectField("Customer", validators=[Optional()], choices=[])
    sale_datetime = DateTimeLocalField(
        "Sale date and time",
        validators=[DataRequired()],
        format="%Y-%m-%dT%H:%M",
        default=datetime.utcnow,
    )
    payment_mode = SelectField(
        "Payment mode",
        validators=[DataRequired()],
        choices=PAYMENT_MODE_CHOICES,
    )
    amount_paid = DecimalField(
        "Amount paid",
        validators=[Optional(), NumberRange(min=0)],
        places=2,
        default=0,
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1500)])
    items = FieldList(FormField(SaleItemEntryForm), min_entries=1)
    submit = SubmitField("Save sale")


class RepaymentForm(FlaskForm):
    """Form for recording repayments against credit sales."""

    sale_id = HiddenField("Sale ID", validators=[DataRequired()])
    amount_paid = DecimalField(
        "Amount paid",
        validators=[DataRequired(), NumberRange(min=0.01)],
        places=2,
    )
    payment_date = DateField(
        "Payment date",
        validators=[DataRequired()],
        default=lambda: datetime.utcnow().date(),
    )
    note = TextAreaField("Note", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Record repayment")


class BusinessSettingsForm(FlaskForm):
    """Form for owner-manageable business settings."""

    business_name = StringField("Business name", validators=[DataRequired(), Length(min=2, max=120)])
    owner_name = StringField("Owner name", validators=[DataRequired(), Length(min=2, max=120)])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=255)])
    address = TextAreaField("Address", validators=[Optional(), Length(max=1000)])
    business_type = StringField("Business type", validators=[Optional(), Length(max=120)])
    preferred_language = SelectField(
        "Preferred language",
        choices=LANGUAGE_CHOICES,
        validators=[DataRequired()],
    )
    near_expiry_threshold_days = IntegerField(
        "Near expiry threshold (days)",
        validators=[DataRequired(), NumberRange(min=1, max=120)],
    )
    currency_symbol = StringField("Currency symbol", validators=[DataRequired(), Length(max=12)])
    receipt_footer_note = TextAreaField("Receipt footer note", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Save settings")


class AdminBusinessCreateForm(FlaskForm):
    """Form for a Super Admin to onboard a business and owner account."""

    business_name = StringField("Business name", validators=[DataRequired(), Length(min=2, max=120)])
    owner_name = StringField("Owner name", validators=[DataRequired(), Length(min=2, max=120)])
    owner_email = StringField("Owner email", validators=[DataRequired(), Email(), Length(max=255)])
    owner_username = StringField("Owner username", validators=[DataRequired(), Length(min=3, max=80)])
    owner_password = PasswordField("Owner password", validators=[DataRequired(), validate_strong_password])
    confirm_owner_password = PasswordField(
        "Confirm owner password",
        validators=[DataRequired(), EqualTo("owner_password", message="Passwords must match.")],
    )
    phone = StringField("Business phone", validators=[Optional(), Length(max=30)])
    business_email = StringField("Business email", validators=[Optional(), Email(), Length(max=255)])
    address = TextAreaField("Address", validators=[Optional(), Length(max=1000)])
    business_type = StringField("Business type", validators=[Optional(), Length(max=120)])
    preferred_language = SelectField(
        "Preferred language",
        choices=LANGUAGE_CHOICES,
        validators=[DataRequired()],
    )
    status = SelectField("Status", validators=[DataRequired()], choices=BUSINESS_STATUS_CHOICES, default="active")
    plan_name = StringField("Plan name", validators=[DataRequired(), Length(min=2, max=120)], default="Full Plan")
    monthly_fee = DecimalField(
        "Monthly fee",
        validators=[DataRequired(), NumberRange(min=0)],
        places=2,
        default=500,
    )
    subscription_status = SelectField(
        "Subscription status",
        validators=[DataRequired()],
        choices=SUBSCRIPTION_STATUS_CHOICES,
        default="trial",
    )
    currency_symbol = StringField("Currency symbol", validators=[DataRequired(), Length(max=12)], default="Rs.")
    preferred_currency = StringField("Preferred currency", validators=[DataRequired(), Length(max=10)], default="NPR")
    near_expiry_threshold_days = IntegerField(
        "Near expiry threshold (days)",
        validators=[DataRequired(), NumberRange(min=1, max=120)],
        default=7,
    )
    receipt_footer_note = TextAreaField("Receipt footer note", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Create business")


class SubscriptionPaymentForm(FlaskForm):
    """Form for manual subscription payment submission."""

    amount_paid = DecimalField(
        "Amount paid",
        validators=[DataRequired(), NumberRange(min=0.01)],
        places=2,
        default=500,
    )
    payment_method = SelectField(
        "Payment method",
        validators=[DataRequired()],
        choices=SUBSCRIPTION_PAYMENT_METHOD_CHOICES,
    )
    transaction_id = StringField("Transaction ID", validators=[Optional(), Length(max=120)])
    payment_date = DateField(
        "Payment date",
        validators=[DataRequired()],
        default=lambda: datetime.utcnow().date(),
    )
    months_covered = IntegerField(
        "Months covered",
        validators=[DataRequired(), NumberRange(min=1, max=24)],
        default=1,
    )
    proof_path = StringField("Proof path / screenshot reference", validators=[Optional(), Length(max=255)])
    note = TextAreaField("Note", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Submit payment for approval")


class PlatformAdminUserForm(FlaskForm):
    """Simple Super Admin form for creating company-side admin accounts."""

    full_name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField(
        "Admin role",
        validators=[DataRequired()],
        choices=[("ops_admin", "Operational Admin"), ("biz_admin", "Business Admin")],
    )
    preferred_language = SelectField(
        "Preferred language",
        choices=LANGUAGE_CHOICES,
        validators=[DataRequired()],
    )
    password = PasswordField("Password", validators=[DataRequired(), validate_strong_password])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create admin account")

    def validate_email(self, field) -> None:
        from app.models import User

        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("A user with this email already exists.")

    def validate_username(self, field) -> None:
        from app.models import User

        if User.query.filter_by(username=field.data.strip().lower()).first():
            raise ValidationError("This username is already in use.")


class ActionForm(FlaskForm):
    """Generic CSRF-protected action form."""

    submit = SubmitField("Submit")
