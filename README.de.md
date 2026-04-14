<!-- translation-of: README.md | based-on-commit: initial -->

<p align="center">
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.md"><img src="https://img.shields.io/badge/lang-English-blue" alt="English"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.ko.md"><img src="https://img.shields.io/badge/lang-한국어-red" alt="Korean"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.ja.md"><img src="https://img.shields.io/badge/lang-日本語-green" alt="Japanese"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.zh-CN.md"><img src="https://img.shields.io/badge/lang-简体中文-orange" alt="Chinese"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.es.md"><img src="https://img.shields.io/badge/lang-Español-yellow" alt="Spanish"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.fr.md"><img src="https://img.shields.io/badge/lang-Français-blueviolet" alt="French"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.de.md"><img src="https://img.shields.io/badge/lang-Deutsch-lightgrey" alt="German"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.pt-BR.md"><img src="https://img.shields.io/badge/lang-Português_(BR)-brightgreen" alt="Portuguese (Brazil)"></a>
</p>

<h1 align="center">codebeacon</h1>

<p align="center">
  Quellcode-AST-Analyse und KI-Kontextgenerierung — einheitlicher Multi-Framework-Knowledge-Graph
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## Warum codebeacon?

Jedes Mal, wenn Sie eine neue KI-Codiersitzung öffnen, beginnt der Assistent bei null. Er kennt weder Ihre Routes, noch Ihre Service-Schicht, noch Ihr Entitätsmodell, noch die Kommunikationswege zwischen Ihren Microservices. Sie verbringen den Beginn jeder Sitzung damit, Dateien einzufügen, die Struktur zu erklären und den Kontext wiederherzustellen.

Bestehende Tools lösen dieses Problem nur teilweise. Route-Analyzer erfassen Ihre Controller, aber übersehen Service-Abhängigkeiten. Knowledge-Graph-Tools erfassen Beziehungen, ignorieren aber die API-Oberfläche. Das Ergebnis: beide Tools parallel ausführen, Ausgaben manuell zusammenführen und das bei jeder Codeänderung wiederholen.

**codebeacon vereint beide Ansätze in einem einzigen CLI.** Ein Befehl scannt die gesamte Codebasis mit tree-sitter-AST-Analyse, löst Dependency-Injection über Dateigrenzen hinweg auf, erkennt Community-Cluster in der Architektur und schreibt eine einsatzbereite Kontextkarte direkt in `CLAUDE.md`, `.cursorrules` und `AGENTS.md`.

---

## Hauptfunktionen

- **Einheitliche Pipeline** — Routes-/Controller-Analyse + Knowledge Graph in einem Tool, kein manuelles Zusammenführen
- **24 Frameworks, 9 Sprachen** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, ASP.NET Core, Vapor, Ktor
- **Auf tree-sitter basierend** — strukturelles AST-Parsing, keine Regex; Sprachgrammatiken standardmäßig enthalten
- **2-Pass DI-Auflösung** — Pass 1 extrahiert lokale AST-Knoten; Pass 2 baut eine globale Symboltabelle auf und löst Interface → Implementation-Mappings auf
- **Wave-Merge-Architektur** — Dateien werden in parallelen Chunks verarbeitet und global zusammengeführt; auch große Monorepos ohne Speicherprobleme
- **Mehrere Ausgabeformate** — JSON-Knowledge-Graph, Markdown-Wiki, Obsidian Vault, KI-Kontextkarten, MCP-Server
- **Community-Erkennung** — Leiden/Louvain-Clustering deckt tatsächliche Architekturgrenzen auf
- **Inkrementeller Cache** — SHA-256-basiert; extrahiert nur seit dem letzten Scan geänderte Dateien neu
- **Keine Konfiguration notwendig** — erkennt Frameworks und Sprachen automatisch; generiert `codebeacon.yaml` für Folgeläufe
- **Deep-Dive-Modus** — `--deep-dive` erzeugt für jedes Sub-Projekt eigene `.codebeacon/` + `CLAUDE.md`; ein Update-Aufruf aus **beliebigem** Sub-Projekt-Ordner synchronisiert automatisch alle Projekte im Workspace

---

## Schnellstart

```bash
pip install codebeacon

codebeacon scan .
```

codebeacon erkennt die Projekttypen, extrahiert Routes/Services/Entitäten/Komponenten, baut den Knowledge Graph auf und schreibt alles nach `.codebeacon/`.

Für einen Multi-Projekt-Workspace:

```bash
codebeacon scan /pfad/zum/workspace   # alle Projekte automatisch erkennen, codebeacon.yaml generieren
codebeacon sync                       # Folgeläufe über Konfiguration
```

---

## Unterstützte Frameworks

| Sprache | Frameworks |
|---------|-----------|
| Java / Kotlin | Spring Boot, Ktor |
| Python | Django, FastAPI, Flask |
| JavaScript / TypeScript | Express, Fastify, Koa, NestJS, React, Next.js, Vue, Nuxt, Angular, SvelteKit |
| Go | Gin, Echo, Fiber |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web, Axum |
| C# | ASP.NET Core |
| Swift | Vapor |

