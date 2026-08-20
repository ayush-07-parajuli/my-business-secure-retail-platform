"""Application factory for the My Business SaaS platform."""

from __future__ import annotations

from pathlib import Path

import click
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import csrf, db, login_manager
from app.forms import LogoutForm
from app.routes import register_blueprints
from app.services import (
    create_demo_seed_data,
    create_seed_users,
    get_subscription_notice_for_user,
    run_demo_smoke_flow,
)
from app.utils import build_navigation, format_currency
from app.utils.i18n import SUPPORTED_LANGUAGES, get_current_language, translate
from config import Config


@login_manager.user_loader
def load_user(user_id: str):
    """Load a user for Flask-Login sessions."""

    from app.models import User

    if not user_id:
        return None

    return db.session.get(User, user_id)


def create_app(config_object: type[Config] = Config) -> Flask:
    """Create and configure the Flask application."""

    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    register_extensions(app)

    # Import models before any db.create_all() calls so SQLAlchemy metadata is complete.
    from app import models  # noqa: F401

    register_blueprints(app)
    register_error_handlers(app)
    register_commands(app)
    register_shell_context(app)

    return app


def register_extensions(app: Flask) -> None:
    """Initialize Flask extensions."""

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    app.jinja_env.filters["currency"] = format_currency

    @login_manager.unauthorized_handler
    def handle_unauthorized():
        flash("Please log in to continue.", "warning")
        return redirect(url_for("auth.login", next=request.url))


def register_error_handlers(app: Flask) -> None:
    """Register HTML error handlers."""

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500


def register_commands(app: Flask) -> None:
    """Register CLI commands used during development."""

    def _handle_schema_upgrade_error(exc: Exception):
        message = (
            "The existing SQLite database appears to use an older schema. "
            "Run 'python -m flask --app run reset-db --with-seed' once to recreate it for the updated My Business version."
        )
        raise click.ClickException(message) from exc

    @app.cli.command("init-db")
    @click.option("--with-seed", is_flag=True, help="Seed demo data after creating the schema.")
    def init_db_command(with_seed: bool):
        """Initialize the SQLite database using SQLAlchemy models."""

        db.create_all()
        click.echo(f"Initialized database at {app.config['SQLALCHEMY_DATABASE_URI']}")
        if with_seed:
            try:
                seeded = create_demo_seed_data()
                click.echo(f"Seeded demo data: {seeded}")
            except (IntegrityError, OperationalError) as exc:
                db.session.rollback()
                _handle_schema_upgrade_error(exc)

    @app.cli.command("reset-db")
    @click.option("--with-seed", is_flag=True, help="Seed demo data after recreating the schema.")
    def reset_db_command(with_seed: bool):
        """Drop and recreate the database schema."""

        if not click.confirm("This will erase the current database schema. Continue?", default=False):
            click.echo("Reset cancelled.")
            return

        db.drop_all()
        db.create_all()
        click.echo(f"Reset database at {app.config['SQLALCHEMY_DATABASE_URI']}")
        if with_seed:
            seeded = create_demo_seed_data()
            click.echo(f"Seeded demo data: {seeded}")

    @app.cli.command("seed-dev")
    def seed_dev_command():
        """Create sample users and tenant data for local development."""

        db.create_all()
        try:
            created = create_seed_users()
        except (IntegrityError, OperationalError) as exc:
            db.session.rollback()
            _handle_schema_upgrade_error(exc)
        if not created:
            click.echo("Seed users already exist. Nothing new was created.")
            return

        click.echo("Created development seed accounts:")
        for label, credentials in created.items():
            click.echo(f"- {label}: {credentials}")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Create or refresh demo-ready data for thesis demonstrations."""

        db.create_all()
        try:
            summary = create_demo_seed_data()
        except (IntegrityError, OperationalError) as exc:
            db.session.rollback()
            _handle_schema_upgrade_error(exc)
        click.echo(f"Demo data ready: {summary}")

    @app.cli.command("demo-smoke")
    def demo_smoke_command():
        """Run an end-to-end smoke test for the thesis demo flow."""

        results = run_demo_smoke_flow()
        click.echo("Smoke flow completed:")
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            click.echo(f"- [{status}] {result.step}: {result.detail}")


def register_shell_context(app: Flask) -> None:
    """Expose key objects in `flask shell`."""

    @app.shell_context_processor
    def make_shell_context():
        from app.models import (
            AuditLog,
            Business,
            Category,
            Customer,
            LoginAttempt,
            Product,
            Repayment,
            Sale,
            SaleItem,
            StockBatch,
            SubscriptionPayment,
            User,
        )

        return {
            "db": db,
            "AuditLog": AuditLog,
            "Business": Business,
            "Category": Category,
            "Customer": Customer,
            "LoginAttempt": LoginAttempt,
            "Product": Product,
            "Repayment": Repayment,
            "Sale": Sale,
            "SaleItem": SaleItem,
            "StockBatch": StockBatch,
            "SubscriptionPayment": SubscriptionPayment,
            "User": User,
        }

    @app.context_processor
    def inject_template_helpers():
        def currency_for_current_user(value, business=None):
            active_business = business
            if active_business is None and current_user.is_authenticated:
                active_business = getattr(current_user, "business", None)
            symbol = getattr(active_business, "currency_symbol", "Rs.") if active_business else "Rs."
            return format_currency(value, symbol)

        return {
            "app_navigation": build_navigation(),
            "currency": currency_for_current_user,
            "logout_form": LogoutForm(),
            "supported_languages": SUPPORTED_LANGUAGES,
            "current_language": get_current_language(),
            "subscription_notice": get_subscription_notice_for_user(current_user),
            "t": translate,
        }
