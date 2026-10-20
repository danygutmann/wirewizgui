import os
import re
import tempfile
from pathlib import Path

from werkzeug.exceptions import BadRequest, Conflict, NotFound

PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
PROJECT_EXTENSIONS = (".yaml", ".yml")
MAX_PROJECT_BYTES = 1_048_576


def project_root(data_dir):
    root = Path(data_dir) / "projects"
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    resolved = root.resolve()
    if resolved.parent != Path(data_dir).resolve():
        raise BadRequest("Invalid project storage directory.")
    return resolved


def template_root(data_dir):
    root = Path(data_dir) / "templates"
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    resolved = root.resolve()
    if resolved.parent != Path(data_dir).resolve():
        raise BadRequest("Invalid template storage directory.")
    return resolved


def project_path(data_dir, name):
    if not isinstance(name, str) or not name or len(name) > 100:
        raise BadRequest("Enter a project name of up to 100 characters.")
    if name.lower().endswith(PROJECT_EXTENSIONS):
        name = name.rsplit(".", 1)[0]
    if not PROJECT_NAME.fullmatch(name) or name in {".", ".."}:
        raise BadRequest("Project names may contain letters, numbers, spaces, dots, _ and - only.")
    root = project_root(data_dir)
    target = root / f"{name}.yaml"
    if target.parent.resolve() != root or target.is_symlink():
        raise BadRequest("Project path is not allowed.")
    return target


def save_project(data_dir, name, source):
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_PROJECT_BYTES:
        raise BadRequest("Project content exceeds the 1 MiB limit.")
    target = project_path(data_dir, name)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".wireviz-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(source)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return target.name


def load_project(data_dir, name):
    target = project_path(data_dir, name)
    try:
        if not target.is_file():
            raise NotFound("Project not found.")
        if target.stat().st_size > MAX_PROJECT_BYTES:
            raise BadRequest("Project exceeds the 1 MiB limit.")
        return target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise NotFound("Project not found.") from exc
    except UnicodeDecodeError as exc:
        raise BadRequest("Project is not valid UTF-8 text.") from exc


def list_projects(data_dir):
    root = project_root(data_dir)
    projects = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in PROJECT_EXTENSIONS:
            continue
        if path.stat().st_size <= MAX_PROJECT_BYTES:
            projects.append({"name": path.stem, "updated": int(path.stat().st_mtime)})
    return sorted(projects, key=lambda item: item["name"].casefold())


def list_user_templates(data_dir):
    root = template_root(data_dir)
    templates = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in PROJECT_EXTENSIONS:
            continue
        if PROJECT_NAME.fullmatch(path.stem) and path.stat().st_size <= MAX_PROJECT_BYTES:
            templates.append({"name": path.name})
    return sorted(templates, key=lambda item: item["name"].casefold())


def load_user_template(data_dir, name):
    if not isinstance(name, str) or len(name) > 105 or "/" in name or "\\" in name:
        raise BadRequest("Template path is not allowed.")
    path = template_root(data_dir) / name
    if (
        Path(name).suffix.lower() not in PROJECT_EXTENSIONS
        or not PROJECT_NAME.fullmatch(Path(name).stem)
        or path.is_symlink()
        or path.resolve().parent != path.parent
    ):
        raise BadRequest("Template path is not allowed.")
    try:
        if not path.is_file():
            raise NotFound("Template not found.")
        if path.stat().st_size > MAX_PROJECT_BYTES:
            raise BadRequest("Template exceeds the 1 MiB limit.")
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise NotFound("Template not found.") from exc
    except UnicodeDecodeError as exc:
        raise BadRequest("Template is not valid UTF-8 text.") from exc