---

## Architektur

codebeacon führt eine 2-Pass-Extraktionspipeline aus:

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         Lokales AST         Symbol-     Cross-      HTTP API
                         pro Chunk           tabelle     Language    Shared DB
                         (Pass 1)            Matching    Artefakt-   Entity-
                                            (Pass 2)    Filterung   Edges
```

**Pass 1 — Wave-Extraktion:** Dateien werden in parallelen Chunks per `ThreadPoolExecutor` verarbeitet. Jede Datei durchläuft fünf Extraktoren: Routes, Services, Entitäten, Komponenten und Abhängigkeiten.

**Pass 2 — Graph-Aufbau:** Alle Wave-Ergebnisse werden zusammengeführt. Eine globale Symboltabelle löst unaufgelöste DI-Referenzen auf — Interface→Implementation-Mappings, die Ein-Pass-Tools übersehen.

---

## Ausgabestruktur

Nach dem Scan werden Kontextkarten-Dateien im Projektstammverzeichnis aktualisiert (vorhandener Nutzerinhalt bleibt erhalten) und der Knowledge Graph in `.codebeacon/`:

```
project-root/
  CLAUDE.md              ← KI-Kontextkarte (codebeacon-Block eingemergt; Nutzerinhalt erhalten)
  .cursorrules           ← Cursor-IDE-Kontext (gleiche Merge-Strategie)
  AGENTS.md              ← OpenAI-Agents-/Codex-Kontext (gleiche Merge-Strategie)
  .codebeacon/
    beacon.json          ← vollständiger Knowledge Graph (Node-Link-JSON, abfragbar)
    REPORT.md            ← God-Nodes, überraschende Verbindungen, Hub-Dateien
    wiki/
      index.md
      overview.md
      routes.md
      <project>/
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian Vault (eine Notiz pro Graph-Knoten)
```

### Deep-Dive-Modus

Mit `--deep-dive` erhält jedes Sub-Projekt sein eigenes `.codebeacon/` + `CLAUDE.md`. Claude Code lädt `CLAUDE.md`-Dateien hierarchisch — eine Sitzung in `api-server/` lädt also sowohl den Workspace-Überblick als auch die projektspezifischen Details.

Das entscheidende Merkmal: ein Update-Aufruf aus **jedem beliebigen Sub-Projekt** synchronisiert automatisch den gesamten Workspace:

```bash
# Erster Deep-Dive-Scan
codebeacon scan /workspace --deep-dive

# Später aus einem beliebigen Sub-Projekt — findet die übergeordnete Konfig und aktualisiert ALLE Projekte
cd /workspace/api-server
codebeacon scan . --update
```

Ausgabestruktur:
```
workspace/
  CLAUDE.md                   ← kombiniert (alle Projekte)
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← kombinierter Knowledge Graph
  api-server/
    CLAUDE.md                 ← nur api-server
    .codebeacon/              ← api-server-Graph
  frontend/
    CLAUDE.md                 ← nur frontend
    .codebeacon/              ← frontend-Graph
```

## Konfiguration

Führe `codebeacon init` aus, um `codebeacon.yaml` zu generieren, oder erstelle die Datei manuell:

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # optional: wird automatisch erkannt

  - name: frontend
    path: ./frontend
    type: react

output:
  dir: .codebeacon
  wiki: true
  obsidian: true
  context_map:
    targets: [CLAUDE.md, .cursorrules, AGENTS.md]

wave:
  auto: true
  chunk_size: 300              # Dateien pro Chunk
  max_parallel: 5              # parallele Threads

semantic:
  enabled: false               # mit --semantic überschreiben

deep_dive: false               # auf true setzen für Pro-Projekt-Ausgabe
```

### .codebeaconignore

Platziere eine `.codebeaconignore`-Datei im Projektstammverzeichnis, um Verzeichnisse oder Dateien vom Scan auszuschließen. Gleiche Syntax wie `.gitignore` — ein Muster pro Zeile, `#` für Kommentare.

```
# .codebeaconignore
generated/
build/
*.generated.ts
fixtures/
```

---

## KI-Integration

### Claude Code Skill (`/codebeacon`)

Installiere codebeacon als Claude Code Slash-Befehl:

```bash
pip install codebeacon
codebeacon install
```

Dies kopiert `SKILL.md` nach `~/.claude/skills/codebeacon/` und registriert den `/codebeacon`-Trigger in `~/.claude/CLAUDE.md`. Starte deine Claude Code-Sitzung neu und tippe `/codebeacon`, um das aktuelle Verzeichnis zu scannen.

```
/codebeacon                  # aktuelles Verzeichnis scannen
/codebeacon /path/to/project # bestimmten Pfad scannen
/codebeacon sync             # erneut aus codebeacon.yaml scannen
```

### MCP-Server

Führe codebeacon als persistenten MCP-Server aus, damit jeder MCP-kompatible Client den Wissensgraphen direkt abfragen kann.

**Schritt 1 — Projekt scannen:**
```bash
codebeacon scan .
```

**Schritt 2 — zur MCP-Client-Konfiguration hinzufügen:**

