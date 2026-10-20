import { basicSetup, EditorView } from "codemirror";
import { yaml } from "@codemirror/lang-yaml";
import { indentWithTab } from "@codemirror/commands";
import { keymap } from "@codemirror/view";
import YAML from "yaml";
import "./style.css";

const $ = (selector) => document.querySelector(selector);
const example = $("#example-yaml").value.trimStart();
const status = $("#syntax-state");
const errors = $("#syntax-errors");
const message = $("#editor-message");
const renderStatus = $("#render-status");
const renderButton = $("#render-button");
const img = $("#diagram");
const emptyPreview = $("#empty-preview");
const snippetList = $("#snippet-list");
const projectSelect = $("#project-select");
let initialSource = example;
let currentSvg = "";
let validationTimer;
let objectUrl;

function validate(source) {
  const document = YAML.parseDocument(source, { uniqueKeys: true, prettyErrors: true });
  if (!source.trim()) {
    return [{ message: "Das YAML-Dokument ist leer.", line: 1, column: 1 }];
  }
  return document.errors.map((error) => {
    const location = error.linePos?.[0];
    return {
      message: error.message,
      line: location?.line ?? 1,
      column: location?.col ?? 1,
    };
  });
}

function showValidation() {
  const problems = validate(editor.state.doc.toString());
  errors.replaceChildren();
  if (problems.length) {
    status.textContent = "Syntaxfehler";
    status.className = "state-pill invalid";
    for (const problem of problems.slice(0, 5)) {
      const row = document.createElement("p");
      row.textContent = `Zeile ${problem.line}, Spalte ${problem.column}: ${problem.message}`;
      errors.append(row);
    }
    renderButton.disabled = true;
  } else {
    status.textContent = "YAML gültig";
    status.className = "state-pill valid";
    renderButton.disabled = false;
  }
}

const editor = new EditorView({
  doc: example,
  extensions: [
    basicSetup,
    yaml(),
    keymap.of([indentWithTab]),
    EditorView.lineWrapping,
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        message.textContent = "";
        clearTimeout(validationTimer);
        validationTimer = setTimeout(showValidation, 120);
      }
    }),
  ],
  parent: $("#editor"),
});
showValidation();

function setDocument(source) {
  editor.dispatch({
    changes: { from: 0, to: editor.state.doc.length, insert: source },
    selection: { anchor: 0 },
  });
  showValidation();
}

function safeTopLevelInsertion(source, cursor) {
  const line = editor.state.doc.lineAt(cursor);
  const beforeCursor = line.text.slice(0, cursor - line.from);
  return beforeCursor.trim() === "" && (line.text.trim() === "" || !/^\s/.test(line.text));
}

function appendTemplate(source, snippet) {
  const sourceDoc = YAML.parseDocument(source, { uniqueKeys: true });
  const fragmentDoc = YAML.parseDocument(snippet.text, { uniqueKeys: true });
  if (sourceDoc.errors.length || fragmentDoc.errors.length) {
    return { error: "Der Entwurf oder der Textbaustein ist syntaktisch ungültig." };
  }
  if (!sourceDoc.contents) {
    return { source: snippet.text };
  }
  if (!YAML.isMap(sourceDoc.contents) || !YAML.isMap(fragmentDoc.contents)) {
    return { error: "Der Textbaustein kann in diesem YAML-Dokument nicht sicher zusammengeführt werden." };
  }
  for (const incoming of fragmentDoc.contents.items) {
    const key = String(incoming.key?.value ?? "");
    const existing = sourceDoc.contents.items.find((item) => String(item.key?.value ?? "") === key);
    if (!existing) {
      sourceDoc.contents.items.push(incoming);
      continue;
    }
    if (snippet.id === "example") {
      return { error: "Das vollständige Beispiel würde vorhandene Abschnitte ersetzen. Lade es stattdessen separat." };
    }
    const currentValue = existing.value;
    const incomingValue = incoming.value;
    if (YAML.isMap(currentValue) && YAML.isMap(incomingValue)) {
      const existingKeys = new Set(currentValue.items.map((pair) => String(pair.key?.value ?? "")));
      const collision = incomingValue.items.some((pair) => existingKeys.has(String(pair.key?.value ?? "")));
      if (collision) {
        return { error: `Der Abschnitt „${key}“ enthält bereits einen gleichnamigen Eintrag. Es wurde nichts geändert.` };
      }
      currentValue.items.push(...incomingValue.items);
    } else if (YAML.isSeq(currentValue) && YAML.isSeq(incomingValue)) {
      currentValue.items.push(...incomingValue.items);
    } else {
      return { error: `Der Abschnitt „${key}“ hat eine andere Struktur; es wurde nichts geändert.` };
    }
  }
  return { source: sourceDoc.toString() };
}

