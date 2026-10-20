import os

from flask import Flask

from wireviz_gui.routes import api


def create_app(test_config=None):
    secret_key = os.getenv("SECRET_KEY")
    if os.getenv("APP_MODE") == "production" and secret_key in {
        None,
        "",
        "REPLACE_WITH_A_LONG_RANDOM_SECRET",
        "development-only-change-me",
    }:
        raise RuntimeError("Set SECRET_KEY to a unique random value before running in production.")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATA_DIR="/data",
        MAX_CONTENT_LENGTH=1_048_576,
        SECRET_KEY=secret_key or "development-only-change-me",
        WIREVIZ_API_URL=os.getenv("WIREVIZ_API_URL", ""),
    )
    if test_config:
        app.config.update(test_config)

    app.register_blueprint(api)
    app.extensions["wireviz_render_cache"] = {}
    return app
