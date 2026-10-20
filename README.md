# WireViz Cable Designer

Eine kleine Flask-Webanwendung zum Bearbeiten, Prüfen und Rendern von WireViz-Kabelbeschreibungen. Das Rendering übernimmt ausschließlich der bereits vorhandene WireViz-Web-Dienst. Editor und Stylesheets werden beim Image-Build lokal gebündelt; im Browser ist kein CDN erforderlich.

## Architektur und Datenfluss

```text
Browser / CodeMirror 6
        │ YAML, same-origin HTTP
        ▼
Flask GUI ── Syntaxprüfung ── multipart/form-data ──► WireViz-Web
        │                                               POST /render
        ├── Projekte ──► /data/projects/
        ├── eigene Vorlagen ◄── /data/templates/
        └── SVG-Sanitizer ◄── image/svg+xml
```

WireViz-Web erwartet bei `POST /render` ein `multipart/form-data`-Dateifeld namens `yml_file`. Der `Accept`-Header wählt das Ausgabeformat; die GUI fordert `image/svg+xml` an. Die API dokumentiert daneben `image/png`, `text/html`, `text/plain` und `application/json`. Die GUI zeigt und lädt nur SVG, weil es direkt als Diagramm nutzbar ist. Die API stellt außerdem `/status`, `/doc` und einen separaten PlantUML-Endpunkt bereit; die GUI verwendet diese nicht.

