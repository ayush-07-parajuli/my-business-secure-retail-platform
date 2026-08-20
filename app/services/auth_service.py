"""Authentication, audit, and brute-force support helpers."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from flask import current_app, has_request_context, request
from sqlalchemy import or_

from app.extensions import db
from app.models import AuditLog, Business, LoginAttempt, User
from app.models.base import utc_now


def normalize_identifier(identifier: str) -> str:
    """Normalize a login identifier for consistent lookups."""

    return (identifier or "").strip().lower()


def get_client_ip() -> str | None:
    """Return the best available client IP for logging."""

    if not has_request_context():
        return None

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr


def get_user_agent() -> str | None:
    """Return the current request user agent string."""

    if not has_request_context():
        return None

    return request.headers.get("User-Agent")


def find_user_by_identifier(identifier: str, *, roles: tuple[str, ...] | None = None) -> User | None:
    """Find a user by email or username, optionally restricted by role."""

    normalized = normalize_identifier(identifier)
    query = User.query.filter(
        or_(
            db.func.lower(User.email) == normalized,
            db.func.lower(User.username) == normalized,
        )
    )

    if roles:
        query = query.filter(User.role.in_(roles))

    return query.first()


def is_login_temporarily_blocked(identifier: str, *, scope: str) -> bool:
    """Check whether login is temporarily blocked due to repeated failures."""

    normalized = normalize_identifier(identifier)
    ip_address = get_client_ip()
    window_start = utc_now() - timedelta(
        minutes=current_app.config["AUTH_ATTEMPT_WINDOW_MINUTES"]
    )
    failure_query = LoginAttempt.query.filter(
        LoginAttempt.success.is_(False),
        LoginAttempt.attempt_scope == scope,
        LoginAttempt.attempted_at >= window_start,
    )

    identifier_failures = failure_query.filter(
        db.func.lower(LoginAttempt.attempted_identifier) == normalized
    ).count()
    ip_failures = 0
    if ip_address:
        ip_failures = failure_query.filter(LoginAttempt.ip_address == ip_address).count()

    threshold = current_app.config["AUTH_MAX_FAILED_ATTEMPTS"]
    return identifier_failures >= threshold or ip_failures >= threshold


def record_login_attempt(
    *,
    identifier: str,
    scope: str,
    success: bool,
    role_attempted: str | None = None,
    user: User | None = None,
    business: Business | None = None,
    reason: str | None = None,
) -> LoginAttempt:
    """Persist a login attempt entry."""

    attempt = LoginAttempt(
        attempt_scope=scope,
        attempted_identifier=normalize_identifier(identifier),
        role_attempted=role_attempted,
        success=success,
        failure_reason=reason,
        user=user,
        business=business,
        ip_address=get_client_ip(),
        user_agent=get_user_agent(),
    )
    db.session.add(attempt)
    return attempt


def record_audit_event(
    *,
    action: str,
    description: str,
    entity_type: str,
    entity_id: str | None = None,
    user: User | None = None,
    business: Business | None = None,
    severity: str = "info",
) -> AuditLog:
    """Persist an audit log entry for auth and security events."""

    entry = AuditLog(
        action=action,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
        user=user,
        business=business,
        severity=severity,
        ip_address=get_client_ip(),
    )
    db.session.add(entry)
    return entry


def register_business_owner(
    *,
    business_name: str,
    owner_full_name: str,
    email: str,
    username: str,
    phone: str,
    password: str,
    preferred_language: str,
    business_type: str | None = None,
) -> tuple[Business, User]:
    """Create a business and its initial owner account."""

    normalized_email = email.strip().lower()
    normalized_username = username.strip().lower()

    business = Business(
        business_name=business_name.strip(),
        owner_name=owner_full_name.strip(),
        email=normalized_email,
        phone=phone.strip(),
        business_type=(business_type or "").strip() or None,
        preferred_language=preferred_language,
        status="active",
        preferred_currency="NPR",
        currency_symbol="Rs.",
    )
    from app.services.subscription_service import initialize_business_subscription

    initialize_business_subscription(business, status="trial")
    owner = User(
        business=business,
        full_name=owner_full_name.strip(),
        username=normalized_username,
        email=normalized_email,
        role="owner",
        preferred_language=preferred_language,
        status="active",
        is_primary_owner=True,
    )
    owner.set_password(password)

    db.session.add_all([business, owner])
    db.session.flush()

    record_audit_event(
        action="owner_registered",
        description=f"Business owner '{owner.email}' registered business '{business.business_name}'.",
        entity_type="business",
        entity_id=business.id,
        user=owner,
        business=business,
    )
    return business, owner


def create_platform_admin_user(
    *,
    full_name: str,
    username: str,
    email: str,
    password: str,
    role: str,
    preferred_language: str,
    actor: User,
) -> User:
    """Create an ops_admin or biz_admin account."""

    normalized_email = email.strip().lower()
    normalized_username = username.strip().lower()

    if role not in {"ops_admin", "biz_admin"}:
        raise ValueError("Platform admin role must be ops_admin or biz_admin.")

    if User.query.filter(
        or_(db.func.lower(User.email) == normalized_email, db.func.lower(User.username) == normalized_username)
    ).first():
        raise ValueError("The email or username is already in use.")

    user = User(
        full_name=full_name.strip(),
        username=normalized_username,
        email=normalized_email,
        role=role,
        status="active",
        preferred_language=preferred_language,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    record_audit_event(
        action="company_admin_created",
        description=f"{actor.full_name} created {role} account '{user.email}'.",
        entity_type="user",
        entity_id=user.id,
        user=actor,
    )
    return user


def update_successful_login(user: User) -> None:
    """Update a user's successful login metadata."""

    timestamp = utc_now()
    user.last_login_at = timestamp
    user.failed_login_count = 0
    if user.business:
        user.business.last_login_at = timestamp