**Claude Code** (`.claude.json` im Projektstamm oder global `~/.claude.json`):
```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "codebeacon",
      "args": ["serve"]
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "codebeacon",
      "args": ["serve", "--dir", "/path/to/.codebeacon"]
    }
  }
}
```

**Verfügbare MCP-Tools nach Verbindung:**

| Tool | Beschreibung |
|------|--------------|
| `beacon_wiki_index` | Globale Projektübersicht (Routen, Services, Entitäten) |
| `beacon_wiki_article` | Wiki-Artikel anhand eines Pfads lesen |
| `beacon_query` | Knoten per Teilstring-Suche finden |
| `beacon_path` | Kürzester Abhängigkeitspfad zwischen zwei Knoten |
| `beacon_blast_radius` | Upstream-Aufrufer und downstream betroffene Knoten |
| `beacon_routes` | Alle HTTP-Routen auflisten (nach Projekt filterbar) |
| `beacon_services` | Alle Services/Klassen auflisten (nach Projekt filterbar) |

---

## Installationsoptionen

```bash
pip install codebeacon              # Sprachgrammatiken inklusive
pip install codebeacon[cluster]     # + Leiden-Community-Erkennung (graspologic)
pip install --upgrade codebeacon    # auf die neueste Version mit allen Abhängigkeiten aktualisieren
```

Java, Kotlin, Python, JavaScript, TypeScript, Go, Ruby, PHP, C#, Rust, Swift, HTML und Svelte sind standardmäßig enthalten.

---

## CLI-Referenz

```bash
codebeacon scan .                         # aktuelles Verzeichnis
codebeacon scan . --update                # inkrementell: nur geänderte Dateien
codebeacon scan . --wiki-only             # Extraktion überspringen, Wiki/Obsidian/Kontext aus vorhandenem beacon.json regenerieren
codebeacon scan . --semantic              # LLM-semantische Extraktion
codebeacon scan . --list-only             # nur Frameworks erkennen
codebeacon scan /workspace --deep-dive    # Pro-Projekt- + kombinierte Workspace-Ausgabe

codebeacon init [pfad]                    # codebeacon.yaml generieren
codebeacon sync                           # von codebeacon.yaml ausführen

codebeacon query <Begriff>                # Graph durchsuchen (demnächst)
codebeacon path <Quelle> <Ziel>           # kürzester Pfad zwischen zwei Knoten

codebeacon serve [--dir .codebeacon]      # MCP-Server starten (stdio)
codebeacon install                        # Claude-Code-Skill installieren
```

---

## Vergleich

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| Routes-/Controller-Analyse | ✅ | ❌ | ✅ |
| Service-/DI-Graph | teilweise | ✅ | ✅ |
| Interface → Impl-Auflösung | ❌ | ❌ | ✅ |
| Entitäts-/ORM-Modell-Extraktion | ✅ | ❌ | ✅ |
| Frontend-Komponenten-Analyse | ✅ | ❌ | ✅ |
| Community-Erkennung | ❌ | ✅ | ✅ |
| Obsidian-Vault-Export | ❌ | ✅ | ✅ |
| MCP-Server | ✅ | ❌ | ✅ |
| KI-Kontextkarte (CLAUDE.md) | ✅ | ✅ | ✅ |
| Multi-Projekt-Workspace | teilweise | ❌ | ✅ |
| Python-basiert | ❌ | ✅ | ✅ |

---

## Benchmarks

| Codebasis | Stack | Dateien | Knoten | Kanten | Communities | Scan-Zeit |
|-----------|-------|---------|--------|--------|-------------|-----------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3 Projekte) | 444 | 382 | 553 | 175 | ~12s |

---

## Datenschutz und Sicherheit

Alle Verarbeitung erfolgt lokal. Ihr Quellcode verlässt niemals Ihren Rechner. Keine Telemetrie, keine Netzwerkaufrufe im normalen Betrieb.

- Das Flag `--semantic` (standardmäßig deaktiviert) aktiviert zwei Extraktionsmodi:
  1. **Strukturierte Kommentaranalyse** (kein LLM erforderlich) — leitet Kreuzreferenzen aus Javadoc (`@see`, `{@link}`), Python-Docstrings (`:class:`, `:func:`) und JSDoc (`@see`, `@param`-Typen) ab
  2. **LLM-Inferenz** (optional) — bei gesetztem `ANTHROPIC_API_KEY` werden Code-Ausschnitte an die Claude-API gesendet; nur bei expliziter Aktivierung verwenden

---

## Mitwirken

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

Der einfachste Einstiegspunkt für neuen Framework-Support ist das Schreiben einer tree-sitter-Query-Datei in `codebeacon/extract/queries/`. Siehe [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md).

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).

---

## Danksagungen

Aufgebaut auf [tree-sitter](https://tree-sitter.github.io/tree-sitter/), [NetworkX](https://networkx.org/) und [graspologic](https://microsoft.github.io/graspologic/). Inspiriert von den komplementären Ansätzen von [codesight](https://github.com/Houseofmvps/codesight) und [graphify](https://github.com/safishamsi/graphify).
