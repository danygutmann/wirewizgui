import json
import os
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, session
from werkzeug.exceptions import BadRequest

from wireviz_gui.storage import (
    list_projects,
    list_user_templates,
    load_project,
    load_user_template,
    save_project,
)
from wireviz_gui.validation import validate_yaml
from wireviz_gui.wireviz_api import ApiFailure, ApiTimeout, render_yaml

api = Blueprint("gui", __name__)
MAX_YAML_BYTES = 1_048_576
SNIPPET_DATA = json.loads(Path(__file__).with_name("snippets.json").read_text(encoding="utf-8"))
EXAMPLE = SNIPPET_DATA["example"]
SNIPPETS = SNIPPET_DATA["snippets"]


def _json_object():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise BadRequest("Expected a JSON object.")
    return payload


def _source(payload):
    source = payload.get("yaml")
    if not isinstance(source, str):
        raise BadRequest("The YAML document must be text.")
    if len(source.encode("utf-8")) > MAX_YAML_BYTES:
        raise BadRequest("YAML content exceeds the 1 MiB limit.")
    return source


def _session_cache():
    cache = current_app.extensions["wireviz_render_cache"]
    render_id = session.get("render_id")
    if render_id is None:
        render_id = uuid.uuid4().hex
        session["render_id"] = render_id
    return cache, render_id


@api.after_app_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'",
    )
    return response


@api.get("/")
def index():
    return render_template("index.html", example=EXAMPLE)


@api.get("/healthz")
def health():
    return "ok", 200, {"Content-Type": "text/plain; charset=utf-8"}


@api.get("/api/templates")
def templates():
    return jsonify({"example": EXAMPLE, "snippets": SNIPPETS})


@api.post("/api/validate")
def validate():
    source = _source(_json_object())
    _, error = validate_yaml(source)
    if error:
        return jsonify({"valid": False, "error": error}), 400
    return jsonify({"valid": True})


@api.post("/api/render")
def render():
    source = _source(_json_object())
    _, error = validate_yaml(source)
    if error:
        return jsonify({"error": "YAML syntax error.", "details": error}), 400

    try:
        svg = render_yaml(source, current_app.config.get("WIREVIZ_API_URL") or os.getenv("WIREVIZ_API_URL", ""))
    except ApiTimeout as exc:
        return jsonify({"error": str(exc)}), 504
    except ApiFailure as exc:
        return jsonify({"error": str(exc)}), 502

    cache, render_id = _session_cache()
    cache[render_id] = svg.decode("utf-8")
    while len(cache) > 32:
        cache.pop(next(iter(cache)))
    return jsonify({"svg": cache[render_id], "filename": "wireviz-diagram.svg"})


@api.get("/api/render/last")
def last_render():
    cache = current_app.extensions["wireviz_render_cache"]
    svg = cache.get(session.get("render_id"))
    if svg is None:
        return jsonify({"error": "No successful render is available yet."}), 404
    return jsonify({"svg": svg, "filename": "wireviz-diagram.svg"})


@api.get("/api/projects")
def projects():
    return jsonify({"projects": list_projects(current_app.config["DATA_DIR"])})


@api.post("/api/projects")
def save():
    payload = _json_object()
    source = _source(payload)
    name = payload.get("name")
    filename = save_project(current_app.config["DATA_DIR"], name, source)
    return jsonify({"name": filename}), 201


@api.get("/api/projects/<name>")
def load(name):
    return jsonify({"name": name, "yaml": load_project(current_app.config["DATA_DIR"], name)})


@api.get("/api/user-templates")
def user_templates():
    return jsonify({"templates": list_user_templates(current_app.config["DATA_DIR"])})


@api.get("/api/user-templates/<name>")
def user_template(name):
    return jsonify({"name": name, "yaml": load_user_template(current_app.config["DATA_DIR"], name)})
