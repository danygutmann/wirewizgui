import errno
import os
import re
import stat
import tempfile
from pathlib import Path

from werkzeug.exceptions import BadRequest, NotFound

PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
PROJECT_EXTENSIONS = (".yaml", ".yml")
MAX_PROJECT_BYTES = 1_048_576


def project_root(data_dir):
    root = Path(data_dir) / "projects"
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    if root.is_symlink():
        raise BadRequest("Project storage directory must not be a symlink.")
    resolved = root.resolve()
    if resolved.parent != Path(data_dir).resolve():
        raise BadRequest("Invalid project storage directory.")
    return resolved


def template_root(data_dir):
    root = Path(data_dir) / "templates"
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    if root.is_symlink():
        raise BadRequest("Template storage directory must not be a symlink.")
    resolved = root.resolve()
    if resolved.parent != Path(data_dir).resolve():
        raise BadRequest("Invalid template storage directory.")
    return resolved


def project_path(data_dir, name, strip_extension=True):
    if not isinstance(name, str) or not name or len(name) > 100:
        raise BadRequest("Enter a project name of up to 100 characters.")
    if strip_extension:
        if name.lower().endswith(PROJECT_EXTENSIONS):
            name = name.rsplit(".", 1)[0]
        elif Path(name).suffix:
            raise BadRequest("Projects must use the .yaml or .yml extension.")
    if not PROJECT_NAME.fullmatch(name) or name in {".", ".."}:
        raise BadRequest("Project names may contain letters, numbers, spaces, dots, _ and - only.")
    root = project_root(data_dir)
    target = root / f"{name}.yaml"
    if target.parent.resolve() != root or target.is_symlink():
        raise BadRequest("Project path is not allowed.")
    return target


def save_project(data_dir, name, source):
    try:
        encoded = source.encode("utf-8") if isinstance(source, str) else b""
    except UnicodeEncodeError as exc:
        raise BadRequest("Project content must be valid UTF-8 text.") from exc
    if not isinstance(source, str):
        raise BadRequest("Project content must be text.")
    if len(encoded) > MAX_PROJECT_BYTES:
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
    target = project_path(data_dir, name, strip_extension=False)
    return _read_text(target, "Project")


def _read_text(path, kind):
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise BadRequest(f"{kind} must be a regular file.")
            if details.st_size > MAX_PROJECT_BYTES:
                raise BadRequest(f"{kind} exceeds the 1 MiB limit.")
            content = source.read(MAX_PROJECT_BYTES + 1)
        if len(content) > MAX_PROJECT_BYTES:
            raise BadRequest(f"{kind} exceeds the 1 MiB limit.")
        return content.decode("utf-8")
    except FileNotFoundError as exc:
        raise NotFound(f"{kind} not found.") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise BadRequest(f"{kind} path is not allowed.") from exc
        raise
    except UnicodeDecodeError as exc:
        raise BadRequest(f"{kind} is not valid UTF-8 text.") from exc


def list_projects(data_dir):
    root = project_root(data_dir)
    projects = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".yaml":
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
    return _read_text(path, "Template")
