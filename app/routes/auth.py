"""Authentication routes and role-aware access flow."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms import (
    ChangePasswordForm,
    LoginForm,
    OwnerRegistrationForm,
)
from app.services import (
    find_user_by_identifier,
    get_subscription_summary,
    increment_failed_login,
    is_login_temporarily_blocked,
    record_audit_event,
    record_login_attempt,
    register_business_owner,
    update_successful_login,
)
from app.utils.auth import is_safe_url, redirect_to_dashboard
from app.utils.i18n import set_language

auth_bp = Blueprint("auth", __name__)


LOGIN_CONFIG = {
    "tenant": {
        "roles": ("super_admin", "ops_admin", "biz_admin", "owner", "staff"),
        "scope": "tenant",
        "template": "auth/login.html",
        "login_endpoint": "auth.login",
        "dashboard_hint": "their authorized workspace",
        "role_mismatch_message": "This login page is only for authorized accounts.",
        "invalid_credentials_message": "Invalid credentials. Please try again.",
        "blocked_message": "Too many failed login attempts were detected. Please wait a few minutes and try again.",
        "inactive_message": "Your account is inactive. Please contact support.",
        "business_inactive_message": "Your business account is suspended or inactive. Please contact platform support.",
        "success_message": "Welcome back, {name}.",
    },
    "admin": {
        "roles": ("super_admin",),
        "scope": "admin",
        "template": "auth/admin_login.html",
        "login_endpoint": "auth.admin_login",
        "dashboard_hint": "the Super Admin control center",
        "role_mismatch_message": "This login page is only for Super Admin accounts.",
        "invalid_credentials_message": "Invalid admin credentials. Please try again.",
        "blocked_message": "Too many failed admin login attempts were detected. Please wait and try again.",
        "inactive_message": "This admin account is inactive.",
        "business_inactive_message": "This account is not available.",
        "success_message": "Welcome back, {name}.",
    },
    "ops": {
        "roles": ("ops_admin",),
        "scope": "ops",
        "template": "auth/ops_login.html",
        "login_endpoint": "auth.ops_login",
        "dashboard_hint": "the operational admin area",
        "role_mismatch_message": "This login page is only for Operational Admin accounts.",
        "invalid_credentials_message": "Invalid operational admin credentials. Please try again.",
        "blocked_message": "Too many failed operational admin login attempts were detected. Please wait and try again.",
        "inactive_message": "This operational admin account is inactive.",
        "business_inactive_message": "This account is not available.",
        "success_message": "Welcome back, {name}.",
    },
    "biz": {
        "roles": ("biz_admin",),
        "scope": "biz",
        "template": "auth/biz_login.html",
        "login_endpoint": "auth.biz_login",
        "dashboard_hint": "the business admin area",
        "role_mismatch_message": "This login page is only for Business Admin accounts.",
        "invalid_credentials_message": "Invalid business admin credentials. Please try again.",
        "blocked_message": "Too many failed business admin login attempts were detected. Please wait and try again.",
        "inactive_message": "This business admin account is inactive.",
        "business_inactive_message": "This account is not available.",
        "success_message": "Welcome back, {name}.",
    },
}


def _role_login_endpoint(user) -> str:
    """Return the unified public login endpoint for logged-out users."""

    return "auth.login"


def _login_attempt_scope(user) -> str:
    """Resolve the existing login-attempt scope for a user record."""

    if user is None:
        return "tenant"
    if user.is_super_admin():
        return "admin"
    if user.is_ops_admin():
        return "ops"
    if user.is_biz_admin():
        return "biz"
    return "tenant"


def _handle_authenticated_redirect():
    """Redirect an already-authenticated user safely."""

    if current_user.is_authenticated:
        if not current_user.is_active:
            destination = _role_login_endpoint(current_user)
            logout_user()
            flash("Your previous session has expired because the account is inactive.", "warning")
            return redirect(url_for(destination))
        return redirect_to_dashboard()
    return None


def _render_login(template_name: str, form):
    return render_template(template_name, form=form)


def _process_login(form, *, config_key: str):
    """Run the shared login logic for a role-scoped login page."""

    login_config = LOGIN_CONFIG[config_key]

    if not form.validate_on_submit():
        return None

    identifier = form.identifier.data
    candidate_user = find_user_by_identifier(identifier)
    attempt_scope = _login_attempt_scope(candidate_user)

    if is_login_temporarily_blocked(identifier, scope=attempt_scope):
        record_login_attempt(
            identifier=identifier,
            scope=attempt_scope,
            success=False,
            reason="temporarily_blocked",
        )
        record_audit_event(
            action="user_login_failed",
            description=f"Temporarily blocked login attempt for '{identifier}' on {config_key} login.",
            entity_type="auth",
            severity="warning",
        )
        db.session.commit()
        flash(login_config["blocked_message"], "danger")
        return _render_login(login_config["template"], form)

    user = candidate_user if candidate_user and candidate_user.has_role(*login_config["roles"]) else None

    if candidate_user is not None and user is None:
        record_login_attempt(
            identifier=identifier,
            scope=attempt_scope,
            success=False,
            role_attempted=candidate_user.role,
            user=candidate_user,
            business=candidate_user.business,
            reason="role_mismatch",
        )
        record_audit_event(
            action="user_login_failed",
            description=(
                f"Role mismatch login attempt for '{candidate_user.email}' on {config_key} login."
            ),
            entity_type="user",
            entity_id=candidate_user.id,
            user=candidate_user,
            business=candidate_user.business,
            severity="warning",
        )
        db.session.commit()
        flash(
            f"{login_config['role_mismatch_message']} Please use the correct login page for {login_config['dashboard_hint']}.",
            "warning",
        )
        return _render_login(login_config["template"], form)

    if user is None or not user.check_password(form.password.data):
        increment_failed_login(user)
        record_login_attempt(
            identifier=identifier,
            scope=attempt_scope,
            success=False,
            role_attempted=user.role if user else None,
            user=user,
            business=user.business if user else None,
            reason="invalid_credentials",
        )
        record_audit_event(
            action="user_login_failed",
            description=f"Failed login attempt for '{identifier}' on {config_key} login.",
            entity_type="user",
            entity_id=user.id if user else None,
            user=user,
            business=user.business if user else None,
            severity="warning",
        )
        db.session.commit()
        flash(login_config["invalid_credentials_message"], "danger")
        return _render_login(login_config["template"], form)

    if user.status != "active":
        increment_failed_login(user)
        record_login_attempt(
            identifier=identifier,
            scope=attempt_scope,
            success=False,
            role_attempted=user.role,
            user=user,
            business=user.business,
            reason="inactive_user",
        )
        record_audit_event(
            action="user_login_failed",
            description=f"Inactive user '{user.email}' attempted to log in via {config_key}.",
            entity_type="user",
            entity_id=user.id,
            user=user,
            business=user.business,
            severity="warning",
        )
        db.session.commit()
        flash(login_config["inactive_message"], "warning")
        return _render_login(login_config["template"], form)

    if user.business and user.business.status != "active":
        increment_failed_login(user)
        record_login_attempt(
            identifier=identifier,
            scope=attempt_scope,
            success=False,
            role_attempted=user.role,
            user=user,
            business=user.business,
            reason="suspended_business",
        )
        record_audit_event(
            action="blocked_suspended_business_login",
            description=(
                f"Blocked login for '{user.email}' because business "
                f"'{user.business.business_name}' is not active."
            ),
            entity_type="business",
            entity_id=user.business.id,
            user=user,
            business=user.business,
            severity="warning",
        )
        db.session.commit()
        flash(login_config["business_inactive_message"], "danger")
        return _render_login(login_config["template"], form)

    login_user(user, remember=form.remember_me.data)
    update_successful_login(user)
    set_language(user.preferred_language)
    record_login_attempt(
        identifier=identifier,
        scope=_login_attempt_scope(user),
        success=True,
        role_attempted=user.role,
        user=user,
        business=user.business,
    )
    record_audit_event(
        action="user_login_success",
        description=f"User '{user.email}' logged in successfully via {config_key} login.",
        entity_type="user",
        entity_id=user.id,
        user=user,
        business=user.business,
    )
    db.session.commit()

    flash(login_config["success_message"].format(name=user.full_name), "success")
    if user.business:
        subscription_summary = get_subscription_summary(user.business)
        if subscription_summary and subscription_summary["status"] != "active":
            flash(subscription_summary["status_message"], subscription_summary["severity"])

    next_url = request.form.get("next") or request.args.get("next")
    if is_safe_url(next_url):
        return redirect(next_url)
    return redirect_to_dashboard(user)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle unified public login for all account types."""

    redirected = _handle_authenticated_redirect()
    if redirected:
        return redirected

    form = LoginForm()
    response = _process_login(form, config_key="tenant")
    if response is not None:
        return response
    return render_template("auth/login.html", form=form)


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Preserve the old URL while directing users to the unified login flow."""

    if request.method == "GET":
        return redirect(url_for("auth.login", next=request.args.get("next")))
    return login()


@auth_bp.route("/ops/login", methods=["GET", "POST"])
def ops_login():
    """Preserve the old URL while directing users to the unified login flow."""

    if request.method == "GET":
        return redirect(url_for("auth.login", next=request.args.get("next")))
    return login()


@auth_bp.route("/biz/login", methods=["GET", "POST"])
def biz_login():
    """Preserve the old URL while directing users to the unified login flow."""

    if request.method == "GET":
        return redirect(url_for("auth.login", next=request.args.get("next")))
    return login()


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a business and its first owner account."""

    redirected = _handle_authenticated_redirect()
    if redirected:
        return redirected

    form = OwnerRegistrationForm()
    if form.validate_on_submit():
        register_business_owner(
            business_name=form.business_name.data,
            owner_full_name=form.owner_full_name.data,
            email=form.email.data,
            username=form.username.data,
            phone=form.phone.data,
            password=form.password.data,
            preferred_language=form.preferred_language.data,
            business_type=form.business_type.data,
        )
        set_language(form.preferred_language.data)
        db.session.commit()
        flash(
            "Your My Business account has been created successfully. You can sign in now.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Allow any authenticated user to update their password."""

    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = current_user._get_current_object()
        if not user.check_password(form.current_password.data):
            form.current_password.errors.append("Current password is incorrect.")
        else:
            user.set_password(form.new_password.data)
            record_audit_event(
                action="user_password_changed",
                description=f"Password changed for '{user.email}'.",
                entity_type="user",
                entity_id=user.id,
                user=user,
                business=user.business,
            )
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect_to_dashboard(user)
    return render_template("auth/change_password.html", form=form)


@auth_bp.post("/logout")
@login_required
def logout():
    """Log out the current user."""

    user = current_user._get_current_object()
    destination = _role_login_endpoint(user)
    record_audit_event(
        action="user_logout",
        description=f"User '{user.email}' logged out.",
        entity_type="user",
        entity_id=user.id,
        user=user,
        business=user.business,
    )
    db.session.commit()
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for(destination))


@auth_bp.get("/select-language/<language_code>")
def select_language(language_code: str):
    """Switch the current UI language."""

    if set_language(language_code):
        flash("Language updated.", "info")
    else:
        flash("Selected language is not supported.", "warning")

    return redirect(request.referrer or url_for("auth.login"))
