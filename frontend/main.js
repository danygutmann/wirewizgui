import { basicSetup, EditorView } from "codemirror";
import { yaml } from "@codemirror/lang-yaml";
import { indentWithTab } from "@codemirror/commands";
import { keymap } from "@codemirror/view";
import YAML from "yaml";
import { insertSnippet } from "./insertion.js";
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

function addSnippetButton(snippet) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button snippet-button";
  button.textContent = snippet.label;
  button.addEventListener("click", () => {
    const source = editor.state.doc.toString();
    const cursor = editor.state.selection.main.head;
    const result = insertSnippet(source, snippet, cursor);
    if (result.error) {
      message.textContent = result.error;
      return;
    }
    setDocument(result.source);
    message.textContent = `${snippet.label} ${result.message}.`;
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

async function refreshTemplates() {
  const response = await fetch("/api/user-templates");
  if (!response.ok) return;
  const { templates } = await response.json();
  const select = $("#template-select");
  select.replaceChildren(new Option("Beispiele und eigene Vorlagen …", ""));
  select.add(new Option("WireViz-Beispielkabel", "example"));
  for (const template of templates) {
    select.add(new Option(template.name, template.name));
  }
}

$("#template-select").addEventListener("change", async () => {
  const name = $("#template-select").value;
  if (!name) return;
  if (name === "example") {
    setDocument(example);
    message.textContent = "Beispielkabel geladen.";
    return;
  }
  const response = await fetch(`/api/user-templates/${encodeURIComponent(name)}`);
  const result = await response.json();
  if (!response.ok) {
    message.textContent = result.message || "Vorlage konnte nicht geladen werden.";
    return;
  }
  setDocument(result.yaml);
  message.textContent = `Vorlage „${result.name}“ geladen.`;
});

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
refreshTemplates();

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