def increment_failed_login(user: User | None) -> None:
    """Increment the failed login counter for a known user."""

    if user is not None:
        user.failed_login_count += 1


def create_seed_users() -> dict[str, str]:
    """Create baseline development users when they do not exist."""

    created: dict[str, str] = {}

    admin_email = current_app.config["DEFAULT_SUPER_ADMIN_EMAIL"]
    admin_password = current_app.config["DEFAULT_SUPER_ADMIN_PASSWORD"]

    super_admin = User.query.filter_by(email=admin_email).first()
    if super_admin is None:
        super_admin = User(
            full_name="Platform Super Admin",
            username="superadmin",
            email=admin_email,
            role="super_admin",
            status="active",
            preferred_language="en",
        )
        super_admin.set_password(admin_password)
        db.session.add(super_admin)
        created["super_admin"] = f"{admin_email} / {admin_password}"

    ops_admin_email = current_app.config["DEFAULT_OPS_ADMIN_EMAIL"]
    ops_admin_password = current_app.config["DEFAULT_OPS_ADMIN_PASSWORD"]
    ops_admin = User.query.filter_by(email=ops_admin_email).first()
    if ops_admin is None:
        ops_admin = User(
            full_name="Operations Admin",
            username="opsadmin",
            email=ops_admin_email,
            role="ops_admin",
            status="active",
            preferred_language="en",
        )
        ops_admin.set_password(ops_admin_password)
        db.session.add(ops_admin)
        created["ops_admin"] = f"{ops_admin_email} / {ops_admin_password}"

    biz_admin_email = current_app.config["DEFAULT_BIZ_ADMIN_EMAIL"]
    biz_admin_password = current_app.config["DEFAULT_BIZ_ADMIN_PASSWORD"]
    biz_admin = User.query.filter_by(email=biz_admin_email).first()
    if biz_admin is None:
        biz_admin = User(
            full_name="Business Admin",
            username="bizadmin",
            email=biz_admin_email,
            role="biz_admin",
            status="active",
            preferred_language="en",
        )
        biz_admin.set_password(biz_admin_password)
        db.session.add(biz_admin)
        created["biz_admin"] = f"{biz_admin_email} / {biz_admin_password}"

    sample_business = Business.query.filter_by(email="owner@example.com").first()
    if sample_business is None:
        sample_business = Business(
            business_name="My Business Demo Store",
            owner_name="Sample Owner",
            phone="+9779800000000",
            email="owner@example.com",
            business_type="Retail",
            status="active",
            preferred_language="en",
            preferred_currency="NPR",
            currency_symbol="Rs.",
        )
        from app.services.subscription_service import initialize_business_subscription

        initialize_business_subscription(sample_business, status="active")
        db.session.add(sample_business)
        db.session.flush()
    else:
        from app.services.subscription_service import initialize_business_subscription

        initialize_business_subscription(sample_business, status=sample_business.subscription_status or "active")
        sample_business.plan_name = "Full Plan"
        sample_business.subscription_plan = "Full Plan"
        sample_business.monthly_fee = Decimal(str(current_app.config.get("DEFAULT_MONTHLY_SUBSCRIPTION_FEE", 500)))
        sample_business.preferred_currency = sample_business.preferred_currency or "NPR"
        sample_business.currency_symbol = sample_business.currency_symbol or "Rs."

    owner = User.query.filter_by(email="owner@example.com").first()
    if owner is None:
        owner = User(
            business=sample_business,
            full_name="Sample Owner",
            username="owner",
            email="owner@example.com",
            role="owner",
            status="active",
            preferred_language="en",
            is_primary_owner=True,
        )
        owner.set_password(current_app.config["DEFAULT_OWNER_PASSWORD"])
        db.session.add(owner)
        created["owner"] = f"owner@example.com / {current_app.config['DEFAULT_OWNER_PASSWORD']}"

    staff = User.query.filter_by(email="staff@example.com").first()
    if staff is None:
        staff = User(
            business=sample_business,
            full_name="Sample Staff",
            username="staff",
            email="staff@example.com",
            role="staff",
            status="active",
            preferred_language="en",
        )
        staff.set_password(current_app.config["DEFAULT_STAFF_PASSWORD"])
        db.session.add(staff)
        created["staff"] = f"staff@example.com / {current_app.config['DEFAULT_STAFF_PASSWORD']}"

    db.session.commit()
    return created
