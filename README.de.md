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

## Neu in 0.7.1

Das bisher größte Audit-Release: ein doppelter Upstream-Parity-Sweep (graphify v0.9.13–v0.9.53 / Issues #1777–#3235, dazu codesight #50–#55), gegen codebeacon verifiziert mit verpflichtender Reproduktion — **~70 bestätigte Defekte behoben** von zehn parallelen Fixern, jeder Fix mutationsgetestet, anschließend vom Lead adversarisch reviewt mit echten CLI-Integrationsläufen. Suite: 885 → 1.481 Tests.

- **Der JS/TS-Graph hat sich ungefähr verdoppelt** — exportierte kleingeschriebene Arrow-Functions, `const`s und Objektliteral-Member (`export const useAuthStore = …`, `authUtils.clear`) werden endlich zu Nodes: in einer echten Next.js-App mit 865 Dateien stiegen die Komponenten-Nodes von **960 → 2.237**, und die Dateien, die nichts beitrugen, fielen von 406 → 108. Imports werden jetzt zuerst über den **Pfad** aufgelöst (relative Specifier, `tsconfig`/`jsconfig`-Aliase inklusive `extends`-Ketten und `${configDir}`, Package-Suffixe), bevor auf Labels zurückgefallen wird — so kann sich `from codebeacon.graph.build import …` nicht mehr an ein unbeteiligtes `build`-Symbol binden, und die „High-Impact Files"-Liste in CLAUDE.md spiegelt die Realität wider. Auch die Vererbung von reinem JS `class X extends Y` und dynamische `await import()`-Kanten werden erfasst.
- **Route-Prefixe komponieren wie in den echten Frameworks** — verifiziert gegen laufende FastAPI-/Express-/Flask-Server: `include_router(prefix=)` komponiert mit dem eigenen Prefix des Routers, Includes in Attributform (`app.include_router(pkg.router, …)`, `@pkg.router.get`) verschwinden nicht mehr, kaskadierte Mounts in derselben Datei werden ausmultipliziert, ein zweimal gemounteter Router liefert beide Routen, und Flasks `register_blueprint(url_prefix=)` *überschreibt* korrekt. Bekannte Grenze: eine Mount-Kette über **Dateien** hinweg wird weiterhin nicht komponiert.
- **Interface→Impl-DI-Auflösung funktioniert jetzt wirklich** — eine Serialisierungsgrenze in der Extraktions-Pipeline verwarf seit 0.6.x stillschweigend `implements`/`extends`, sodass das gesamte Feature end-to-end tot war, während das Wiki richtig aussah. Behoben, Cache invalidiert und über die echte Pipeline grenzgetestet. Das DI-Binding ist jetzt außerdem evidenzbasiert abgesichert: keine sprach- oder projektübergreifenden Erfindungen mehr (ein Spring-service kann keine React-Komponente mehr „injizieren"), mehrdeutige Fälle mit mehreren Implementierungen binden nur über die `*Impl`-Namenskonvention mit einer expliziten `AMBIGUOUS`-Konfidenz, und eine doppelte Kante hält ihre zweite Relation in einem neuen `also`-Attribut fest, statt sie zu überschreiben.
- **Node-Identität ist deterministisch und erweiterungsbewusst** — `Button.tsx` und `Button.jsx` sind zwei Nodes (zuvor absorbierte einer den anderen stillschweigend — 6,3 % der Deklarationen in codebeacons eigenem Repo); Node-IDs hängen nicht mehr von der Thread-Abschlussreihenfolge oder vom Checkout-Verzeichnis ab, sodass Wiki-/Obsidian-Dateinamen zwischen Läufen nicht mehr flattern. Kollidierende Labels erhalten das kürzeste unterscheidende Pfad-Suffix. (Die IDs zuvor kollabierter Nodes ändern sich beim Upgrade einmalig.)
- **Die Ignore-Schicht deckt sich viel enger mit git** — verschachtelte `.gitignore`-Dateien gelten für ihren eigenen Teilbaum (die `app/.gitignore` eines Monorepos wird nicht mehr selbst ignoriert, was früher Zehntausende Build-Dateien in den Scan zog), `.git/info/exclude` wird beachtet, verlinkte Worktrees werden strukturell erkannt statt den Korpus zu verdoppeln, und Ignore-Dateien mit BOM / in UTF-16 / NFD-kodiert werden dekodiert, statt Regeln stillschweigend fallen zu lassen. Mehrdeutige Verzeichnisnamen (`env/`, `build/`, `public/`, `coverage/`, …) werden nur mit bestätigender Evidenz gepruned — eine UVM-`env/`-Testbench oder ein Python-Package namens `coverage/` bleibt im Graphen. Das Matching ist ~19× schneller, und eine neue `ignored.json`-Diagnose hält fest, *warum* jeder Teilbaum übersprungen wurde.
- **Der Shrink-Guard schützt jetzt die Pfade, auf die es ankommt** — er wurde früher schon durch die bloße Anwesenheit von `--update` entschärft, also genau auf den unbeaufsichtigten Pfaden (Watch, Git-Hooks, CI); ein Berechtigungsfehler konnte deinen committeten Graphen stillschweigend halbieren. Er ordnet jetzt jeden entfernten Node seiner Quelldatei zu (gelöscht / neu ignoriert / **unerklärt** — nur Letzteres verweigert, mit einem echten `--force`-Flag), bleibt überall scharf geschaltet, behandelt einen unlesbaren Teilbaum als „unbekannt, nicht durchwinken" und warnt, wenn Kanten kollabieren, obwohl die Nodes stabil blieben.
- **`scan → knowledge → scan` klemmt nicht mehr** — der in 0.7.0 dokumentierte Ablauf beendete sich entweder mit 1 („refusing to shrink") oder verwarf stillschweigend dein Notizen-Overlay. Der Guard ist jetzt Tier-bewusst, und das Knowledge-Overlay wird **nach jedem Scan automatisch neu angewendet**; das Löschen einer Notiz pruned genau diese Notiz. Selbst geschriebene `[[wikilinks]]` erzeugen endlich Kanten (sie wurden geparst und dann verworfen — 100 % Verlust), Notizen tragen `node_kind`/Frontmatter, und generierte Dateien (CLAUDE.md, KNOWLEDGE.md) werden nicht mehr als Notizen re-ingestiert.
- **Ein committeter Index bleibt sauber** — ein unveränderter Rescan schreibt jetzt **null** committete Dateien neu (vorher: jede einzelne, ~31k Dateien Churn upstream): `built_at_ts` leitet sich aus dem Commit ab, Exporte schreiben nur bei Inhaltsänderung, und der maschinenlokale AST-Cache git-ignoriert sich selbst. HTML-Exporte (`beacon.html`, `callflow.html`) liefern ihr JS **standardmäßig offline** aus (vendored d3 + mermaid unter `_assets/`) — passend zur Air-Gap-Haltung; setze `output.html_assets: cdn`, um das alte Verhalten zu behalten. Absolute Pfade der Build-Maschine lecken in kein Artefakt mehr.
- **MCP-Antworten, denen du programmatisch trauen kannst** — Tool-Fehler geben `isError: true` mit der handlungsleitenden Meldung zurück (statt erfolgsförmiger Fehlerprosa oder eines Protokollfehlers, den der Client verschluckt); die Namensauflösung bevorzugt eine exakte Übereinstimmung vor Teilstrings, sodass `blast_radius("User")` nicht mehr über `UserServiceImpl` Auskunft gibt; jedes Tool respektiert ein `token_budget` (Standard 2.000 Tokens) und kündigt Kürzungen gegen die tatsächliche Gesamtmenge an.
- **Robustheits- & Sicherheits-Sweep** — `.csproj`-XML wird mit einem DOCTYPE/ENTITY-Filter geparst; modellgerichteter Text (MCP-Ausgabe, CLAUDE.md) neutralisiert Chat-Template-Steuertokens anhand ihrer Form (`<|…|>`, `[INST]`); `hook install` funktioniert in Git-Worktrees und lässt ein Repo nie halb konfiguriert zurück; `install`/`upgrade` sichern eine handbearbeitete SKILL.md, statt sie zu überschreiben, und ein nicht terminierter Marker kann Nutzerinhalte darunter nicht mehr löschen; eine CLAUDE.md in cp949/latin-1 bringt den Scan nicht zum Absturz; `codebeacon … | head` beendet sich sauber; der Watch-Modus triggert sich unter Linux nicht mehr selbst über inotify-Events; das Leiden-Clustering ist geseedet, sodass Communities nicht mehr 12 % pro Rescan driften.

Upgrade-Hinweise: Node-IDs zuvor kollabierter Deklarationen ändern sich einmalig; semantische `task_id`s werden einmalig invalidiert (Tasks hashen jetzt die ganze Datei, was „Edits jenseits von Zeichen 4.000 werden nie neu analysiert" behebt); der AST-Cache wird einmalig invalidiert (Schema-Stempel); neues Kanten-Attribut `also`, neuer Konfidenzwert `AMBIGUOUS`, neuer `verification`-Marker auf semantisch geprägten Externals. Falls dein Repo `.codebeacon/cache/` bereits committet hat, führe einmalig `git rm --cached -r .codebeacon/cache` aus — die neue selbst-ignorierende `.gitignore` kann bereits getrackte Dateien nicht mehr aus dem Index entfernen.

Ältere Releases: siehe [CHANGELOG.md](CHANGELOG.md) (Englisch).

---

## Warum codebeacon?

Jedes Mal, wenn Sie eine neue KI-Codiersitzung öffnen, beginnt der Assistent bei null. Er kennt weder Ihre Routes, noch Ihre Service-Schicht, noch Ihr Entitätsmodell, noch die Kommunikationswege zwischen Ihren Microservices. Sie verbringen den Beginn jeder Sitzung damit, Dateien einzufügen, die Struktur zu erklären und den Kontext wiederherzustellen.

Bestehende Tools lösen dieses Problem nur teilweise. Route-Analyzer erfassen Ihre Controller, aber übersehen Service-Abhängigkeiten. Knowledge-Graph-Tools erfassen Beziehungen, ignorieren aber die API-Oberfläche. Das Ergebnis: beide Tools parallel ausführen, Ausgaben manuell zusammenführen und das bei jeder Codeänderung wiederholen.

**codebeacon vereint beide Ansätze in einem einzigen CLI.** Ein Befehl scannt die gesamte Codebasis mit tree-sitter-AST-Analyse, löst Dependency-Injection über Dateigrenzen hinweg auf, erkennt Community-Cluster in der Architektur und schreibt eine einsatzbereite Kontextkarte direkt in `CLAUDE.md`, `.cursorrules` und `AGENTS.md`.

---

## Hauptfunktionen

- **Einheitliche Pipeline** — Routes-/Controller-Analyse + Knowledge Graph in einem Tool, kein manuelles Zusammenführen
- **27 Frameworks, 9 Sprachen** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor
- **Auf tree-sitter basierend** — strukturelles AST-Parsing, keine Regex; Sprachgrammatiken standardmäßig enthalten
- **2-Pass DI-Auflösung** — Pass 1 extrahiert lokale AST-Knoten; Pass 2 baut eine globale Symboltabelle auf und löst Interface → Implementation-Mappings auf
- **Wave-Merge-Architektur** — Dateien werden in parallelen Chunks verarbeitet und global zusammengeführt; auch große Monorepos ohne Speicherprobleme
- **Mehrere Ausgabeformate** — JSON-Knowledge-Graph, Markdown-Wiki, Obsidian Vault, KI-Kontextkarten, MCP-Server, interaktives HTML
- **Visuelle Exploration** — `beacon.html` (D3 einklappbarer Baum) und `callflow.html` (Mermaid-Architekturdiagramme nach Community gruppiert) werden bei jedem Scan neu erzeugt
- **Community-Erkennung** — Leiden/Louvain-Clustering deckt tatsächliche Architekturgrenzen auf
- **Inkrementeller Cache** — SHA-256 + mtime/size Fast-Path; reine mtime-Änderungen durch Sync-Tools (Obsidian/iCloud/Nextcloud) lösen niemals eine unnötige Re-Extraktion aus
- **Confidence-Promotion** — datei-übergreifende `calls`-Kanten werden automatisch von INFERRED auf EXTRACTED hochgestuft, wenn ein expliziter Import das Binding belegt
- **Sichere Schreibvorgänge** — beacon.json hat einen Shrink-Guard (ein Teil-Lauf kann niemals einen vollständigen Graph überschreiben) und stempelt `built_at_commit`, sodass REPORT.md veraltete Ausgaben gegen den aktuellen HEAD kennzeichnet
- **Multi-Entwickler-freundlich** — `codebeacon hook install` registriert einen git-Merge-Driver für `beacon.json` und einen Post-Commit-Hook für inkrementelle Rebuilds; zwei Devs, die denselben Branch scannen, produzieren niemals Merge-Konflikte im Graph
- **Gehärtete Ausgabe** — YAML-Frontmatter und MCP-Labels werden sanitisiert: U+2028/U+2029, C0-Steuerzeichen und Bidi-Marken werden entfernt, bevor sie Obsidian, Cursor oder den Agenten erreichen
- **`.codebeaconignore` im gitignore-Stil** — last-match-wins mit `!`-Negation, Verzeichnis-Patterns (`build/`), verankerte Patterns (`/secrets.txt`), Trailing-Whitespace-Regeln
- **Keine Konfiguration notwendig** — erkennt Frameworks und Sprachen automatisch; generiert `codebeacon.yaml` für Folgeläufe
- **Deep-Dive-Modus** — `--deep-dive` erzeugt für jedes Sub-Projekt eigene `.codebeacon/` + `CLAUDE.md`; ein Update-Aufruf aus **beliebigem** Sub-Projekt-Ordner synchronisiert automatisch alle Projekte im Workspace
- **Automatische Workspace-Wiedererkennung** — bei jedem `scan`/`sync` scannt codebeacon den Workspace erneut und hängt vor der Extraktion automatisch neue Projekte an die `codebeacon.yaml` an, sodass frisch hinzugefügte Sub-Projekte nicht unbemerkt übersprungen werden; `--no-rediscover` deaktiviert dies für handgepflegte Konfigurationen
- **Graphify-artige Semantik-Anreicherung** — nach der AST-Extraktion dispatcht der Skill einen parallelen Subagenten pro Chunk, der vollständige Knowledge-Graph-Fragmente `{nodes, edges, hyperedges}` mit 8 Relationstypen (`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`) und Konfidenz EXTRACTED/INFERRED/AMBIGUOUS erzeugt; auf Claude Code läuft der Subagent eine Stufe unter dem Host-Modell (Opus→Sonnet, Sonnet→Haiku), damit die Kosten proportional zur Korpus-Größe bleiben. Code-Knoten gehören dem AST; das LLM darf nur `concept`/`document`/`paper`-Knoten beisteuern. Bestehende 0.3.x-Archive werden unter dem neuen Schema unverändert wiedergegeben
- **Wissensmodus (`codebeacon knowledge`)** — scannt Markdown-Notizen (ADRs, Meeting-Protokolle, Retros, Specs, Research) und erzeugt eine einzelne `KNOWLEDGE.md` neben `.codebeacon/`. Automatische Klassifizierung nach Dateinamen- und Überschriftenmustern, Parsing von Obsidian-YAML-Frontmatter und `[[backlinks]]`, sowie ein „Key Decisions" + „Open Questions"-Roll-up ganz oben, damit der Agent versteht, *warum* die Codebasis so aussieht, wie sie aussieht. Reine Heuristik — kein LLM-Aufruf
- **Pfad-Kurzform** — `codebeacon ./src` ist jetzt äquivalent zu `codebeacon scan ./src`; wenn das erste Argument kein registrierter Sub-Befehl ist, wird `scan` automatisch eingefügt — die `graphify <path>` / `codesight <path>` Muskelerinnerung funktioniert genauso
- **Gehärtete Semantik-Pipeline** — `semantic-apply` schützt vor fehlerhaftem Agent-JSONL (null/Listen/Code-Fence-Zeilen, fehlende Felder), coerced kaputte `confidence_score`-Werte (None/NaN/String/außerhalb des Bereichs) zu einem sicheren Default, snapshottet `beacon.json` → `beacon.json.bak` vor dem Merge, sodass die AST-Baseline jederzeit wiederherstellbar ist, und regeneriert `beacon.html` + `callflow.html`, damit die visuellen Exporte die neu inferierten Kanten reflektieren
- **Schutzschienen für sensible Dateien/Verzeichnisse** — `secrets/`, `credentials/`, `.ssh/`, `.aws/`, `.gnupg/` werden immer übersprungen; Dateinamen, die Credential-Mustern entsprechen (`api_token`, `oauth_token`, `private_key`, `client_secret`; Underscore- *und* Bindestrich-Varianten) werden vom Collector vor den Extraktoren ausgeschlossen

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
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`); `.sln` / `.csproj` / `.fsproj` / `.vbproj` für `ProjectReference` + `PackageReference` geparst |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) eingesammelt — Extraktoren framework-agnostisch |

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
    beacon.json          ← vollständiger Knowledge Graph; bettet `meta.built_at_commit` ein
    beacon.html          ← D3-Baum-Viewer (im Browser öffnen)
    callflow.html        ← Mermaid-Call-Flow-Diagramme, nach Community gruppiert
    REPORT.md            ← God-Nodes, überraschende Verbindungen, Hub-Dateien, Frische
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

## Visuelle Exploration

Jeder Scan schreibt zwei eigenständige HTML-Dateien neben `beacon.json`:

```
.codebeacon/beacon.html      # D3 v7 einklappbarer Baum — in jedem Browser öffnen
.codebeacon/callflow.html    # Mermaid-Architekturdiagramme, eines pro Community
```

Kein Build, kein statischer Server, kein Copy-Paste. Datei öffnen, klicken um Projekte → Typen → Knoten auszuklappen; Hover zeigt Source-Pfade und Grad. `callflow.html` gruppiert den Graph nach Community und rendert jede als Mermaid-Flowchart, mit den ausgehenden Cross-Community-Kanten in einer einklappbaren Tabelle.

---

## Multi-Entwickler-Workflow

Zwei Devs, die `codebeacon scan` auf demselben Branch ausführen, produzieren leicht unterschiedliche `beacon.json` — historisch ein Merge-Konflikt-Hotspot. `codebeacon hook install` löst das:

```bash
codebeacon hook install            # im Repo-Root
```

Es registriert:

- einen **git-Merge-Driver**, der zwei `beacon.json` per Union zu einer zusammenführt (Knoten per ID, Kanten per `(source, target, relation)` dedupliziert),
- einen `.gitattributes`-Eintrag, der `*beacon.json` auf den Driver verweist,
- einen **Post-Commit-Hook**, der `codebeacon scan . --update` im Hintergrund ausführt, damit der Graph niemals hinter den Commits zurückbleibt. Ausgabe in `~/.cache/codebeacon-rebuild.log`.

Der Merge-Driver beendet sich immer mit 0 — eine Graph-Regeneration blockiert niemals einen echten Merge.

---

## Sicherheitsgarantien

Invarianten, die der Writer bei jedem erfolgreichen Scan durchsetzt:

| Guard | Was er verhindert |
|---|---|
| **Shrink-Guard** | Eine partielle Extraktion oder ein unterbrochener Lauf kann niemals eine größere vollständige `beacon.json` überschreiben. Per `force=True` aus der API umgehbar. |
| **Atomares Schreiben** | `beacon.json` wird via `os.replace` geschrieben, die Datei ist also entweder komplett oder unangetastet — niemals halb geschrieben. |
| **`built_at_commit`-Stempel** | `beacon.json` bettet `meta.built_at_commit` (vollständige SHA) ein und `REPORT.md` zeigt die Kurz-SHA. Wenn HEAD weiter ist, markiert der Report den Graphen als `⚠ stale` mit einem einzeiligen Hinweis. |
| **Frontmatter-/Label-Härtung** | YAML-Frontmatter-Werte sind single-quoted und escapen U+2028, U+2029, Tab und C0-Steuerzeichen; MCP-Tool-Ausgabe lässt jedes Label durch denselben Sanitizer laufen. Ein böswilliger Identifier im Quellcode kann Obsidians YAML-Parser nicht zerschlagen oder Steuersequenzen in den Kontext eines LLM-Agenten injizieren. |

---

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
  enabled: false               # nur strukturierte Kommentaranalyse;
                               # mit --semantic überschreiben. AI-semantik lebt NICHT
                               # hier — sie wird vom /codebeacon-Skill
                               # (= laufender Agent) ausgelöst.

deep_dive: false               # auf true setzen für Pro-Projekt-Ausgabe
```

### .codebeaconignore

Platziere eine `.codebeaconignore`-Datei im Projektstammverzeichnis, um Verzeichnisse oder Dateien vom Scan auszuschließen. Semantik konform zu `.gitignore` — last-match-wins mit `!`-Negation, verankerte Muster (`/foo`), nur-Verzeichnis-Muster (`build/`), Kommentare:

```
# .codebeaconignore

# Verzeichnisse
build/
generated/
fixtures/

# nur am Root verankert
/scripts/local-only.ts

# Glob-Muster
*.gen.ts
**/snapshots/**

# eine Datei wieder einschließen, auch wenn build/ ignoriert ist
!build/manifest.ts
```

`!pattern` schließt einen zuvor ignorierten Pfad wieder ein; spätere Regeln überschreiben frühere. Der Walker schneidet Verzeichnisse weg, deren Name auf das Regelset matcht, aber er verschiebt das Wegschneiden, wenn eine Negationsregel eine geschachtelte Datei wieder einschließen könnte.

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
codebeacon scan . --semantic              # Extraktion strukturierter Kommentar-Referenzen (Javadoc/JSDoc/docstring)
codebeacon scan . --list-only             # nur Frameworks erkennen
codebeacon scan /workspace --deep-dive    # Pro-Projekt- + kombinierte Workspace-Ausgabe
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # wiederholbare gitignore-Stil-Patterns
                                          # mit .codebeaconignore / .gitignore vereint

codebeacon init [pfad]                    # codebeacon.yaml generieren
codebeacon sync                           # von codebeacon.yaml ausführen (hängt neue Workspace-Projekte automatisch an)
codebeacon sync --no-rediscover           # neue Projekte nicht automatisch anhängen (handgepflegter yaml-Modus)
codebeacon sync --exclude PATTERN         # gleiches Flag, gleiche Semantik

# PR / CI: was bricht dieser Diff wirklich?
codebeacon affected --base main           # die Aufrufer der geänderten Dateien stromaufwärts begehen
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # explizite Pfade — kein git nötig

codebeacon query <Begriff> [--dir .codebeacon] [--limit N]   # Knoten per Label-Substring suchen
codebeacon path <Quelle> <Ziel> [--dir .codebeacon]          # kürzester Abhängigkeitspfad

# Multi-Entwickler-Support (git plumbing)
codebeacon hook install [path]            # Merge-Driver + Post-Commit-Inkrement-Rebuild installieren
codebeacon merge-driver <base> <cur> <other>  # von git nach `hook install` aufgerufen; Union-Merge von beacon.json

# AI-semantische Anreicherung (LLM macht der Agent, codebeacon nur die Buchführung)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # rehydriert .codebeacon/semantic/original/*.jsonl auf das
                                          # frische beacon.json + entfernt Einträge mit verschwundenen
                                          # Knoten, schreibt dann neue Aufgaben nach
                                          # .codebeacon/semantic/pending/chunk_NNN.jsonl
                                          # (--chunk-size pro Chunk, Std. 10). task_id enthält einen
                                          # Content-Hash – geänderte Dateien werden neu emittiert.
codebeacon semantic-apply   [--dir .codebeacon]
                                          # für jede vom Agent geschriebene .codebeacon/semantic/
                                          # results/chunk_NNN.jsonl: INFERRED references-Kanten in
                                          # beacon.json mergen + den Pending-Chunk nach
                                          # .codebeacon/semantic/original/chunk_NNN.jsonl VERSCHIEBEN
                                          # (dauerhaftes Archiv). Results löschen, alles regenerieren.

codebeacon serve [--dir .codebeacon]      # MCP-Server starten (stdio)
codebeacon install                        # Claude-Code-Skill installieren (User-Scope: ~/.claude/)
codebeacon install --project [PATH]       # nach <PATH>/.claude/ installieren (team-geteilt, repo-gepinnt)
codebeacon upgrade                        # pip-Upgrade + ~/.claude/skills/codebeacon/SKILL.md aktualisieren
                                          # (`--force` falls editable-Installation)
```

---

## AI-semantische Anreicherung (via `/codebeacon`-Skill)

Tree-sitter-Parsing findet, was im AST steht. **AI-semantik** findet, was nur in den *Kommentaren* lebt — das `@see UserService` in einer Javadoc, das `:class:`OrderRepository`` in einer Python-Docstring, die vertraglichen Referenzen neben einem Route-Handler. codebeacon liefert dafür zwei Schichten:

| Schicht | Flag | Kosten | Was sie erfasst |
|---|---|---|---|
| Strukturierte Kommentaranalyse | `--semantic` | kostenlos, lokal, kein LLM | Javadoc `@see` / `{@link}`, JSDoc `@see` / `@param`-Typen, Python `:class:` / `:func:` / `See Also` |
| **AI-semantik** | automatisch im `/codebeacon`-Skill | nutzt das aktuelle Modell des Agenten — **kein extra API-Schlüssel** | nicht aufgelöste Klassen-/Typ-/Service-Referenzen, die Regex nicht findet (freier Prosa, indirekte Erwähnungen, reine Typ-Hinweise) |

Das CLI selbst **ruft niemals einen LLM-Anbieter auf**. Die AI-semantik-Schicht gehört bewusst dem **laufenden Agenten** innerhalb des `/codebeacon` Claude-Code-Skills — so wird die Modellwahl des Nutzers (Opus / Sonnet / Haiku / etc.) respektiert, und codebeacon braucht weder `ANTHROPIC_API_KEY` noch irgendeine Cloud-Konfiguration.

### Wie es läuft

Wenn Sie `/codebeacon` in Claude Code aufrufen:

1. `scan` / `sync` baut `beacon.json` aus dem AST (kein LLM-Aufruf).
2. `codebeacon semantic-prepare` rehydriert das Archiv unter `.codebeacon/semantic/original/*.jsonl` auf den frischen Graphen und **entfernt** Einträge, deren Quellknoten nicht mehr existiert. Anschließend schreibt es neue Aufgaben nach `.codebeacon/semantic/pending/chunk_NNN.jsonl` (≤ `--chunk-size` pro Datei, Std. 10). Chunk-Nummern setzen genau dort an, wo das dauerhafte Archiv aufhört — keine Kollisionen möglich.
3. Der Skill verarbeitet Pending-Chunks **einzeln**. Für jedes `pending/chunk_NNN.jsonl` liest der Agent (mit dem Modell der laufenden Sitzung) den `excerpt` jeder Aufgabe und schreibt eine gleichnamige `semantic/results/chunk_NNN.jsonl`.
4. `codebeacon semantic-apply` mergt die Ergebnisse als `INFERRED references`-Kanten in `beacon.json` und **verschiebt** jede abgeschlossene `pending/chunk_NNN.jsonl` nach **`semantic/original/chunk_NNN.jsonl`** (mit den angewandten Kanten zur Nachvollziehbarkeit). Die Result-Dateien werden gelöscht, Wiki + Obsidian + Kontextkarte regeneriert.
5. Beim nächsten Scan: `semantic-prepare` liest jeden Chunk unter `original/`, wendet seine Kanten auf den frisch gebauten Graphen an (historische Inferenzen bleiben erhalten) und überspringt jede Aufgabe, deren `task_id` bereits archiviert ist. `task_id` = `SHA1(file_path | node_id | excerpt_hash[:8])` — ändert sich der semantische Inhalt einer Datei, bekommt sie eine neue id und wird neu analysiert.

Inkrementelle, idempotente Anreicherung: der Agent analysiert dieselbe (Datei, Inhalt)-Kombination nie zweimal, das angesammelte AI-Signal überlebt jeden Rescan, und die Chunk-Aufteilung hält den Arbeitsumfang des Agenten klein.

### Direkte CLI-Nutzung

Wenn Sie nicht über den Skill gehen (z. B. CI), können Sie dieselben zwei Befehle manuell ausführen und Ihre eigenen `results/chunk_NNN.jsonl` liefern:

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# .codebeacon/semantic/pending/chunk_001.jsonl ... existieren jetzt.
# Schreiben Sie für jeden Pending-Chunk eine gleichnamige results/chunk_NNN.jsonl.
# Jede Zeile:
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### Deaktivieren

Übergeben Sie `--no-semantic` (oder `--wiki-only`, oder `--list-only`) beim Aufruf des Skills, um den AI-Schritt komplett zu überspringen. Die strukturierte Kommentaranalyse läuft weiterhin, wenn Sie `--semantic` an `scan` / `sync` übergeben.

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

Die gesamte AST-Verarbeitung läuft lokal. Wenn Sie codebeacon direkt aufrufen, verlässt Ihr Quellcode niemals Ihren Rechner. Keine Telemetrie, keine Netzwerkaufrufe im normalen Betrieb.

- Die CLI selbst **ruft niemals einen LLM-Anbieter auf** — das codebeacon-Paket enthält weder API-Client, noch Schlüsselverwaltung, noch Modellnamen.
- `--semantic` aktiviert **ausschließlich die strukturierte Kommentaranalyse** (Javadoc `@see` / `{@link}`, JSDoc `@see` / `@param`-Typen, Python `:class:` / `:func:` / `See Also`). Vollständig lokal.
- **AI-semantik** (die tiefere LLM-Schicht) wird vom `/codebeacon` Claude-Code-Skill ausgelöst. Der Agent liest `semantic-tasks.jsonl`, führt die Analyse mit dem **Modell der laufenden Sitzung** aus und schreibt `semantic-results.jsonl`. Die Python-CLI bereitet nur das Aufgaben-Batch vor und mergt die Ergebnisse — sie weiß nicht einmal, welches Modell verwendet wurde. Übergeben Sie `--no-semantic` an den Skill, um den LLM-Schritt vollständig zu überspringen.

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
