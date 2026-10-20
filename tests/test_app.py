import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from werkzeug.exceptions import BadRequest

from wireviz_gui import create_app
from wireviz_gui.storage import load_project, save_project
from wireviz_gui.validation import validate_yaml
from wireviz_gui.wireviz_api import ApiFailure, ApiTimeout, render_yaml, sanitize_svg


SVG = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)" viewBox="0 0 10 10">
  <script>alert(1)</script>
  <g onclick="alert(2)"><text x="1" y="5">safe</text></g>
  <foreignObject><div>unsafe</div></foreignObject>
</svg>"""
VALID_YAML = "connectors: {}\n"


class FakeResponse:
    status = 200

    def __init__(self, body=SVG, content_type="image/svg+xml"):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body[:size]


class WireVizGuiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "DATA_DIR": self.temporary.name,
                "SECRET_KEY": "test-only-secret",
                "WIREVIZ_API_URL": "http://wireviz-web:3005",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary.cleanup()

    def test_application_starts_and_serves_local_editor_assets(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/static/dist/app.js", response.data)
        self.assertNotIn(b"cdn.", response.data)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_yaml_validation_reports_syntax_and_duplicate_key_locations(self):
        self.assertEqual(self.client.post("/api/validate", json={"yaml": VALID_YAML}).status_code, 200)
        response = self.client.post("/api/validate", json={"yaml": "connectors: [\n"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"]["line"], 2)
        duplicate = self.client.post(
            "/api/validate", json={"yaml": "connectors: {}\nconnectors: {}\n"}
        )
        self.assertEqual(duplicate.json["error"]["line"], 2)
        self.assertIn("duplicate key", duplicate.json["error"]["message"])

    def test_non_mapping_yaml_is_rejected(self):
        _, error = validate_yaml("- item\n")
        self.assertEqual(error["line"], 1)
        self.assertIn("top-level mapping", error["message"])

    def test_all_shipped_snippets_are_valid_yaml(self):
        data = json.loads(
            (Path(__file__).parents[1] / "wireviz_gui" / "snippets.json").read_text()
        )
        for snippet in data["snippets"]:
            with self.subTest(snippet=snippet["id"]):
                _, error = validate_yaml(snippet["text"])
                self.assertIsNone(error)
        _, error = validate_yaml(data["example"])
        self.assertIsNone(error)

    def test_project_save_load_list_and_safe_overwrite(self):
        self.assertEqual(
            self.client.post("/api/projects", json={"name": "Engine harness", "yaml": VALID_YAML}).status_code,
            201,
        )
        loaded = self.client.get("/api/projects/Engine%20harness")
        self.assertEqual(loaded.json["yaml"], VALID_YAML)
        updated = "connectors:\n  X1: {}\n"
        save_project(self.temporary.name, "Engine harness.yaml", updated)
        self.assertEqual(load_project(self.temporary.name, "Engine harness"), updated)
        listing = self.client.get("/api/projects")
        self.assertEqual(listing.json["projects"][0]["name"], "Engine harness")

    def test_project_paths_and_symlinks_are_rejected(self):
        for name in ("../outside", "/tmp/outside", "nested/file", ".", ".."):
            with self.subTest(name=name):
                response = self.client.post(
                    "/api/projects", json={"name": name, "yaml": VALID_YAML}
                )
                self.assertEqual(response.status_code, 400)

        outside = Path(self.temporary.name).parent / f"{Path(self.temporary.name).name}-outside.yaml"
        outside.write_text("do not read")
        link = Path(self.temporary.name) / "projects" / "linked.yaml"
        link.symlink_to(outside)
        self.assertEqual(self.client.get("/api/projects/linked").status_code, 400)
        self.assertEqual(outside.read_text(), "do not read")

    def test_upload_limits_are_enforced(self):
        large_yaml = "x" * 1_048_577
        response = self.client.post("/api/projects", json={"name": "large", "yaml": large_yaml})
        self.assertEqual(response.status_code, 413)

    @patch("wireviz_gui.wireviz_api.urllib.request.urlopen")
    def test_wireviz_api_uses_documented_multipart_contract_and_sanitizes_svg(self, urlopen):
        urlopen.return_value = FakeResponse()
        svg = render_yaml(VALID_YAML, "http://wireviz-web:3005")
        urlopen.assert_called_once()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://wireviz-web:3005/render")
        self.assertEqual(request.get_header("Accept"), "image/svg+xml")
        self.assertIn(b'name="yml_file"; filename="cable.yaml"', request.data)
        self.assertIn(VALID_YAML.encode(), request.data)
        self.assertNotIn(b"<script", svg)
        self.assertNotIn(b"onclick", svg)
        self.assertNotIn(b"foreignObject", svg)
        self.assertIn(b"safe", svg)

    @patch("wireviz_gui.routes.render_yaml", return_value=SVG)
    def test_render_success_is_available_after_a_later_api_failure(self, render_yaml_mock):
        rendered = self.client.post("/api/render", json={"yaml": VALID_YAML})
        self.assertEqual(rendered.status_code, 200)
        self.assertIn("<svg", rendered.json["svg"])
        render_yaml_mock.side_effect = ApiFailure("API unavailable")
        failed = self.client.post("/api/render", json={"yaml": VALID_YAML})
        self.assertEqual(failed.status_code, 502)
        last = self.client.get("/api/render/last")
        self.assertEqual(last.status_code, 200)
        self.assertEqual(last.json["svg"], rendered.json["svg"])

    @patch("wireviz_gui.routes.render_yaml")
    def test_invalid_yaml_never_calls_the_render_api(self, render_yaml_mock):
        response = self.client.post("/api/render", json={"yaml": "connectors: [\n"})
        self.assertEqual(response.status_code, 400)
        render_yaml_mock.assert_not_called()

    @patch("wireviz_gui.routes.render_yaml", side_effect=ApiTimeout("slow"))
    def test_render_timeout_is_reported_as_gateway_timeout(self, _render_mock):
        response = self.client.post("/api/render", json={"yaml": VALID_YAML})
        self.assertEqual(response.status_code, 504)
        self.assertIn("slow", response.json["error"])

    @patch("wireviz_gui.wireviz_api.urllib.request.urlopen", side_effect=URLError("offline"))
    def test_unreachable_api_and_non_svg_responses_fail_cleanly(self, _urlopen):
        with self.assertRaises(ApiFailure):
            render_yaml(VALID_YAML, "http://wireviz-web:3005")
        with patch(
            "wireviz_gui.wireviz_api.urllib.request.urlopen",
            return_value=FakeResponse(content_type="text/html"),
        ):
            with self.assertRaisesRegex(ApiFailure, "not an SVG"):
                render_yaml(VALID_YAML, "http://wireviz-web:3005")

    def test_svg_with_non_svg_root_is_rejected(self):
        with self.assertRaisesRegex(ApiFailure, "did not return an SVG"):
            sanitize_svg(b"<html/>")

    def test_bad_project_names_raise_before_any_file_is_written(self):
        with self.assertRaises(BadRequest):
            save_project(self.temporary.name, "../escape", "secret")
        self.assertFalse((Path(self.temporary.name).parent / "escape.yaml").exists())


if __name__ == "__main__":
    unittest.main()
