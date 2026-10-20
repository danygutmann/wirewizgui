import os
import unittest

from wireviz_gui.wireviz_api import render_yaml


@unittest.skipUnless(
    os.getenv("WIREVIZ_INTEGRATION") == "1" and os.getenv("WIREVIZ_API_URL"),
    "Set WIREVIZ_INTEGRATION=1 and WIREVIZ_API_URL to run the live API check.",
)
class WireVizIntegrationTests(unittest.TestCase):
    def test_example_renders_with_live_wireviz_web_api(self):
        source = """metadata:
  title: Integration smoke test
connectors:
  X1:
    type: D-Sub
    subtype: female
    pinlabels: [GND, TX]
cables:
  W1:
    gauge: 0.25 mm2
    wirecount: 2
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
"""
        svg = render_yaml(source, os.environ["WIREVIZ_API_URL"])
        self.assertIn(b"<svg", svg)


if __name__ == "__main__":
    unittest.main()
