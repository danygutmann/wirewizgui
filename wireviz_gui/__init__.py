import os

from flask import Flask

from wireviz_gui.routes import api


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATA_DIR="/data",
        MAX_CONTENT_LENGTH=1_048_576,
        SECRET_KEY=os.getenv("SECRET_KEY", "development-only-change-me"),
        WIREVIZ_API_URL=os.getenv("WIREVIZ_API_URL", ""),
    )
    if test_config:
        app.config.update(test_config)

    app.register_blueprint(api)
    app.extensions["wireviz_render_cache"] = {}
    return app
