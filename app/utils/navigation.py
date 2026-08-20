"""Role-aware navigation helpers for the dashboard shell."""

from __future__ import annotations

from flask import request
from flask_login import current_user


def _nav_item(label_key: str, endpoint: str, *, active_prefix: str | None = None) -> dict:
    """Build a single navigation item definition."""

    active_match = active_prefix or endpoint
    current_endpoint = request.endpoint or ""
    return {
        "label_key": label_key,
        "endpoint": endpoint,
        "active": current_endpoint == endpoint or current_endpoint.startswith(active_match),
    }


def build_navigation() -> list[dict]:
    """Return grouped navigation sections for the active user."""

    if not current_user.is_authenticated:
        return []

    if current_user.is_super_admin():
        return [
            {
                "title_key": "nav.section_platform",
                "items": [
                    _nav_item("nav.dashboard", "admin.dashboard", active_prefix="admin.dashboard"),
                    _nav_item("nav.operational_admin", "ops.dashboard", active_prefix="ops."),
                    _nav_item("nav.business_admin", "biz.dashboard", active_prefix="biz."),
                    _nav_item("nav.businesses", "admin.businesses", active_prefix="admin.business"),
                    _nav_item("nav.users", "admin.users", active_prefix="admin.user"),
                    _nav_item("nav.payments", "biz.payments", active_prefix="biz.payment"),
                    _nav_item("nav.revenue", "biz.revenue", active_prefix="biz.revenue"),
                    _nav_item("nav.activity_logs", "admin.activity_logs", active_prefix="admin.activity_logs"),
                    _nav_item("nav.login_attempts", "admin.login_attempts", active_prefix="admin.login_attempts"),
                    _nav_item("nav.settings", "auth.change_password", active_prefix="auth.change_password"),
                ],
            }
        ]

    if current_user.is_ops_admin():
        return [
            {
                "title_key": "nav.section_platform",
                "items": [
                    _nav_item("nav.dashboard", "ops.dashboard", active_prefix="ops.dashboard"),
                    _nav_item("nav.businesses", "ops.businesses", active_prefix="ops.business"),
                    _nav_item("nav.users", "ops.users", active_prefix="ops.users"),
                    _nav_item("nav.activity_logs", "ops.activity_logs", active_prefix="ops.activity_logs"),
                    _nav_item("nav.login_attempts", "ops.login_attempts", active_prefix="ops.login_attempts"),
                ],
            }
        ]

    if current_user.is_biz_admin():
        return [
            {
                "title_key": "nav.section_platform",
                "items": [
                    _nav_item("nav.dashboard", "biz.dashboard", active_prefix="biz.dashboard"),
                    _nav_item("nav.subscriptions", "biz.subscriptions", active_prefix="biz.subscription"),
                    _nav_item("nav.payments", "biz.payments", active_prefix="biz.payments"),
                    _nav_item("nav.revenue", "biz.revenue", active_prefix="biz.revenue"),
                    _nav_item("nav.reports", "biz.reports", active_prefix="biz.reports"),
                ],
            }
        ]

    if current_user.is_owner():
        return [
            {
                "title_key": "nav.section_core",
                "items": [
                    _nav_item("nav.dashboard", "owner.dashboard", active_prefix="owner.dashboard"),
                    _nav_item("nav.categories", "owner.categories", active_prefix="owner.categor"),
                    _nav_item("nav.products", "owner.products", active_prefix="owner.product"),
                    _nav_item("nav.inventory", "owner.inventory", active_prefix="owner.inventory"),
                    _nav_item("nav.sales", "owner.sales", active_prefix="owner.sale"),
                    _nav_item("nav.customers", "owner.customers", active_prefix="owner.customer"),
                    _nav_item("nav.credits", "owner.credits", active_prefix="owner.credit"),
                    _nav_item("nav.repayments", "owner.repayments", active_prefix="owner.repayment"),
                ],
            },
            {
                "title_key": "nav.section_reports",
                "items": [
                    _nav_item("nav.sales_report", "owner.sales_report", active_prefix="owner.sales_report"),
                    _nav_item("nav.profit_report", "owner.profit_report", active_prefix="owner.profit_report"),
                    _nav_item("nav.credit_report", "owner.credit_report", active_prefix="owner.credit_report"),
                    _nav_item("nav.inventory_report", "owner.inventory_report", active_prefix="owner.inventory_report"),
                    _nav_item("nav.low_stock", "owner.report_low_stock", active_prefix="owner.report_low_stock"),
                    _nav_item("nav.near_expiry", "owner.report_near_expiry", active_prefix="owner.report_near_expiry"),
                    _nav_item("nav.expired_stock", "owner.report_expired", active_prefix="owner.report_expired"),
                    _nav_item(
                        "nav.customer_ledgers",
                        "owner.customer_ledgers_report",
                        active_prefix="owner.customer_ledgers_report",
                    ),
                ],
            },
            {
                "title_key": "nav.section_settings",
                "items": [
                    _nav_item("nav.subscription", "owner.subscription", active_prefix="owner.subscription"),
                    _nav_item("nav.settings", "owner.settings", active_prefix="owner.settings"),
                ],
            },
        ]

    return [
        {
            "title_key": "nav.section_core",
            "items": [
                _nav_item("nav.dashboard", "staff.dashboard", active_prefix="staff.dashboard"),
                _nav_item("nav.new_sale", "staff.sale_new", active_prefix="staff.sale_new"),
                _nav_item("nav.sales", "staff.sales", active_prefix="staff.sale"),
                _nav_item("nav.products", "staff.products", active_prefix="staff.products"),
                _nav_item("nav.customers", "staff.customers", active_prefix="staff.customers"),
            ],
        }
    ]
