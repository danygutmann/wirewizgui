import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import YAML from "yaml";

import { insertSnippet } from "./insertion.js";

const templateData = JSON.parse(
  await readFile(new URL("../wireviz_gui/snippets.json", import.meta.url), "utf8"),
);
const base = `metadata:
  revision: 1
connectors:
  X1:
    type: D-Sub
cables:
  W1:
    wirecount: 2
connections: []
`;

test("each configured text snippet inserts as valid YAML", () => {
  for (const snippet of templateData.snippets) {
    const result = insertSnippet("", snippet, 0);
    assert.ok(result.source, `${snippet.id} should insert`);
    assert.deepEqual(YAML.parseDocument(result.source).errors, []);
  }
});

test("existing top-level sections merge without creating duplicate keys", () => {
  for (const snippet of templateData.snippets.filter(({ id }) => id !== "example")) {
    const result = insertSnippet(base, snippet);
    assert.ok(result.source, `${snippet.id}: ${result.error}`);
    const parsed = YAML.parseDocument(result.source);
    assert.deepEqual(parsed.errors, []);
    const rootKeys = parsed.contents.items.map(({ key }) => key.value);
    assert.equal(new Set(rootKeys).size, rootKeys.length);
  }
});

test("entry collisions and full examples never overwrite existing content", () => {
  const original = base.replace(
    "    type: D-Sub",
    "    type: D-Sub\n  X3:\n    type: Existing",
  );
  const connector = templateData.snippets.find(({ id }) => id === "connector");
  const rejected = insertSnippet(original, connector);
  assert.match(rejected.error, /gleichnamigen Eintrag/);
  assert.equal(rejected.source, undefined);

  const fullExample = templateData.snippets.find(({ id }) => id === "example");
  assert.match(insertSnippet(base, fullExample).error, /leeren Editor/);
});

test("new root sections require a safe top-level cursor position", () => {
  const snippet = templateData.snippets.find(({ id }) => id === "metadata");
  const result = insertSnippet("options:\n  color_mode: FULL\n  \n", snippet, 27);
  assert.match(result.error, /Cursor an einen YAML-Abschnittsanfang/);
});

test("simple complete example can be inserted in an empty editor", () => {
  const snippet = templateData.snippets.find(({ id }) => id === "example");
  const result = insertSnippet("", snippet, 0);
  assert.equal(result.source, templateData.example);
});
