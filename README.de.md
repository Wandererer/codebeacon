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

## Neu in 0.6.9

Die bislang größte Audit-Release: ein doppelter Upstream-Parity-Sweep (das allererste vollständige Audit von codesights Tracker, plus graphify v0.9.4–v0.9.12 / Issues bis #1776), kombiniert mit einer unabhängigen Multi-Agent-Bug-Hunt über codebeacon selbst. Jeder Kandidat wurde vor der Behebung reproduziert, jede Behebung mutation-getestet, und eine adversariale Zweitprüfung griff anschließend die Fixes selbst an — und fing so vor der Auslieferung 18 weitere Lücken ab. **48 echte Bugs behoben.**

- **Deine CLAUDE.md ist jetzt sicher** — bei einer handgeschriebenen CLAUDE.md (z. B. aus `/init`) konnte der Merge-Schritt die eigenen `## Architecture` / `## Common Commands`-Abschnitte des Nutzers für codebeacon-Ausgabe halten und löschen. Das Entfernen läuft jetzt nur noch auf Dateien, die sich eindeutig als codebeacon-generiert ausweisen, und ist am generierten Block verankert — deine Abschnitte bleiben erhalten. `codebeacon.yaml` wird jetzt zudem atomar geschrieben (und durch Symlinks hindurch, unter Erhalt der Dateimodi), sodass ein abgebrochener Schreibvorgang eine handgepflegte Konfiguration nicht zerstören kann.
- **Dateien verschwinden nicht mehr still aus dem Index** — Großbuchstaben-Erweiterungen (`App.PY`, `Page.TSX`) wurden übersprungen; nach Zugangsdaten benannte Quellmodule (`api_key_manager.go`, `access_token_service.py`) fielen der Secret-File-Heuristik zum Opfer; ein einziges Nicht-UTF-8-Byte in einer `.gitignore` ließ den gesamten Scan abstürzen; und ein Repo, das unter einem Ordner namens `build/` oder `dist/` ausgecheckt war, bekam durch den Artefakt-Filter, der übergeordnete Verzeichnisse matchte, **seinen gesamten Graphen gelöscht**. Alles behoben; übersprungene Symlinks erhalten jetzt eine gruppierte Warnung statt Schweigen.
- **Die `.gitignore`-Behandlung stimmt jetzt exakt mit git überein** — die Negations-Semantik (`dir/` + `!dir/keep.txt`) wird über jede Regelform hinweg differenziell gegen `git check-ignore` getestet; eine Datei unter einem ausgeschlossenen Verzeichnis kann nicht mehr wieder aufgenommen werden, genau wie bei git. Das Standard-Rettungsidiom `dir/*` + `!dir/keep` funktioniert wie bisher.
- **Gleichnamige Projekte koexistieren** — zwei (oder drei) Unterprojekte, alle namens `frontend`, kollabierten früher zu einem einzigen: kollidierende Node-IDs ließen Routen still verschwinden, und ihre wiki-/obsidian-Ordner überschrieben sich gegenseitig. Doppelte Namen werden jetzt automatisch mit einem Präfix aus dem übergeordneten Verzeichnis eindeutig gemacht.
- **Die Routen-Extraktion wurde grundlegend korrigiert** — Express-`app.use('/api', router)`-Mount-Präfixe werden angewendet, und verkettetes `router.route(x).get().post()` liefert jeden Verb; Flask-`register_blueprint`- / FastAPI-`include_router`-Präfixe hängen nicht mehr davon ab, wo sie in der Datei stehen; Springs `@RequestMapping(method = RequestMethod.X)` erfasst den echten Verb statt `ANY`; Next.js-Catch-all-Segmente (`[...slug]`) werden nicht mehr verstümmelt und `@slot`-Parallel-Routen aus URLs entfernt; Laravels kanonisches `class X extends Model` erzeugt endlich eine Entity (zuvor matchten nur voll qualifizierte Basen — und `ViewModel` schleicht sich nicht mehr ein).
- **Phantom-Graph-Edges beseitigt** — ein kleingeschriebenes Import wie `CONFIG` wird nicht mehr per Case-Folding auf eine unverwandte `Config`-Klasse gefaltet (das falsche god-node-Muster), Imports binden nie über eine Sprachgrenze hinweg (`import time` → `time.ts`), DI-Bindungen bevorzugen das registrierende Projekt statt der ersten gleichnamigen Klasse irgendwo, und ein gleichnamiges Service + Entity in einem Verzeichnis kollabiert nicht mehr zu einem einzigen Node.
- **Exporte sind Windows-fest und absturzsicher** — obsidian-Notiznamen entfernen den vollständigen unter Windows unzulässigen Zeichensatz (Flask-`<string:id>`-Routen brachen den Export unter Windows) und schützen vor reservierten Gerätenamen; `None`-Labels lassen die wiki-, Call-Flow-HTML- oder obsidian-Exporter nicht mehr abstürzen; git-Hooks werden mit LF-Zeilenenden geschrieben, damit sie unter Windows laufen; und lange Projektnamen können mitten im Export die Dateisystem-Grenzen nicht mehr sprengen.
- **Eine fehlerhafte Eingabe kann langlaufende Prozesse nicht mehr töten** — der MCP-Server übersteht fehlerhafte JSON-RPC-Nachrichten, statt zu sterben; eine beschädigte `beacon.json` oder ein beschädigter AST-Cache (inklusive ungültigem UTF-8 und null/fehlerhaften Kollektionen) wird gesichert und gemeldet, statt `affected`, `serve` oder den Merge-Treiber abstürzen zu lassen.
- **Byte-reproduzierbare Ausgabe** — die Node-Reihenfolge folgt nicht mehr der Thread-Fertigstellungsreihenfolge und Shared-Entity-Annotationen werden sortiert, sodass zweimaliges Scannen eines unveränderten Baums byte-identische `beacon.json`, wiki und CLAUDE.md erzeugt. Das Leiden-Clustering-Backend (durch eine graspologic-API-Änderung still kaputt — es lief *nie*) ist wieder im Dienst.
- **Die Konfiguration, die du schreibst, ist die Konfiguration, die läuft** — dokumentierte `codebeacon.yaml`-Einstellungen (`wave.*`, `output.wiki/obsidian`, `context_map.targets`, `semantic.enabled`) wurden geparst und dann ignoriert; sie steuern jetzt die Pipeline, `--list-only` wird innerhalb von Workspaces berücksichtigt, und `codebeacon upgrade` gibt für uv-venv-Installationen den richtigen Befehl aus. Bonus-Konsistenz: die Projects-Tabelle, die Notes-Spalte und der Architecture-Abschnitt von CLAUDE.md sind sich jetzt über eine einzige „Services"-Zahl einig, passend zum wiki.

---

## Neu in 0.6.8

Ein graphify-Parity-Audit von Upstream v0.8.41–v0.9.3 (gemeldete Issues bis #1568). Jeder Kandidat wurde vor der Behebung gegen codebeacon reproduziert und durch eine adversariale Review-Runde erneut geprüft; **7 echte Bugs** bestätigt, angeführt von einer Datenverlust-Falle und einem Privacy-Leak.

- **`--obsidian-dir` kann keine Notizen mehr löschen** — bei einem bestehenden Obsidian-Vault fegte der Export vor der Neugenerierung *jede* `.md` darunter weg und konnte so ein echtes Vault leeren. codebeacon verweigert jetzt jedes Verzeichnis, das es nicht besitzt (nur ein wirklich leeres Verzeichnis oder eines mit seinem `.codebeacon-vault.json`-Marker wird übernommen) und überspringt den Export mit einer klaren Meldung statt zu löschen.
- **`.gitignore` wird nicht mehr still durch `.codebeaconignore` deaktiviert** — das Hinzufügen einer `.codebeaconignore` *ersetzte* bisher die `.gitignore` des Repos, sodass eine nur durch `.gitignore` ausgeschlossene Datei (ein neutral benanntes `prod-dump.sql`, `customer-data.*`) in die committeten `.codebeacon/`-Artefakte indexiert werden konnte. Beide werden jetzt zusammengeführt (`.codebeaconignore` gewinnt bei Konflikten); das Hinzufügen kann nur *mehr* ausschließen.
- **Keine maschinenabsoluten Pfade mehr in committeten Artefakten** — `source_file`-Werte an Edges/Links (der Großteil von `beacon.json`) und die `Source:`-Zeilen in Wiki-/Obsidian-Notizen behielten absolute `/Users/du/...`-Pfade, sodass der committete Index nicht portabel war und lokale Pfade preisgab. Alle sind jetzt projekt-relativ (inklusive Edges und projektübergreifender `shares_db_entity`-Dateien).
- **Gleichnamige Symbole in unterschiedlichen Verzeichnissen überschreiben sich nicht mehr** — Wiki-/Obsidian-Dateinamen wurden ohne Groß-/Kleinschreibungs-Faltung aus dem Label abgeleitet, sodass unter macOS/Windows `UserService` und `userService` kollidierten und eine Notiz still verloren ging. Dateinamen sind jetzt kollisions-gesalzen und case-gefaltet; Labels aus reiner Interpunktion (`@`) fallen auf `unnamed` zurück statt auf ein kaputtes `@.md`.
- **Ein beschädigtes `beacon.json` stürzt nicht mehr ab** — `codebeacon affected`, der MCP-Server und `--wiki-only`-Läufe sichern jetzt einen beschädigten/abgeschnittenen Graphen und melden eine klare „Scan erneut ausführen"-Meldung statt eines rohen Tracebacks.
- **Mehr React-Komponenten werden erfasst** — `react.scm` übersah Function-Expression-Komponenten (`const X = function() {…}`), bare-importierte HOCs (`const X = forwardRef(…)` ohne `React.`-Präfix) und nicht exportierte `function X()`-Komponenten. Alle drei werden jetzt extrahiert.
- **Wiki-Links laufen nie ins Leere** — ein Link auf eine nie geschriebene Seite wird zu reinem Text herabgestuft, und ein Link auf einen Artikel in einem Nachbar-Bucket (ein Service → seine Entity) wird auf den korrekten relativen Pfad repariert, statt auf eine fehlende Datei zu zeigen.

---

## Neu in 0.6.7

Folgearbeiten zum graphify-Parity-Audit aus 0.6.6: Grammar-Drift schlägt jetzt laut fehl statt stillschweigend, und Negationen in der Ignore-Datei verlangsamen Scans nicht mehr.

- **Grammar-Drift ist ein lauter Fehler, kein stiller leerer Graph** — wenn eine tree-sitter-Query gegen eine Grammar, die sie unterstützen *soll*, nicht kompiliert (z. B. eine umbenannte Node-Art in einem künftigen Grammar-Update), wirft `run_query` jetzt eine Ausnahme und die Datei wird als `ExtractionFailure` erfasst, statt still nichts zu extrahieren. Zusammen mit den Obergrenzen-Pins aus 0.6.6 und dem Test „jede Query kompiliert gegen jede Grammar, die sie beansprucht" wird Drift nun auf drei unabhängige Weisen erkannt.
- **Eine einzelne `!`-Negation in `.codebeaconignore` erzwingt keinen vollständigen Baum-Durchlauf mehr** — eine Negationsregel irgendwo hat das Verzeichnis-Pruning *überall* deaktiviert, sodass der Scanner in jedes ausgeschlossene Verzeichnis (`node_modules`, `build`, …) hinabstieg, selbst wenn die Negation dort nichts retten konnte. Ein ignoriertes Verzeichnis wird jetzt nur behalten, wenn eine Negation tatsächlich eine Datei *darunter* wieder einschließen könnte; nicht zugehörige `!`-Regeln kosten nichts.
- **Ignore-Globs werden einmal kompiliert** — der gitignore-artige Matcher merkt sich die kompilierte Regex je Muster, statt sie bei jeder Pfadprüfung neu zu bauen (schnellere Erkennung bei tiefen Bäumen mit großen Ignore-Dateien). Semantik unverändert.

---

## Neu in 0.6.6

Ein graphify-Parity-Audit von Upstream v0.8.37–v0.8.40 (und gemeldeten Issues bis #1362): ein „prüfen, dann adversarial widerlegen"-Durchlauf über 32 Kandidaten bestätigte **6 echte Bugs**. Der Hauptpunkt — drei Framework-Extraktoren produzierten still *nichts*.

- **TypeScript-Express/Koa/Fastify-Apps extrahieren jetzt Routen** — `express.scm` hatte die JavaScript-Node-Art für Klassennamen fest verdrahtet, was unter der TypeScript-Grammar ein „Impossible pattern" ist; die gesamte Query kompilierte nicht und der Fehler wurde verschluckt: **TS-Express-Apps extrahierten 0 Routen**. (JavaScript-Apps funktionierten, und die einzige Test-Fixture war `.js`, daher blieb es unbemerkt.) Dieselbe Ursache traf `vue.scm` (Vue-SFCs mit reinem `<script>` → 0 Komponenten). Beide nutzen jetzt einen grammar-neutralen Node-Wildcard, der unter JS und TS kompiliert.
- **Kotlin-Dateien in Spring-Projekten verursachen keinen Fehler mehr** — `spring_boot.scm` ist eine Java-Grammar-Query, durfte aber gegen Kotlin laufen und gab `Invalid node type: marker_annotation` aus, wobei jede `.kt`-Datei verworfen wurde. Kotlin wird jetzt sauber ausgeschlossen (Kotlin-Spring-Boot bräuchte eine eigene Query).
- **tree-sitter-Grammars haben jetzt Versions-Obergrenzen** — `pyproject.toml` pinnte Grammars nach oben offen (`>=0.23`), sodass ein künftiges Grammar-Release, das AST-Node-Arten umbenennt, die Queries still wieder hätte brechen können. Jede Grammar hat nun eine kompatible Obergrenze, und ein neuer Test prüft, dass jede ausgelieferte `.scm` gegen jede beanspruchte Grammar kompiliert.
- **Der Extraktions-Cache ist versioniert** — nach einem Upgrade konnte ein inkrementelles `--update` für unveränderte Dateien Ergebnisse der *alten* Version wiederverwenden (ein Content-Hash erkennt nicht, dass sich der Extraktor geändert hat). Der Cache trägt jetzt die codebeacon-Version und wird bei Abweichung verworfen.
- **Akzentuierte / Nicht-ASCII-Namen werden unter macOS aufgelöst** — `codebeacon query` / `path` / MCP und `affected` normalisieren Labels und Pfade jetzt nach Unicode-NFC, sodass ein aus einem macOS-Dateinamen (als NFD gespeichert) kopierter Name das NFC-Label im Graphen trifft (z. B. `Auditoría`).
- Außerdem: eine beschädigte `cache.json` wird gesichert und neu aufgebaut, statt still zurückgesetzt und überschrieben zu werden.

---

## Neu in 0.6.5

`codebeacon upgrade` funktioniert jetzt überall — bisher ging der Befehl von einer normalen pip-Installation aus und scheiterte auf anderen Maschinen stillschweigend.

- **Erkennung des Installations-Managers** — der upgrade-Befehl erkennt, wie codebeacon installiert wurde, und führt das passende Tool aus: `pip install --upgrade` bei pip, `pipx upgrade codebeacon` bei pipx, `uv tool upgrade codebeacon` bei uv. pipx/uv-tool-venvs kommen *ohne* `pip`-Modul, daher starb der alte bedingungslose `python -m pip`-Aufruf, bevor er irgendetwas tat.
- **Upgrade-Verifikation** — nach dem Upgrade liest ein frischer Interpreter die installierte Version neu ein und meldet `0.6.4 -> 0.6.5`. Hat sich die Version nicht geändert, obwohl PyPI ein neueres Release hat, gibt es eine Warnung, dass das `codebeacon` im PATH zu einer anderen Python-Umgebung gehören könnte — statt eines falschen „Upgrade complete".
- **Handlungsfähige Fehlermeldungen** — eine Umgebung ohne pip zeigt die exakt auszuführenden Befehle; eine PEP-668-Ablehnung (`externally-managed-environment`) erklärt die Lösung (pipx oder ein virtualenv), statt einen rohen pip-Fehler auszugeben. Der Befehl zeigt außerdem vorab die aktuelle Version neben der neuesten auf PyPI.

---

## Neu in 0.6.4

Deep-dive-Aufräumarbeit — Ausgaben landen dort, wo man nach ihnen sucht, plus zwei Bugs mit stillem Datenverlust, gefunden bei der Verifikation an einem Workspace mit 47 Projekten.

- **Deep-dive schreibt auf genau zwei Ebenen** — jede *Repo-Wurzel* (ein Verzeichnis mit eigenem `.git` oder `codebeacon.yaml`) und die *Scan-Wurzel*. Die Framework-Ordner eines Monorepos (`mono/landing`, `mono/server`) bekommen nicht mehr jeweils ein eigenes `.codebeacon/` + CLAUDE.md; ihr kombinierter Graph liegt unter `mono/.codebeacon/`, und die Scan-Wurzel trägt den vollständigen Workspace-Graphen, sodass jedes Projekt von einer Stelle aus auffindbar ist. Deep-dive *innerhalb* eines Monorepos auszuführen erzeugt jetzt eine einzige Wurzel-Ausgabe statt einer pro Unterordner.
- **Cache-Schlüssel sind nach Framework namespaced** — eine Repo-Gruppe teilt sich einen Cache, und ein Elternprojekt, das die Dateien eines verschachtelten Projekts zuerst durchlief (`desktop/` als sveltekit über `desktop/src-tauri`), vergiftete den Cache zuvor mit leeren Ergebnissen, die das verschachtelte Projekt (tauri) dann wiederverwendete — und so stillschweigend alle seine Routen und Entitäten verlor.
- **Grammatik-Lade-Race behoben** — zwei parallele Extraktions-Worker, die auf eine ungecachte tree-sitter-Grammatik trafen, bauten jeweils eine eigene `Language`-Instanz; die Dateien des unterlegenen Threads fielen anschließend durch einen Identitätscheck und extrahierten zu **nichts** — keine Warnung, kein Fehlereintrag, nur ein paar Dateien, denen bei großen Scans zufällig alle Routen fehlten. Der erste Ladevorgang ist jetzt auf eine einzige geteilte Instanz gelockt (über 20 aufeinanderfolgende Vollscans als stabil verifiziert).

---

## Neu in 0.6.3

Bugfix-Release — ein graphify-Paritätsaudit (Upstream 3.–10. Juni) plus ein unabhängiges Audit von codebeacons eigenem Code: **16 Fixes**, Ende-zu-Ende verifiziert mit einem `--deep-dive`-Workspace-Scan über 47 Projekte (5.226 Knoten / 8.715 Kanten).

- **Git-Hooks feuern jetzt überall** — der Post-Commit-Rebuild-Hook pinnt den installierenden Python-Interpreter ins Skript und löst sich per `subprocess` statt `nohup` vom Prozess, sodass er in GUI-Git-Clients (Sublime Merge, GitKraken), CI-Runnern und unter Windows funktioniert — Umgebungen, in denen der `codebeacon`-Launcher nicht auf dem `PATH` liegt und der alte Hook stillschweigend nichts tat. `codebeacon hook install` erneut ausführen, um den Fix zu übernehmen; der Merge-Driver wird auf dieselbe Weise gepinnt.
- **Auskommentierte JS/TS-Imports erzeugen keine Kanten mehr** — die Regex-Durchläufe für Barrel-Reexports und `require()` entfernen jetzt zuerst `//`- und `/* */`-Kommentare (string-literal-bewusst). Ein auskommentiertes `export * from './legacy'` erzeugte zuvor eine Phantomkante und falsche Importzyklen.
- **`from pkg import name` bindet das echte Ziel (Python)** — der Import-Extraktor erfasst nun die importierten Namen, sodass `from auth.services import UserService` auf den `UserService`-Knoten verlinkt und `from src.services import enricher` auf das Submodul. Zuvor wurde nur das letzte Segment des Modulpfads probiert, wodurch Testdateien unverbunden blieben. Aliase (`import x as y`) lösen zum wahren Symbolnamen auf.
- **„High-Impact Files" sind tatsächlich high-impact** — das Hub-Ranking (CLAUDE.md, `analyze`) zählte Import-*Fan-out* über das `source_file` der Kante (immer der Importeur), sodass Einstiegspunkte echte geteilte Module mit pro Knoten aufgeblähten Zahlen überholten („imported by 392 files" in einem 60-Dateien-Repo). Beide Kopien zählen jetzt distinkte importierende Dateien pro importierter Datei.
- **DI-`injects`-Kanten tragen echte Dateipfade** — aufgelöste Dependency-Injection-Kanten stempelten die Graphknoten-ID (`proj::Name`) in `source_file`; sie tragen jetzt die tatsächliche Datei des Quellknotens.
- **Verschachtelte Ktor-Routenpräfixe werden verkettet** — `route("/api") { route("/v1") { get("/users") } }` extrahiert `/api/v1/users`, statt jedes äußere Präfix zu verwerfen.
- **Routen mit gleichem Pfad matchen beide** — wenn zwei Services dieselbe URL exponieren (Gateway + Upstream), behält die `calls_api`-Anreicherung nicht mehr stillschweigend nur die letzte.
- **Konfiguration toleriert spärliches YAML** — leer gelassene `output:` / `wave:` / `semantic:` stürzen nicht mehr mit `AttributeError` ab; ein verirrter nackter `-` unter `projects:` löst einen sauberen Konfigurationsfehler statt eines `TypeError` aus.
- **Spracherkennung überspringt Vendor-Verzeichnisse** — die Fallback-Sprachabstimmung klammert `node_modules` / `.git` / `dist` aus, sodass ein Python-Repo mit vendored JS nicht mehr als *javascript* erkannt wird (und die Discovery nicht mehr Zehntausende Vendor-Dateien durchkriecht).
- **Wiki-Links passen zu ihren Dateien** — Link-Ziele verwenden jetzt exakt dieselbe Dateinamen-Transformation, mit der der Generator schreibt, sodass Labels mit Leerzeichen, `#`, Klammern oder Generics keine toten Links mehr erzeugen.
- Außerdem: deterministische Reihenfolge der Anreicherungskanten, ein Build-Guard gegen `None`-Labels, ein thread-sicherer Extraktions-Cache, FastAPI-`Depends()`-Geisterreferenzen entfernt und Obsidian-Service-Ordnernamen byte-begrenzt.

---

## Neu in 0.6.2

- **Deterministische Community-IDs** — gleich große Communities wurden nach der Enumerationsreihenfolge des Partitionierers nummeriert, was bei einem No-op-Rescan 77–88 % von `beacon.json` umwälzte; identische Gruppierungen erhalten jetzt immer identische IDs.
- **Notiz-Dateinamen byte-begrenzt** — ein über 85 Zeichen langer CJK-Klassenname sprengte das 255-Byte-Dateisystemlimit und ließ den gesamten Wiki-/Obsidian-Export mit `ENAMETOOLONG` abstürzen; jetzt bei 200 UTF-8-Bytes gekappt, mit kollisionssicherem Hash-Suffix.
- **DI-Kanten für FastAPI / Laravel / ASP.NET wiederhergestellt** — aufgelöste `Depends()`- / `bind()`- / `AddScoped<>`-Referenzen waren nach Dateipfad indiziert, während Knoten nach Projekt indiziert sind, sodass die Kanten stillschweigend verworfen wurden; sie werden jetzt auf die finalen Knoten-IDs umgemappt.
- **Interface-→-Implementierung-DI wiederbelebt** — `implements`/`extends`-Metadaten wurden von keinem Extraktor befüllt, sodass interface-typisierte Injektion nie aufgelöst wurde; Spring, ASP.NET, NestJS und Angular verdrahten sie jetzt durchgängig.

---

## Neu in 0.6.1

Patch-Release — Extraktionskorrektheit und reproduzierbare Ausgabe.

- **Sechs Framework-Extraktoren wiederhergestellt** — die tree-sitter-Queries für `laravel`, `angular`, `aspnet`, `actix`, `ktor` und `vapor` waren mit aktuellen Grammatik-Versionen aus dem Takt geraten und extrahierten **nichts**: die Query ließ sich nicht kompilieren und der Fehler wurde als Warnung verschluckt. Alle sechs kompilieren und extrahieren nun gegen die mitgelieferten Grammatiken (Laravel `scope:`/`name:`-Felder, Angular `export class`-Dekoratoren, ASP.NET `invocation_expression`-Felder, Actix geschwister-verankerte Attribute, Kotlin-1.x-Knotenumbenennungen, Swift-0.0.1-Knotensatz) — jeweils mit Regressionstest gegen erneutes stilles Brechen.
- **Reproduzierbare `beacon.json`** — `source_file`-Pfade der Knoten werden vor der Serialisierung relativ zum jeweiligen Projekt-Root umgeschrieben, sodass das Scannen desselben Commits auf zwei Maschinen einen byte-identischen Graphen erzeugt statt absolute Pfade im Diff zu wälzen.
- **`affected` meldet nicht mehr zu viel** — der Seed-Abgleich geänderter Dateien ist nun pfadsegment-ausgerichtet, sodass `src/user.py` keine fremden Knoten wie `foosrc/user.py` mehr hineinzieht.
- **`semantic-apply`-Absturz behoben** — ein `confidence_score: null` in einer archivierten/migrierten JSONL-Kante bricht den Lauf nicht mehr mit `TypeError` ab, sondern wird wie im Rest der Pipeline auf den sicheren Standard normalisiert.
- **NetworkX-3.6-Vorwärtskompatibilität** — `beacon.json` wird mit explizitem `edges="links"`-Schlüssel geschrieben, damit eine geänderte Upstream-Voreinstellung das Festplattenformat nicht still verändert; der MCP-Server lädt über dieselbe Kompatibilitätsschicht.
- **Obsidian-Vault-Hygiene** — die Bereinigung veralteter Notizen erfasst den gesamten Vault (Root + verschachtelt), und der Cross-Language-Import-Filter richtet sich nach der echten Quellsprache der Notiz statt nach einem Dateinamen-Suffix, das nie passte.
- **gitignore-Semantik** — verankerte Muster wie `build/*.js` lassen `*` nicht mehr über `/` greifen, sodass verschachtelte Dateien nicht fälschlich ignoriert werden.
- **Next.js App Router** — JS-basierte `page.js` / `page.jsx`-Routen werden nun erkannt (zuvor nur `.ts` / `.tsx`).
- **DI-Zuordnungskorrekturen** — FastAPI `Depends()` und Angular-Konstruktor-Injektion werden per Byte-Range der umschließenden Funktion/Klasse zugeordnet statt der ersten/letzten in der Datei; Razor `@using` erzeugt keine doppelten Kanten mehr.

---

## Neu in 0.6.0

- **`codebeacon affected`** — nimmt eine Liste geänderter Dateien (oder via `--base <ref>` ein git diff) und gibt jeden nachgelagerten Graphknoten aus. Für CI-Risikoeinstufung und PR-Reviews.
- **`.NET`-Projektdateien** — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml` werden jetzt geparst: `<ProjectReference>` / `<PackageReference>` werden zu Graphkanten, Razor-Direktiven `@inherits` / `@inject` / `@using` verbinden Blazor-Seiten mit ihren Backing-Typen.
- **JS/TS Barrel-Reexports** — `export { X } from './mod'` und `export * from './mod'` erzeugen jetzt explizite `re_exports`-Kanten, sodass Next.js-/Monorepo-Barrels nicht mehr mit 0 Imports erscheinen.
- **`--exclude PATTERN`-Flag** für `scan` / `sync`, plus automatischer Fallback auf `.gitignore`, wenn `.codebeaconignore` fehlt.
- **`codebeacon install --project [PATH]`** — installiert den `/codebeacon`-Skill nach `<PATH>/.claude/` statt `~/.claude/`, damit Teams eine SKILL.md-Version pro Repo festpinnen können.
- **Wiki repariert sich selbst** — `--update`-Läufe entfernen jetzt `wiki/<project>/{controllers,services,entities,components}/*.md`-Dateien, deren Graphknoten nicht mehr existieren.
- **Shrink-Guard bei expliziten Löschungen gelockert** — im `--update`-Modus wird ein kleineres `beacon.json` nicht mehr abgelehnt, wenn der Cache die Löschungen bereits berücksichtigt hat; bei stiller Korruption greift die Sperre weiterhin.
- **Datei-übergreifende Deklarations-Union** — Swift `extension Foo`, C# partial classes, Ruby reopened classes vereinen ihre `fields` / `methods` zu einem kanonischen Knoten, statt vom letzten Schreiber überschrieben zu werden.
- **Härtere Suche** — `BeaconIndex` nutzt `casefold()`, sodass deutsches `ß`, türkisches `i/İ`, griechisches `σ/ς` und CJK-Labels korrekt matchen.
- **Reichhaltigerer Semantik-Kontext** — jeder Task-Chunk bringt jetzt Graph-Caller und -Callees als `neighbors` mit, damit das LLM bei echten Knotenlabels bleibt; `SKILL.md` ergänzt **Step 0 — Constrained query expansion**, sodass `/codebeacon query`-Flows keine Phantom-Tokens erfinden können.
- **`semantic-apply` Zero-Yield-Guard** — wenn jeder Chunk mit 0 Kanten archiviert wurde, beendet die CLI mit Exit 1, sodass CI stille LLM-Fehler bemerkt.
- **ArkTS (`.ets`) und Worktree-Sicherheit** — `.ets` wird eingesammelt; verschachtelte `worktrees/`-Verzeichnisse werden übersprungen, damit verlinkte Worktrees nicht doppelt indexiert werden.

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