function addSnippetButton(snippet) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button snippet-button";
  button.textContent = snippet.label;
  button.addEventListener("click", () => {
    const source = editor.state.doc.toString();
    const cursor = editor.state.selection.main.head;
    const roots = YAML.parseDocument(snippet.text).contents;
    const keys = YAML.isMap(roots) ? roots.items.map((item) => String(item.key?.value)) : [];
    const existing = YAML.parseDocument(source).contents;
    const hasCollision = YAML.isMap(existing) && keys.some((key) =>
      existing.items.some((item) => String(item.key?.value) === key));

    if (!hasCollision) {
      if (!safeTopLevelInsertion(source, cursor)) {
        message.textContent = "Bitte den Cursor an einen YAML-Abschnittsanfang oder in eine leere Zeile auf oberster Ebene setzen.";
        return;
      }
      const insertion = snippet.text.trimEnd();
      const before = source.slice(0, cursor);
      const after = source.slice(cursor);
      const prefix = before && !before.endsWith("\n") ? "\n" : "";
      const suffix = after && !after.startsWith("\n") ? "\n" : "";
      editor.dispatch({
        changes: { from: cursor, insert: `${prefix}${insertion}\n${suffix}` },
        selection: { anchor: cursor + prefix.length + insertion.length + 1 },
      });
      message.textContent = `${snippet.label} eingefügt.`;
      showValidation();
      return;
    }

    const merged = appendTemplate(source, snippet);
    if (merged.error) {
      message.textContent = merged.error;
      return;
    }
    setDocument(merged.source);
    message.textContent = `${snippet.label} sicher in vorhandene Abschnitte eingefügt.`;
  });
  snippetList.append(button);
}

fetch("/api/templates")
  .then((response) => response.json())
  .then(({ snippets }) => snippets.forEach(addSnippetButton))
  .catch(() => { message.textContent = "Textbausteine konnten nicht geladen werden."; });

async function refreshProjects() {
  const response = await fetch("/api/projects");
  if (!response.ok) return;
  const { projects } = await response.json();
  projectSelect.replaceChildren(new Option("Gespeicherte Projekte …", ""));
  for (const project of projects) {
    projectSelect.add(new Option(project.name, project.name));
  }
}

projectSelect.addEventListener("change", async () => {
  if (!projectSelect.value) return;
  const response = await fetch(`/api/projects/${encodeURIComponent(projectSelect.value)}`);
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.message || "Projekt konnte nicht geladen werden.";
    return;
  }
  setDocument(result.yaml);
  $("#project-name").value = result.name;
  message.textContent = `Projekt „${result.name}“ geladen.`;
});

$("#save-project").addEventListener("click", async () => {
  const name = $("#project-name").value.trim();
  if (!name) {
    message.textContent = "Bitte zuerst einen Projektnamen eingeben.";
    return;
  }
  const exists = [...projectSelect.options].some((option) => option.value === name);
  if (exists && !window.confirm(`Projekt „${name}“ überschreiben?`)) return;
  const response = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, yaml: editor.state.doc.toString() }),
  });
  const result = await response.json();
  message.textContent = response.ok ? `Projekt „${result.name}“ gespeichert.` : result.message || "Speichern fehlgeschlagen.";
  if (response.ok) await refreshProjects();
});

projectSelect.addEventListener("focus", refreshProjects);
refreshProjects();

$("#load-example").addEventListener("click", () => {
  setDocument(example);
  message.textContent = "Beispielkabel geladen.";
});
$("#reset-editor").addEventListener("click", () => {
  setDocument(initialSource);
  message.textContent = "Ausgangszustand wiederhergestellt.";
});
$("#download-yaml").addEventListener("click", () => {
  const blob = new Blob([editor.state.doc.toString()], { type: "text/yaml;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "wireviz-project.yaml";
  link.click();
  URL.revokeObjectURL(link.href);
});

$("#open-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 1_048_576) {
    message.textContent = "Datei überschreitet das Limit von 1 MiB.";
    event.target.value = "";
    return;
  }
  setDocument(await file.text());
  $("#project-name").value = file.name.replace(/\.(yaml|yml)$/i, "");
  message.textContent = `Datei „${file.name}“ geladen.`;
  event.target.value = "";
});

renderButton.addEventListener("click", async () => {
  renderButton.classList.add("loading");
  renderButton.disabled = true;
  renderStatus.textContent = "WireViz rendert das Diagramm …";
  try {
    const response = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yaml: editor.state.doc.toString() }),
    });
    const result = await response.json();
    if (!response.ok) {
      renderStatus.textContent = result.details
        ? `YAML-Fehler in Zeile ${result.details.line}, Spalte ${result.details.column}: ${result.details.message}`
        : result.error || "Rendern fehlgeschlagen. Das letzte Ergebnis bleibt erhalten.";
      return;
    }
    showDiagram(result.svg);
    renderStatus.textContent = "Diagramm erfolgreich gerendert.";
  } catch {
    renderStatus.textContent = "Die Anwendung ist nicht erreichbar. Das letzte Ergebnis bleibt erhalten.";
  } finally {
    renderButton.classList.remove("loading");
    showValidation();
  }
});

function showDiagram(svg) {
  currentSvg = svg;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  img.src = objectUrl;
  img.hidden = false;
  emptyPreview.hidden = true;
  $("#download-svg").disabled = false;
}

$("#download-svg").addEventListener("click", () => {
  if (!currentSvg) return;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([currentSvg], { type: "image/svg+xml" }));
  link.download = "wireviz-diagram.svg";
  link.click();
  URL.revokeObjectURL(link.href);
});

fetch("/api/render/last")
  .then((response) => response.ok ? response.json() : null)
  .then((result) => { if (result?.svg) showDiagram(result.svg); })
  .catch(() => {});
