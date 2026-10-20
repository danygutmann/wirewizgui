import YAML from "yaml";

function topLevelCursor(source, cursor) {
  const start = source.lastIndexOf("\n", cursor - 1) + 1;
  const end = source.indexOf("\n", cursor);
  const line = source.slice(start, end < 0 ? source.length : end);
  const prefix = source.slice(start, cursor);
  return prefix.trim() === "" && (line.trim() === "" || !/^\s/.test(line));
}

export function insertSnippet(source, snippet, cursor = source.length) {
  const sourceDoc = YAML.parseDocument(source, { uniqueKeys: true });
  const fragmentDoc = YAML.parseDocument(snippet.text, { uniqueKeys: true });
  if (sourceDoc.errors.length || fragmentDoc.errors.length) {
    return { error: "Der Entwurf oder der Textbaustein ist syntaktisch ungültig." };
  }
  if (snippet.id === "example" && source.trim()) {
    return { error: "Das vollständige Beispiel kann nur in einen leeren Editor eingefügt werden." };
  }
  if (!sourceDoc.contents) return { source: snippet.text, message: "eingefügt" };
  if (!YAML.isMap(sourceDoc.contents) || !YAML.isMap(fragmentDoc.contents)) {
    return { error: "Der Textbaustein kann in diesem YAML-Dokument nicht sicher zusammengeführt werden." };
  }

  const rootPairs = sourceDoc.contents.items;
  for (const incoming of fragmentDoc.contents.items) {
    const key = String(incoming.key?.value ?? "");
    const existing = rootPairs.find((item) => String(item.key?.value ?? "") === key);
    if (!existing) {
      rootPairs.push(incoming);
      continue;
    }
    const currentValue = existing.value;
    const incomingValue = incoming.value;
    if (YAML.isMap(currentValue) && YAML.isMap(incomingValue)) {
      const existingKeys = new Set(currentValue.items.map((pair) => String(pair.key?.value ?? "")));
      if (incomingValue.items.some((pair) => existingKeys.has(String(pair.key?.value ?? "")))) {
        return { error: `Der Abschnitt „${key}“ enthält bereits einen gleichnamigen Eintrag. Es wurde nichts geändert.` };
      }
      currentValue.items.push(...incomingValue.items);
    } else if (YAML.isSeq(currentValue) && YAML.isSeq(incomingValue)) {
      currentValue.items.push(...incomingValue.items);
    } else {
      return { error: `Der Abschnitt „${key}“ hat eine andere Struktur; es wurde nichts geändert.` };
    }
  }

  const hasExistingSection = fragmentDoc.contents.items.some((incoming) =>
    sourceDoc.contents.items.some((item) => item !== incoming && String(item.key?.value ?? "") === String(incoming.key?.value ?? "")));
  if (!hasExistingSection && !topLevelCursor(source, cursor)) {
    return { error: "Bitte den Cursor an einen YAML-Abschnittsanfang oder in eine leere Zeile auf oberster Ebene setzen." };
  }
  return {
    source: sourceDoc.toString(),
    message: hasExistingSection ? "sicher in vorhandene Abschnitte eingefügt" : "eingefügt",
  };
}