Diese Schnittstelle wurde anhand des offiziellen [WireViz-Web README](https://github.com/wireviz/wireviz-web/blob/main/README.rst) und der Implementierung von [`POST /render`](https://github.com/wireviz/wireviz-web/blob/main/wireviz_web/server.py) geprüft. Die Vorlagen folgen der offiziellen [WireViz-Syntax](https://github.com/wireviz/WireViz/blob/master/docs/syntax.md).

Die GUI prüft YAML im Browser zur unmittelbaren Rückmeldung und prüft jede Anfrage zusätzlich serverseitig mit PyYAML. Doppelte YAML-Schlüssel werden abgelehnt. API-SVG wird auf eine kleine SVG-Element- und Attributliste beschränkt; Skripte, Events, aktive eingebettete Inhalte und externe Links werden entfernt. Das letzte erfolgreiche Render-Ergebnis bleibt bei Renderfehlern erhalten. Es wird nur im Arbeitsspeicher zwischengespeichert und nicht dauerhaft abgelegt.

## Verzeichnisstruktur

```text
wireviz_gui/
  routes.py             Flask-HTTP-Routen
  validation.py         Serverseitige YAML-Validierung
  storage.py            Projekt- und Vorlagendateien unter DATA_DIR
  wireviz_api.py        WireViz-Web-Client und SVG-Sanitizer
  snippets.json         Beispielkabel und Einfügebausteine
  templates/index.html  UI
  static/dist/          lokal gebündeltes CodeMirror-JavaScript/CSS
frontend/               CodeMirror-Editor und UI-Styles
tests/                  Unit- und optionaler Live-API-Integrationstest
compose.yaml            Portainer/Docker-Compose-Beispiel
```

Auf der NAS wird das Volume `/volume1/docker/WireViz` nach `/data` eingebunden:

```text
/volume1/docker/WireViz/
├── projects/    gespeicherte YAML-Kabelprojekte
├── templates/   eigene YAML-Vorlagen (durch die GUI lesbar)
└── config/      reserviert für künftig notwendige Anwendungskonfiguration
```

Eigene `.yaml`- oder `.yml`-Vorlagen können in `/volume1/docker/WireViz/templates/` abgelegt und anschließend in der Vorlagenauswahl geladen werden. Die GUI liest nur direkte Dateien mit gültigem Dateinamen; Symlinks, Unterverzeichnisse und Dateien über 1 MiB werden nicht geladen. Die eingebauten Textbausteine sind unabhängig davon im Image enthalten.

## Lokal entwickeln

Voraussetzungen: Python 3.12+, Node.js 24+ und npm.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm run build
DATA_DIR="$PWD/.data" \
WIREVIZ_API_URL="http://localhost:3005" \
SECRET_KEY="lokaler-entwicklungsschluessel" \
python run.py
```

Die Flask-Entwicklungsserver-URL lautet `http://127.0.0.1:5000`. `WIREVIZ_API_URL` zeigt auf einen erreichbaren WireViz-Web-Dienst. Ohne API kann der Editor trotzdem geladen und YAML bearbeitet werden; Rendern meldet dann einen verständlichen Fehler. Die lokale Entwicklung verwendet denselben Compose-Datenaufbau unter `.data/`.

## Tests und Build

```sh
npm ci
npm test
npm run build
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Der Integrationstest gegen einen laufenden echten API-Dienst ist standardmäßig übersprungen. Zum expliziten Ausführen:

```sh
WIREVIZ_INTEGRATION=1 \
WIREVIZ_API_URL="http://localhost:3005" \
python -m unittest tests/test_integration.py -v
```

Das Dockerfile baut die lokalen Browser-Assets reproduzierbar aus der festgeschriebenen `package-lock.json` und installiert gepinnte Python-Abhängigkeiten. Es benötigt zur Laufzeit weder Node.js noch Graphviz; Graphviz und WireViz bleiben im bestehenden API-Container.

## Image in GHCR veröffentlichen

Der Workflow `.github/workflows/publish-image.yml` führt Frontend- und Python-Tests aus und baut danach das Image für GHCR.

- Ein Push auf den Standardbranch veröffentlicht Branch-, Commit- und (auf dem Standardbranch) `latest`-Tags.
- Ein Git-Tag wie `v1.0.0` veröffentlicht das Image `ghcr.io/danygutmann/wirewizgui:1.0.0`.
- Der Workflow authentifiziert sich mit dem automatisch bereitgestellten `GITHUB_TOKEN`; dafür ist kein zusätzliches Repository-Secret erforderlich. Die Workflow-Berechtigung `packages: write` ist gesetzt.
- Das erste veröffentlichte Paket kann zunächst privat sein. Für den Pull durch Portainer muss das Package in GitHub unter **Packages → Package settings → Change visibility** auf „Public“ gesetzt werden. Für ein privates Package ist stattdessen ein GHCR-Token mit `read:packages` und eine Registry-Anmeldung in Portainer erforderlich.
- Für ein Release den Tag `v1.0.0` auf den zu veröffentlichenden Commit pushen. Erst nach erfolgreichem Workflow-Lauf ist der versionierte Tag in Portainer verfügbar. Die `1.0.0` in der Compose-Vorlage ist der vorgesehene erste Release-Tag, kein Nachweis, dass das Image bereits veröffentlicht wurde.

Ein Tag kann beispielsweise mit `git tag v1.0.0` und `git push origin v1.0.0` veröffentlicht werden.

## Portainer-Installation

### 1. Gemeinsames Netzwerk für getrennte Stacks

Die Anwendung nimmt nicht an, dass Docker-Container aus unterschiedlichen Netzwerken einander über ihren Namen erreichen. Falls API und GUI in getrennten Portainer-Stacks liegen:

1. Das externe Netzwerk einmalig auf dem Docker-Host anlegen: `docker network create wireviz-shared`.
2. Den **bestehenden API-Stack** so ergänzen, dass ausschließlich der Dienst `wireviz-web` dieses externe Netzwerk ebenfalls verwendet. Die vorhandenen Image-, Port-, Umgebungs- und sonstigen API-Einstellungen beibehalten. Beispiel für die Ergänzung:

   ```yaml
   services:
     wireviz-web:
       # Bestehende API-Konfiguration unverändert lassen.
       networks:
         wireviz-shared:
           aliases:
             - wireviz-web

   networks:
     wireviz-shared:
       external: true
       name: wireviz-shared
   ```

3. Den API-Stack mit seiner bestehenden Konfiguration aktualisieren. Die API bleibt der vorhandene Dienst `wireviz-web`, bindet intern an `0.0.0.0:3005` und wird nicht durch dieses GUI-Projekt ersetzt.
4. Den GUI-Stack mit der Compose-Vorlage unten deployen. `http://wireviz-web:3005` funktioniert dann über das gemeinsame Netzwerk. Der Host-Port 3005 muss nicht veröffentlicht sein, damit Container im gemeinsamen Netzwerk kommunizieren.
5. Falls API und GUI bereits im **selben** Compose-Stack und damit im selben Netzwerk laufen, ist kein zusätzliches externes Netzwerk erforderlich. Dann kann die `networks:`-Konfiguration in der GUI-Vorlage entfernt werden.

### 2. Volume und Rechte

Vor dem Deployment auf dem NAS `/volume1/docker/WireViz` anlegen. Der Container läuft unprivilegiert als UID/GID `10001` und benötigt Schreibrechte unter `projects/`. Auf Synology die ACL/Rechte des NAS-Ordners für die numerische Container-UID passend freigeben. Keine bestehenden NAS-Daten pauschal mit `chmod -R 777` öffnen oder überschreiben. Die Anwendung erzeugt die Unterordner `projects/`, `templates/` und `config/`.

### 3. Vollständige Compose-Vorlage für den Portainer-Web-Editor

Das Image wird aus GHCR gezogen; auf der NAS ist kein lokaler Build nötig. Erforderlich ist, vor dem Deploy den Secret-Platzhalter durch einen eigenen langen zufälligen Wert zu ersetzen. Der Versions-Tag muss zuvor veröffentlicht und im GHCR-Package verfügbar sein.

```yaml
services:
  wireviz-gui:
    image: ghcr.io/danygutmann/wirewizgui:1.0.0
    container_name: wireviz-gui
    restart: unless-stopped
    ports:
      - "8087:8080"
    environment:
      WIREVIZ_API_URL: "http://wireviz-web:3005"
      DATA_DIR: "/data"
      SECRET_KEY: "REPLACE_WITH_A_LONG_RANDOM_SECRET"
    volumes:
      - /volume1/docker/WireViz:/data
    networks:
      - wireviz-shared
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/healthz', timeout=3).read()"
      interval: 30s
      timeout: 5s
      start_period: 15s
      retries: 3

networks:
  wireviz-shared:
    external: true
    name: wireviz-shared
```

Diese Vorlage entspricht auch der Datei [`compose.yaml`](compose.yaml). Nach dem Deployment ist die GUI unter `http://<NAS-IP>:8087` erreichbar. Der einzige hier benötigte API-Endpunkt ist `http://wireviz-web:3005/render`; der Wert wird ausschließlich mit `WIREVIZ_API_URL` konfiguriert.

Die Anwendung hat keine eingebaute Benutzeranmeldung. Im vertrauenswürdigen LAN betreiben oder den Zugriff mit einer geeigneten vorgeschalteten Authentifizierung/Firewall beschränken. `SECRET_KEY` mit einem nicht wiederverwendeten zufälligen Wert setzen und nicht veröffentlichen.

## Backup und Fehlerbehebung

- Projekte und eigene Vorlagen sind Klartextdateien im NAS-Volume. Diese Ordner regelmäßig mit NAS-Snapshots oder dem vorhandenen Backup-System sichern. Es gibt keine zusätzliche Datenbank und keine eingebaute Backup-Funktion.
- **GUI nicht erreichbar:** Portainer-Containerstatus und Healthcheck prüfen; Host-Port 8087 sowie NAS-Firewall/Portfreigaben kontrollieren.
- **API nicht erreichbar:** Sicherstellen, dass `wireviz-web` im gemeinsamen Docker-Netzwerk ist und dort den Alias `wireviz-web` hat; `WIREVIZ_API_URL` und API-Logs prüfen. `WIREVIZ_LISTEN` des bestehenden Dienstes muss wie vorgegeben `0.0.0.0:3005` sein.
- **YAML wird abgelehnt:** Die Oberfläche zeigt Syntaxfehler mit Zeile/Spalte. Doppelte Schlüssel sind unzulässig. Die WireViz-Fachprüfung findet erst beim API-Rendern statt.
- **API meldet Renderfehler:** Den YAML-Abschnitt, die unterstützten WireViz-Attribute und die WireViz-Web-Logs prüfen. Nur die Syntaxprüfung allein garantiert keine fachlich gültige Kabelbeschreibung.
- **SVG wird nicht angezeigt:** Die GUI akzeptiert nur eine SVG-Antwort der API und entfernt nicht benötigte/aktive SVG-Elemente. API-Antwortformat und API-Containerlogs prüfen.
- **Projekt kann nicht gespeichert werden:** Schreibrechte des NAS-Verzeichnisses für UID/GID 10001 kontrollieren. Projekte und Vorlagen sind auf 1 MiB begrenzt; Pfade und Symlinks außerhalb des Datenverzeichnisses werden zurückgewiesen.

## Einschränkungen

Die Syntaxprüfung im Browser und Server akzeptiert YAML-Syntax, nicht jede WireViz-Fachregel. Die fachliche Prüfung erfolgt daher weiterhin durch WireViz-Web beim Rendern. Benutzerdefinierte Vorlagen sind über `/data/templates/` lesbar; sie werden außerhalb der GUI auf das NAS kopiert. Der optionale Live-API-Test wurde nicht automatisch ausgeführt, sofern kein expliziter Integrationstestdienst konfiguriert ist.
