EXAMPLE = """metadata:
  title: Example cable
  pn: EX-001
  notes: Replace the example values with your own details.

connectors:
  X1:
    type: D-Sub
    subtype: female
    pinlabels: [GND, TX, RX]
  X2:
    type: Molex KK 254
    subtype: female
    pinlabels: [GND, RX, TX]

cables:
  W1:
    gauge: 0.25 mm2
    length: 0.2
    color_code: DIN
    wirecount: 3
    shield: true

connections:
  -
    - X1: [1, 2, 3]
    - W1: [1, 2, 3]
    - X2: [1, 3, 2]
"""

SNIPPETS = [
    {
        "id": "connector",
        "label": "Stecker",
        "section": "connectors",
        "text": """connectors:
  X3:
    type: REPLACE_ME
    subtype: female
    pinlabels: [PIN1, PIN2]
""",
    },
    {
        "id": "cable",
        "label": "Kabel",
        "section": "cables",
        "text": """cables:
  W2:
    gauge: 0.25 mm2
    length: 1
    wirecount: 2
    color_code: DIN
""",
    },
    {
        "id": "connection",
        "label": "Verbindung / Pinzuordnung",
        "section": "connections",
        "text": """connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
""",
    },
    {
        "id": "shield",
        "label": "Schirmung",
        "section": "cables",
        "text": """cables:
  W3:
    gauge: 0.25 mm2
    length: 1
    wirecount: 2
    shield: true

connections:
  -
    - X1: 1
    - W3: s
""",
    },
    {
        "id": "metadata",
        "label": "Metadaten",
        "section": "metadata",
        "text": """metadata:
  title: REPLACE_ME
  pn: REPLACE_ME
  notes: REPLACE_ME
""",
    },
    {
        "id": "example",
        "label": "Vollständiges Beispielkabel",
        "section": None,
        "text": EXAMPLE,
    },
]
