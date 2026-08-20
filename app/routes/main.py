"""Top-level public routes."""

from flask import Blueprint, jsonify, redirect, url_for
from flask_login import current_user

from app.utils.auth import redirect_to_dashboard


main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    """Redirect users to the appropriate landing page."""

    if current_user.is_authenticated:
        return redirect_to_dashboard()

    return redirect(url_for("auth.login"))


@main_bp.get("/health")
def health_check():
    """Simple health endpoint for local verification."""

    return jsonify({"status": "healthy"})
