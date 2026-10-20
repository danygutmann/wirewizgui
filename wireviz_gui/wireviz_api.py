import re
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

from defusedxml import ElementTree

API_TIMEOUT = 45
MAX_SVG_BYTES = 8 * 1024 * 1024
SVG_TAGS = {
    "svg", "g", "path", "polygon", "polyline", "line", "rect", "circle",
    "ellipse", "text", "tspan", "title", "desc", "defs", "clipPath",
    "linearGradient", "radialGradient", "stop",
}
SVG_ATTRIBUTES = {
    "xmlns", "viewBox", "width", "height", "version", "preserveAspectRatio",
    "id", "class", "x", "y", "cx", "cy", "r", "rx", "ry", "x1", "y1",
    "x2", "y2", "points", "d", "transform", "fill", "fill-rule", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
    "font-family", "font-size", "font-weight", "text-anchor",
    "dominant-baseline", "opacity", "fill-opacity", "stroke-opacity",
    "offset", "stop-color", "stop-opacity", "clip-path",
}


class ApiFailure(Exception):
    pass


class ApiTimeout(ApiFailure):
    pass


def sanitize_svg(payload):
    if len(payload) > MAX_SVG_BYTES:
        raise ApiFailure("The render result exceeds the 8 MiB limit.")
    try:
        root = ElementTree.fromstring(payload, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        raise ApiFailure("The WireViz API returned invalid SVG data.") from exc

    local_name = root.tag.rsplit("}", 1)[-1]
    if local_name != "svg":
        raise ApiFailure("The WireViz API did not return an SVG image.")

    def clean(element):
        element.tag = element.tag.rsplit("}", 1)[-1]
        for name, value in list(element.attrib.items()):
            attribute = name.rsplit("}", 1)[-1]
            if attribute not in SVG_ATTRIBUTES or attribute.lower().startswith("on"):
                del element.attrib[name]
                continue
            if attribute in {"fill", "stroke", "clip-path"}:
                safe_color = re.fullmatch(r"#[0-9a-fA-F]{3,8}|[A-Za-z]+|none|url\(#[\w.-]+\)", value)
                if not safe_color:
                    del element.attrib[name]
            elif len(value) > 2048 or any(ord(char) < 32 for char in value):
                del element.attrib[name]
        for child in list(element):
            child_name = child.tag.rsplit("}", 1)[-1]
            if child_name not in SVG_TAGS:
                element.remove(child)
            else:
                clean(child)

    clean(root)
    root.set("xmlns", "http://www.w3.org/2000/svg")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def render_yaml(yaml_source, api_url):
    if not api_url:
        raise ApiFailure("WIREVIZ_API_URL is not configured.")
    parsed_url = urlsplit(api_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ApiFailure("WIREVIZ_API_URL must be an HTTP or HTTPS URL.")
    boundary = f"----WireVizGUI{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="yml_file"; filename="cable.yaml"\r\n'
        "Content-Type: application/yaml; charset=utf-8\r\n\r\n"
    ).encode("ascii") + yaml_source.encode("utf-8") + f"\r\n--{boundary}--\r\n".encode("ascii")
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/render",
        data=body,
        headers={
            "Accept": "image/svg+xml",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=API_TIMEOUT) as response:
            content_type = response.headers.get_content_type()
            if response.status != 200:
                raise ApiFailure(f"WireViz API returned HTTP {response.status}.")
            if content_type != "image/svg+xml":
                raise ApiFailure("WireViz API response was not an SVG image.")
            payload = response.read(MAX_SVG_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", errors="replace").strip()
        message = f"WireViz API returned HTTP {exc.code}."
        if detail:
            message += f" {detail}"
        raise ApiFailure(message) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
            raise ApiTimeout("The WireViz API request timed out.") from exc
        if isinstance(exc, TimeoutError):
            raise ApiTimeout("The WireViz API request timed out.") from exc
        raise ApiFailure("The WireViz API could not be reached.") from exc
    except OSError as exc:
        raise ApiFailure("The WireViz API could not be reached.") from exc

    return sanitize_svg(payload)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None
