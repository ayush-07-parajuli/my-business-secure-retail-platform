"""Authentication-related Flask-WTF forms."""

from __future__ import annotations

import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError

from app.models import Business, User


LANGUAGE_CHOICES = [
    ("en", "English"),
    ("ne", "Nepali"),
]


def validate_strong_password(_form, field) -> None:
    """Require a minimally strong password for prototype auth flows."""

    value = (field.data or "").strip()

    if len(value) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Za-z]", value):
        raise ValidationError("Password must include at least one letter.")
    if not re.search(r"\d", value):
        raise ValidationError("Password must include at least one number.")


class LoginForm(FlaskForm):
    """Unified public login form for all account types."""

    identifier = StringField(
        "Email or username",
        validators=[DataRequired(), Length(max=255)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=255)],
    )
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Log in")


class AdminLoginForm(FlaskForm):
    """Dedicated Super Admin login form."""

    identifier = StringField(
        "Admin email or username",
        validators=[DataRequired(), Length(max=255)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=255)],
    )
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Sign in to admin")


class OpsAdminLoginForm(FlaskForm):
    """Dedicated Operational Admin login form."""

    identifier = StringField(
        "Ops admin email or username",
        validators=[DataRequired(), Length(max=255)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=255)],
    )
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Sign in to ops")


class BizAdminLoginForm(FlaskForm):
    """Dedicated Business Admin login form."""

    identifier = StringField(
        "Business admin email or username",
        validators=[DataRequired(), Length(max=255)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=255)],
    )
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Sign in to business admin")


class OwnerRegistrationForm(FlaskForm):
    """Business owner registration form."""

    business_name = StringField(
        "Business name",
        validators=[DataRequired(), Length(min=2, max=120)],
    )
    owner_full_name = StringField(
        "Owner full name",
        validators=[DataRequired(), Length(min=2, max=120)],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=80)],
    )
    phone = StringField(
        "Phone",
        validators=[DataRequired(), Length(min=5, max=30)],
    )
    preferred_language = SelectField(
        "Preferred language",
        choices=LANGUAGE_CHOICES,
        validators=[DataRequired()],
    )
    business_type = StringField(
        "Business type",
        validators=[Optional(), Length(max=120)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), validate_strong_password],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create business account")

    def validate_email(self, field) -> None:
        email = field.data.strip().lower()

        if User.query.filter_by(email=email).first():
            raise ValidationError("A user with this email already exists.")

        if Business.query.filter_by(email=email).first():
            raise ValidationError("A business with this email already exists.")

    def validate_username(self, field) -> None:
        username = field.data.strip().lower()

        if User.query.filter_by(username=username).first():
            raise ValidationError("This username is already in use.")


class StaffCreationForm(FlaskForm):
    """Placeholder form for staff creation in later phases."""

    full_name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    preferred_language = SelectField(
        "Preferred language",
        choices=LANGUAGE_CHOICES,
        validators=[DataRequired()],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), validate_strong_password],
    )
    submit = SubmitField("Create staff user")


class ChangePasswordForm(FlaskForm):
    """Form for authenticated password changes."""

    current_password = PasswordField(
        "Current password",
        validators=[DataRequired(), Length(min=8, max=255)],
    )
    new_password = PasswordField(
        "New password",
        validators=[DataRequired(), validate_strong_password],
    )
    confirm_new_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )
    submit = SubmitField("Change password")


class LogoutForm(FlaskForm):
    """Simple CSRF-protected logout form."""

    submit = SubmitField("Log out")
