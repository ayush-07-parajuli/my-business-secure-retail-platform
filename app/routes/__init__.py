"""Blueprint registration helpers."""

from app.routes.admin import admin_bp
from app.routes.biz import biz_bp
from app.routes.auth import auth_bp
from app.routes.main import main_bp
from app.routes.ops import ops_bp
from app.routes.owner import owner_bp
from app.routes.staff import staff_bp


def register_blueprints(app) -> None:
    """Register all current blueprints on the Flask app."""

    for blueprint in (main_bp, auth_bp, admin_bp, ops_bp, biz_bp, owner_bp, staff_bp):
        app.register_blueprint(blueprint)
