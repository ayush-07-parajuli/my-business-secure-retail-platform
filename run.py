"""Application entry point for local development."""

from __future__ import annotations

from app import create_app
from config import get_config


app = create_app(get_config())


def main() -> None:
    """Run the Flask development server."""

    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
    )


if __name__ == "__main__":
    main()
