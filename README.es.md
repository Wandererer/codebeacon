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
  Análisis AST de código fuente y generación de contexto para IA — grafo de conocimiento multi-framework unificado
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## Novedades en 0.6.3

Versión de corrección de errores — una auditoría de paridad con graphify (upstream 3–10 de junio) más una auditoría independiente del propio código de codebeacon: **16 correcciones**, verificadas de extremo a extremo con un escaneo de workspace `--deep-dive` de 47 proyectos (5.226 nodos / 8.715 aristas).

- **Los hooks de git ahora se disparan en todas partes** — el hook de reconstrucción post-commit fija el intérprete de Python que hizo la instalación dentro del script y se desacopla vía `subprocess` en lugar de `nohup`, así funciona en clientes git con GUI (Sublime Merge, GitKraken), runners de CI y en Windows — entornos donde el lanzador `codebeacon` no está en el `PATH` y el hook antiguo no hacía nada en silencio. Vuelve a ejecutar `codebeacon hook install` para recoger la corrección; el merge driver se fija de la misma manera.
- **Los imports JS/TS comentados ya no crean aristas** — las pasadas de regex de re-exports barrel y `require()` ahora eliminan primero los comentarios `//` y `/* */` (con conciencia de literales de cadena). Un `export * from './legacy'` comentado producía una arista fantasma y falsos ciclos de import.
- **`from pkg import name` enlaza al objetivo real (Python)** — el extractor de imports ahora captura los nombres importados, así `from auth.services import UserService` enlaza al nodo `UserService` y `from src.services import enricher` enlaza al submódulo. Antes solo se probaba el último segmento de la ruta del módulo, dejando los archivos de test desconectados. Los alias (`import x as y`) se resuelven al nombre real del símbolo.
- **"High-Impact Files" es realmente de alto impacto** — el ranking de hubs (CLAUDE.md, `analyze`) contaba el *fan-out* de imports vía el `source_file` de la arista (siempre el importador), así los puntos de entrada superaban a los módulos compartidos reales con recuentos inflados por nodo ("imported by 392 files" en un repo de 60 archivos). Ambas copias ahora cuentan archivos importadores distintos por archivo importado.
- **Las aristas `injects` de DI llevan rutas de archivo reales** — las aristas de inyección de dependencias resueltas estampaban el ID del nodo del grafo (`proj::Name`) en `source_file`; ahora llevan el archivo real del nodo de origen.
- **Los prefijos de rutas anidadas de Ktor se concatenan** — `route("/api") { route("/v1") { get("/users") } }` extrae `/api/v1/users` en lugar de descartar todos los prefijos exteriores.
- **Las rutas con la misma URL coinciden ambas** — cuando dos servicios exponen la misma URL (gateway + upstream), el enriquecimiento `calls_api` ya no conserva en silencio solo la última.
- **La configuración tolera YAML escaso** — dejar vacíos `output:` / `wave:` / `semantic:` ya no provoca un `AttributeError`; un `-` suelto bajo `projects:` lanza un error de configuración limpio en lugar de un `TypeError`.
- **La detección de lenguaje omite directorios vendorizados** — el voto de lenguaje de respaldo poda `node_modules` / `.git` / `dist`, así un repo Python con JS vendorizado ya no se detecta como *javascript* (y el descubrimiento ya no rastrea decenas de miles de archivos vendorizados).
- **Los enlaces del wiki coinciden con sus archivos** — los destinos de los enlaces ahora usan exactamente la misma transformación de nombre de archivo con la que escribe el generador, así las etiquetas con espacios, `#`, paréntesis o genéricos ya no producen enlaces muertos.
- Además: orden determinista de las aristas de enriquecimiento, una guarda de build contra etiquetas `None`, una caché de extracción segura entre hilos, referencias fantasma de `Depends()` de FastAPI eliminadas, y nombres de carpetas de servicios de Obsidian limitados en bytes.

---

## Novedades en 0.6.2

- **IDs de comunidad deterministas** — las comunidades del mismo tamaño se numeraban según el orden de enumeración del particionador, removiendo el 77–88 % de `beacon.json` en un re-escaneo sin cambios; agrupaciones idénticas ahora reciben siempre IDs idénticos.
- **Nombres de archivo de notas limitados en bytes** — un nombre de clase CJK de más de 85 caracteres desbordaba el límite de 255 bytes del sistema de archivos y hacía fallar toda la exportación wiki/Obsidian con `ENAMETOOLONG`; ahora se limita a 200 bytes UTF-8 con un sufijo hash a prueba de colisiones.
- **Aristas de DI restauradas para FastAPI / Laravel / ASP.NET** — las referencias resueltas de `Depends()` / `bind()` / `AddScoped<>` se indexaban por ruta de archivo mientras los nodos se indexan por proyecto, así las aristas se descartaban en silencio; ahora se remapean a los IDs finales de los nodos.
- **DI interfaz → implementación revivida** — los metadatos `implements`/`extends` nunca eran poblados por ningún extractor, así la inyección tipada por interfaz nunca se resolvía; Spring, ASP.NET, NestJS y Angular ahora la conectan de extremo a extremo.

---

## Novedades en 0.6.1

Versión de parche — corrección de extracción y salida reproducible.

- **Seis extractores de frameworks restaurados** — las queries tree-sitter de `laravel`, `angular`, `aspnet`, `actix`, `ktor` y `vapor` se habían desincronizado de las versiones actuales de las gramáticas y no extraían **nada**: la query no compilaba y el error se silenciaba como advertencia. Las seis ahora compilan y extraen contra las gramáticas incluidas (campos `scope:`/`name:` de Laravel, decoradores `export class` de Angular, campos `invocation_expression` de ASP.NET, atributos anclados a hermanos de Actix, renombrados de nodos de Kotlin 1.x, conjunto de nodos de Swift 0.0.1), cada una con un test de regresión para que no vuelvan a romperse en silencio.
- **`beacon.json` reproducible** — las rutas `source_file` de los nodos se reescriben relativas a la raíz de cada proyecto antes de serializar, así escanear el mismo commit en dos máquinas produce un grafo idéntico byte a byte en lugar de remover rutas absolutas en los diffs.
- **`affected` ya no sobre-reporta** — la coincidencia de archivos cambiados está alineada por segmentos de ruta, de modo que `src/user.py` ya no arrastra nodos ajenos como `foosrc/user.py`.
- **Corrección de fallo en `semantic-apply`** — un `confidence_score: null` en una arista JSONL archivada/migrada ya no aborta la ejecución con `TypeError`; se normaliza al valor seguro por defecto como el resto del pipeline.
- **Compatibilidad futura con NetworkX 3.6** — `beacon.json` se escribe con la clave explícita `edges="links"` para que un cambio de valor por defecto upstream no altere en silencio el formato en disco; el servidor MCP carga a través de la misma capa de compatibilidad.
- **Higiene del vault de Obsidian** — la limpieza de notas obsoletas barre todo el vault (raíz + anidado), y el filtro de imports entre lenguajes se basa en el lenguaje real de la nota en vez de un sufijo de nombre de archivo que nunca coincidía.
- **Semántica de gitignore** — los patrones anclados como `build/*.js` ya no permiten que `*` cruce `/`, así los archivos anidados no se ignoran por error.
- **App Router de Next.js** — ahora se descubren las rutas `page.js` / `page.jsx` basadas en JS (antes solo `.ts` / `.tsx`).
- **Correcciones de atribución de DI** — `Depends()` de FastAPI y la inyección por constructor de Angular se atribuyen a la función/clase contenedora por rango de bytes en vez de la primera/última del archivo; `@using` de Razor ya no emite aristas duplicadas.

---

## Novedades en 0.6.0

- **`codebeacon affected`** — recibe una lista de archivos cambiados (o vía `--base <ref>` un git diff) e imprime todos los nodos del grafo aguas abajo. Pensado para puntuación de riesgo en CI y revisión de PR.
- **Archivos de proyecto `.NET`** — ahora se analizan `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml`: `<ProjectReference>` / `<PackageReference>` se convierten en aristas del grafo, y las directivas Razor `@inherits` / `@inject` / `@using` vinculan las páginas Blazor con sus tipos de respaldo.
- **Re-exports barrel JS/TS** — `export { X } from './mod'` y `export * from './mod'` producen aristas explícitas `re_exports`, para que los barrels de Next.js / monorepo dejen de mostrar 0 imports.
- **Flag `--exclude PATTERN`** para `scan` / `sync`, más respaldo automático a `.gitignore` cuando falta `.codebeaconignore`.
- **`codebeacon install --project [PATH]`** — instala el skill `/codebeacon` en `<PATH>/.claude/` en vez de `~/.claude/`, para que los equipos fijen una versión de SKILL.md por repositorio.
- **El wiki se auto-repara** — las ejecuciones con `--update` ahora eliminan los archivos `wiki/<project>/{controllers,services,entities,components}/*.md` cuyo nodo del grafo ya no existe.
- **Guarda anti-encogimiento relajada para borrados explícitos** — en modo `--update`, ya no se rechaza escribir un `beacon.json` más pequeño si la caché ya contabilizó los archivos eliminados; la guarda sigue activa frente a corrupción silenciosa.
- **Unión de declaraciones cross-file** — `extension Foo` de Swift, `partial class` de C# y clases reabiertas de Ruby unen sus `fields` / `methods` en un único nodo canónico en lugar de que gane el último que escribe.
- **Consulta endurecida** — `BeaconIndex` usa `casefold()`, por lo que `ß` alemán, `i/İ` turco, `σ/ς` griego y etiquetas CJK hacen match correctamente.
- **Contexto semántico más rico** — cada chunk de tarea ahora lleva los llamadores y llamados del grafo en `neighbors`, manteniendo al LLM anclado en etiquetas reales. `SKILL.md` añade **Step 0 — Constrained query expansion** para que los flujos `/codebeacon query` no inventen tokens fantasma.
- **Guarda «cero rendimiento» de `semantic-apply`** — si todos los chunks archivaron 0 aristas, la CLI termina con exit 1, para que CI detecte fallos silenciosos del LLM.
- **ArkTS (`.ets`) y seguridad de worktree** — `.ets` se recoge; los directorios `worktrees/` anidados se omiten para evitar la indexación duplicada de worktrees enlazadas.

---

## ¿Por qué codebeacon?

Cada vez que se abre una nueva sesión de codificación con IA, el asistente comienza desde cero. No conoce sus rutas, su capa de servicios, su modelo de entidades ni cómo se comunican sus microservicios. Se pasa el inicio de cada sesión pegando archivos, explicando la estructura y restableciendo el contexto.

Las herramientas existentes resuelven esto de forma parcial. Los analizadores de rutas mapean sus controladores, pero omiten las dependencias de servicios. Las herramientas de grafos de conocimiento capturan relaciones, pero ignoran la superficie de la API. El resultado es ejecutar ambas herramientas, unir la salida manualmente y repetirlo cada vez que cambia el código.

**codebeacon unifica ambos enfoques en un único CLI.** Un comando escanea toda la base de código con análisis AST de tree-sitter, resuelve la inyección de dependencias entre archivos, detecta clústeres de comunidades en la arquitectura y escribe un mapa de contexto listo para usar directamente en `CLAUDE.md`, `.cursorrules` y `AGENTS.md`.

---

## Características principales

- **Pipeline unificado** — análisis de rutas/controladores + grafo de conocimiento en una sola herramienta
- **27 frameworks, 9 lenguajes** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor
- **Basado en tree-sitter** — análisis AST estructural, no expresiones regulares; gramáticas de lenguaje incluidas por defecto
- **Resolución DI en 2 pasos** — Pass 1 extrae nodos AST locales; Pass 2 construye una tabla de símbolos global y resuelve los mapeos Interface → Implementation
- **Arquitectura Wave merge** — archivos procesados en chunks paralelos y fusionados globalmente; maneja grandes monorepos sin problemas de memoria
- **Múltiples formatos de salida** — grafo JSON, wiki Markdown, Obsidian Vault, mapas de contexto para IA, servidor MCP, HTML interactivo
- **Exploración visual** — `beacon.html` (árbol colapsable D3) y `callflow.html` (diagramas Mermaid de arquitectura por comunidad) regenerados en cada escaneo
- **Detección de comunidades** — clustering Leiden/Louvain revela los límites arquitectónicos reales
- **Caché incremental** — SHA-256 + ruta rápida por mtime/size; los cambios de mtime sin cambio de contenido (Obsidian/iCloud/Nextcloud) nunca disparan re-extracción innecesaria
- **Promoción de confianza** — los edges `calls` entre archivos pasan de INFERRED a EXTRACTED automáticamente cuando un import explícito prueba el binding
- **Escrituras seguras** — beacon.json tiene shrink guard (una ejecución parcial nunca puede sobrescribir un grafo completo) y estampa `built_at_commit` para que REPORT.md marque la salida como stale frente al HEAD actual
- **Amigable para múltiples desarrolladores** — `codebeacon hook install` registra un git merge driver para `beacon.json` y un hook post-commit de rebuild incremental, así dos devs escaneando la misma rama nunca producen conflictos de merge en el grafo
- **Salida endurecida** — los frontmatter YAML y las etiquetas MCP se sanitizan: U+2028/U+2029, controles C0 y marcas bidi se eliminan antes de llegar a Obsidian, Cursor o al agente
- **`.codebeaconignore` estilo gitignore** — last-match-wins con negación `!`, patrones de directorio (`build/`), patrones anclados (`/secrets.txt`), reglas de espacio final
- **Cero configuración** — detecta frameworks y lenguajes automáticamente; genera `codebeacon.yaml` para ejecuciones posteriores
- **Modo Deep Dive** — `--deep-dive` genera `.codebeacon/` + `CLAUDE.md` propios para cada sub-proyecto; ejecutar el comando de actualización desde **cualquier** sub-proyecto sincroniza automáticamente todos los proyectos del workspace
- **Auto-redescubrimiento del workspace** — en cada `scan`/`sync`, codebeacon re-escanea el workspace y añade automáticamente al `codebeacon.yaml` los nuevos proyectos antes de extraer, de modo que los sub-proyectos recién añadidos nunca se omitan silenciosamente; usa `--no-rediscover` para optar por el modo de configuración curada manualmente
- **Enriquecimiento semántico estilo Graphify** — tras la extracción AST, el skill despacha un subagente paralelo por chunk para emitir fragmentos completos de grafo `{nodes, edges, hyperedges}` con 8 tipos de relación (`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`) y confianza EXTRACTED/INFERRED/AMBIGUOUS; en Claude Code el subagente se ejecuta un nivel por debajo del modelo host (Opus→Sonnet, Sonnet→Haiku) para mantener el gasto proporcional al tamaño del corpus. El AST posee los nodos de código; el LLM solo puede aportar nodos `concept`/`document`/`paper`. Los archivos 0.3.x existentes se replayean con el nuevo esquema sin cambios
- **Modo de conocimiento (`codebeacon knowledge`)** — escanea notas markdown (ADRs, actas de reunión, retros, specs, research) y produce un único `KNOWLEDGE.md` junto a `.codebeacon/`. Clasifica automáticamente por patrones de nombre de fichero y de encabezados, parsea frontmatter YAML de Obsidian y `[[backlinks]]`, y muestra arriba un resumen de "Key Decisions" + "Open Questions" para que el agente entienda *por qué* el código tiene la forma que tiene. Heurística pura — sin llamadas a LLM
- **Atajo de ruta** — `codebeacon ./src` ahora equivale a `codebeacon scan ./src`; cuando el primer argumento no es un subcomando registrado, `scan` se inyecta automáticamente, conservando la memoria muscular de `graphify <path>` / `codesight <path>`
- **Pipeline semántico endurecido** — `semantic-apply` protege contra JSONL del agente mal formado (líneas null/lista/code-fence, campos faltantes), coerce valores rotos de `confidence_score` (None/NaN/string/fuera de rango) a un default seguro, snapshotea `beacon.json` → `beacon.json.bak` antes del merge para que la baseline AST siempre sea recuperable, y regenera `beacon.html` + `callflow.html` para que los exports visuales reflejen los nuevos edges inferidos
- **Guardas de ficheros/directorios sensibles** — los directorios `secrets/`, `credentials/`, `.ssh/`, `.aws/`, `.gnupg/` se omiten siempre; los nombres de fichero que coincidan con patrones de credenciales (`api_token`, `oauth_token`, `private_key`, `client_secret`; variantes con guion bajo *y* guion) quedan excluidos del recolector antes de llegar a los extractores

---

## Inicio rápido

```bash
pip install codebeacon

codebeacon scan .
```

codebeacon detecta los tipos de proyecto, extrae rutas/servicios/entidades/componentes, construye el grafo de conocimiento y escribe todo en `.codebeacon/`.

Para un workspace multi-proyecto:

```bash
codebeacon scan /ruta/al/workspace   # detecta todos los proyectos, genera codebeacon.yaml
codebeacon sync                      # ejecuciones posteriores vía configuración
```

---

## Frameworks soportados

| Lenguaje | Frameworks |
|----------|-----------|
| Java / Kotlin | Spring Boot, Ktor |
| Python | Django, FastAPI, Flask |
| JavaScript / TypeScript | Express, Fastify, Koa, NestJS, React, Next.js, Vue, Nuxt, Angular, SvelteKit |
| Go | Gin, Echo, Fiber |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web, Axum, Tauri, Rocket, Warp |
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`); `.sln` / `.csproj` / `.fsproj` / `.vbproj` analizados para `ProjectReference` + `PackageReference` |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) recogido — los extractores son agnósticos al framework |

---

## Arquitectura

codebeacon ejecuta un pipeline de extracción en 2 pasos:

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         AST local          Tabla de     Filtro      HTTP API
                         por chunk          símbolos     artefactos  DB compartida
                         (Pass 1)           (Pass 2)
```

**Pass 1 — Extracción Wave:** Los archivos se procesan en chunks paralelos. Cada archivo pasa por cinco extractores: rutas, servicios, entidades, componentes y dependencias. Los resultados se cachean por SHA-256.

**Pass 2 — Construcción del grafo:** Se fusionan todos los resultados Wave. Una tabla de símbolos global resuelve las referencias de inyección de dependencias no resueltas — mapeos Interface→Implementation que las herramientas de un solo paso no capturan.

---

## Estructura de salida

Después del escaneo, los archivos de mapa de contexto se actualizan en la raíz del proyecto (el contenido del usuario se conserva) y el grafo de conocimiento en `.codebeacon/`:

```
project-root/
  CLAUDE.md              ← mapa de contexto para IA (bloque codebeacon fusionado; contenido del usuario conservado)
  .cursorrules           ← contexto para Cursor IDE (misma estrategia de fusión)
  AGENTS.md              ← contexto para OpenAI Agents / Codex (misma estrategia de fusión)
  .codebeacon/
    beacon.json          ← grafo de conocimiento completo; incrusta `meta.built_at_commit`
    beacon.html          ← visor de árbol colapsable D3 (abrir en cualquier navegador)
    callflow.html        ← diagramas Mermaid de call-flow agrupados por comunidad
    REPORT.md            ← nodos dios, conexiones sorprendentes, archivos hub, frescura
    wiki/
      index.md
      overview.md
      routes.md
      <project>/
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian Vault (una nota por nodo del grafo)
```

### Modo Deep Dive

Con `--deep-dive`, cada sub-proyecto recibe su propio `.codebeacon/` + `CLAUDE.md`. Claude Code carga los archivos `CLAUDE.md` de forma jerárquica, por lo que una sesión en `api-server/` carga tanto la visión general del workspace como los detalles específicos del proyecto.

La clave: un comando de actualización desde **cualquier sub-proyecto** sincroniza todo el workspace automáticamente:

```bash
# Primer escaneo deep dive
codebeacon scan /workspace --deep-dive

# Más tarde, desde cualquier sub-proyecto — encuentra la config padre y actualiza TODOS los proyectos
cd /workspace/api-server
codebeacon scan . --update
```

Estructura de salida:
```
workspace/
  CLAUDE.md                   ← combinado (todos los proyectos)
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← grafo combinado
  api-server/
    CLAUDE.md                 ← solo api-server
    .codebeacon/
  frontend/
    CLAUDE.md                 ← solo frontend
    .codebeacon/
```

## Exploración visual

Cada escaneo escribe dos archivos HTML autocontenidos junto a `beacon.json`:

```
.codebeacon/beacon.html      # árbol colapsable D3 v7 — abrir en cualquier navegador
.codebeacon/callflow.html    # diagramas Mermaid de arquitectura, uno por comunidad
```

Sin build, sin servidor estático, sin copy-paste. Abre el archivo, haz clic para expandir proyectos → tipos → nodos; hover para ver paths y degree. `callflow.html` agrupa el grafo por comunidad y renderiza cada una como flowchart Mermaid, con los edges salientes a otras comunidades en una tabla plegada.

---

## Flujo multi-desarrollador

Dos devs ejecutando `codebeacon scan` en la misma rama producen `beacon.json` ligeramente distintos — un punto clásico de conflicto de merge. `codebeacon hook install` lo resuelve:

```bash
codebeacon hook install            # en la raíz del repo
```

Registra:

- un **git merge driver** que union-mergea dos `beacon.json` en uno (nodos deduplicados por ID, edges deduplicados por `(source, target, relation)`),
- una entrada `.gitattributes` apuntando `*beacon.json` al driver,
- un **hook post-commit** que ejecuta `codebeacon scan . --update` en background para que el grafo nunca quede atrás de los commits. Salida en `~/.cache/codebeacon-rebuild.log`.

El merge driver siempre sale con 0 — la regeneración del grafo nunca bloquea un merge real.

---

## Garantías de seguridad

Invariantes que el writer impone en cada escaneo exitoso:

| Guard | Lo que previene |
|---|---|
| **Shrink guard** | Una extracción parcial fallida o una ejecución interrumpida nunca puede sobrescribir un `beacon.json` completo y más grande. Bypass con `force=True` desde la API. |
| **Escritura atómica** | `beacon.json` se escribe vía `os.replace`, así que el archivo está completo o intacto — nunca a medio escribir. |
| **Estampa `built_at_commit`** | `beacon.json` incrusta `meta.built_at_commit` (SHA completo) y `REPORT.md` muestra el SHA corto. Si HEAD avanzó, el reporte marca el grafo como `⚠ stale` con un hint de remediación. |
| **Hardening de frontmatter / etiquetas** | Los valores YAML van entre comillas simples y escapan U+2028, U+2029, tab y controles C0; la salida MCP pasa todas las etiquetas por el mismo sanitizer. Un identificador malicioso en código fuente no puede romper el parser YAML de Obsidian ni inyectar secuencias de control en el contexto de un agente LLM. |

---

## Configuración

Ejecuta `codebeacon init` para generar `codebeacon.yaml`, o escríbelo manualmente:

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # opcional: se detecta automáticamente

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
  chunk_size: 300              # archivos por chunk
  max_parallel: 5              # hilos paralelos

semantic:
  enabled: false               # solo extracción de comentarios estructurados;
                               # --semantic lo activa. El AI-semántico NO vive aquí:
                               # lo dispara el skill /codebeacon (= el agente en ejecución).

deep_dive: false               # establecer true para salida por proyecto
```

### .codebeaconignore

Coloca un archivo `.codebeaconignore` en la raíz del proyecto para excluir directorios o archivos del escaneo. Semántica compatible con `.gitignore` — last-match-wins con negación `!`, patrones anclados (`/foo`), patrones solo-directorio (`build/`), comentarios:

```
# .codebeaconignore

# directorios
build/
generated/
fixtures/

# anclado solo a la raíz
/scripts/local-only.ts

# patrones glob
*.gen.ts
**/snapshots/**

# re-incluir un archivo aunque build/ esté ignorado
!build/manifest.ts
```

`!pattern` re-incluye una ruta previamente ignorada; reglas posteriores anulan las anteriores. El walker poda directorios cuyo nombre coincida con las reglas, pero pospone la poda cuando alguna regla de negación pueda re-incluir un archivo anidado.

---

## Integración con IA

### Skill de Claude Code (`/codebeacon`)

Instala codebeacon como comando slash de Claude Code:

```bash
pip install codebeacon
codebeacon install
```

Copia `SKILL.md` en `~/.claude/skills/codebeacon/` y registra el trigger `/codebeacon` en `~/.claude/CLAUDE.md`. Reinicia tu sesión de Claude Code y escribe `/codebeacon` para escanear el directorio actual.

```
/codebeacon                  # escanear directorio actual
/codebeacon /path/to/project # escanear una ruta específica
/codebeacon sync             # re-escanear desde codebeacon.yaml
```

### Servidor MCP

Ejecuta codebeacon como servidor MCP persistente para que cualquier cliente compatible pueda consultar el grafo de conocimiento directamente.

**Paso 1 — escanear el proyecto:**
```bash
codebeacon scan .
```

**Paso 2 — agregar a la configuración del cliente MCP:**

**Claude Code** (`.claude.json` en la raíz del proyecto o `~/.claude.json` global):
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

**Herramientas MCP disponibles tras la conexión:**

| Herramienta | Descripción |
|-------------|-------------|
| `beacon_wiki_index` | Resumen global del proyecto (rutas, servicios, entidades) |
| `beacon_wiki_article` | Leer un artículo wiki por ruta |
| `beacon_query` | Buscar nodos por subcadena de etiqueta |
| `beacon_path` | Ruta de dependencia más corta entre dos nodos |
| `beacon_blast_radius` | Llamadores upstream y nodos afectados downstream |
| `beacon_routes` | Lista de todas las rutas HTTP (filtrable por proyecto) |
| `beacon_services` | Lista de todos los servicios/clases (filtrable por proyecto) |

---

## Opciones de instalación

```bash
pip install codebeacon              # gramáticas de lenguaje incluidas
pip install codebeacon[cluster]     # + detección de comunidades Leiden (graspologic)
pip install --upgrade codebeacon    # actualizar a la última versión con todas las dependencias
```

Los parsers de Java, Kotlin, Python, JavaScript, TypeScript, Go, Ruby, PHP, C#, Rust, Swift, HTML y Svelte se incluyen por defecto.

---

## Referencia CLI

```bash
codebeacon scan .                         # directorio actual
codebeacon scan . --update                # incremental: solo archivos modificados
codebeacon scan . --wiki-only             # saltar extracción, regenerar wiki/obsidian/contexto desde beacon.json existente
codebeacon scan . --semantic              # extracción de referencias de comentarios estructurados (Javadoc/JSDoc/docstring)
codebeacon scan . --list-only             # solo detectar frameworks
codebeacon scan /workspace --deep-dive    # salida por proyecto + workspace combinado
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # patrones tipo gitignore repetibles
                                          # fusionados con .codebeaconignore / .gitignore

codebeacon init [ruta]                    # generar codebeacon.yaml
codebeacon sync                           # ejecutar desde codebeacon.yaml (añade nuevos proyectos del workspace automáticamente)
codebeacon sync --no-rediscover           # no añadir automáticamente nuevos proyectos (modo yaml curado a mano)
codebeacon sync --exclude PATTERN         # mismo flag, misma semántica

# PR / CI: ¿qué rompe realmente este diff?
codebeacon affected --base main           # recorrer aguas arriba los llamadores de los archivos cambiados
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # rutas explícitas — sin git

codebeacon query <término> [--dir .codebeacon] [--limit N]   # buscar nodos por substring de etiqueta
codebeacon path <origen> <destino> [--dir .codebeacon]       # ruta más corta de dependencias

# Soporte multi-desarrollador (git plumbing)
codebeacon hook install [path]            # instala merge driver + hook post-commit incremental
codebeacon merge-driver <base> <cur> <other>  # invocado por git tras `hook install`; union-merge de beacon.json

# Enriquecimiento AI-semántico (el LLM lo ejecuta el agente, codebeacon lleva la contabilidad)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # rehidrata .codebeacon/semantic/original/*.jsonl sobre el
                                          # nuevo beacon.json + poda entradas que apuntan a nodos
                                          # desaparecidos, luego escribe tareas en
                                          # .codebeacon/semantic/pending/chunk_NNN.jsonl
                                          # (--chunk-size por chunk, predet. 10). El task_id incluye
                                          # hash de contenido: si el archivo cambia, se reemite.
codebeacon semantic-apply   [--dir .codebeacon]
                                          # por cada .codebeacon/semantic/results/chunk_NNN.jsonl que
                                          # haya escrito el agente, fusiona las aristas INFERRED
                                          # references en beacon.json y MUEVE el chunk pendiente a
                                          # .codebeacon/semantic/original/chunk_NNN.jsonl (archivo
                                          # durable). Borra los resultados y regenera todo.

codebeacon serve [--dir .codebeacon]      # servidor MCP (stdio)
codebeacon install                        # instalar skill de Claude Code (ámbito usuario: ~/.claude/)
codebeacon install --project [PATH]       # instalar en <PATH>/.claude/ (compartido por el equipo, fijado al repo)
codebeacon upgrade                        # pip upgrade + refrescar ~/.claude/skills/codebeacon/SKILL.md
                                          # (use `--force` si está instalado en modo editable)
```

---

## Enriquecimiento AI-semántico (mediante el skill `/codebeacon`)

El análisis con tree-sitter encuentra lo que está en el AST. **AI-semántico** encuentra lo que vive sólo en los *comentarios* — el `@see UserService` en un Javadoc, el `:class:`OrderRepository`` en una docstring de Python, las referencias contractuales documentadas junto a un handler de ruta. codebeacon ofrece dos capas para esto:

| Capa | Flag | Coste | Qué captura |
|---|---|---|---|
| Análisis de comentarios estructurados | `--semantic` | gratis, local, sin LLM | Javadoc `@see` / `{@link}`, JSDoc `@see` / tipos de `@param`, Python `:class:` / `:func:` / `See Also` |
| **AI-semántico** | automático en el skill `/codebeacon` | usa el modelo actual del agente — **sin API key adicional** | referencias de clase/tipo/servicio que el regex no atrapa (texto libre, menciones indirectas, sólo hints de tipo) |

El CLI por sí mismo **nunca llama a un LLM**. La capa AI-semántica es propiedad intencional del **agente en ejecución** dentro del skill `/codebeacon` de Claude Code — así se respeta el modelo elegido por el usuario (Opus / Sonnet / Haiku / lo que sea) y codebeacon nunca necesita `ANTHROPIC_API_KEY` ni configuración en la nube.

### Cómo funciona

Cuando invocas `/codebeacon` en Claude Code:

1. `scan` / `sync` construye `beacon.json` desde el AST (sin LLM).
2. `codebeacon semantic-prepare` rehidrata el archivo en `.codebeacon/semantic/original/*.jsonl` sobre el grafo nuevo y **poda** las entradas que apuntan a nodos ya desaparecidos. Después escribe los nuevos task chunks en `.codebeacon/semantic/pending/chunk_NNN.jsonl` (cada chunk ≤ `--chunk-size`, predet. 10). La numeración de chunks continúa donde dejó el archivo durable, así nunca colisiona.
3. El skill itera los chunks pendientes **uno por uno**. Para cada `pending/chunk_NNN.jsonl`, el agente (con el modelo de su sesión actual) lee el `excerpt` de cada task y escribe un `semantic/results/chunk_NNN.jsonl` con el mismo nombre.
4. `codebeacon semantic-apply` mezcla los resultados como aristas `INFERRED references` en `beacon.json` y **mueve** cada `pending/chunk_NNN.jsonl` terminado a **`semantic/original/chunk_NNN.jsonl`** (con las aristas aplicadas para auditoría). Los archivos de resultados se eliminan; wiki + obsidian + mapa de contexto se regeneran.
5. En la siguiente ejecución: `semantic-prepare` lee cada chunk bajo `original/`, aplica sus aristas al grafo recién construido (las inferencias históricas no se pierden) y omite cualquier task cuyo `task_id` ya esté archivado. `task_id` = `SHA1(file_path | node_id | excerpt_hash[:8])`: si el contenido del archivo cambia, recibe un id nuevo y se reanaliza.

Enriquecimiento incremental e idempotente: el agente nunca reanaliza la misma combinación (archivo, contenido) dos veces, la señal AI acumulada sobrevive a cada re-escaneo y los chunks mantienen pequeño el conjunto de trabajo del agente.

### Uso directo del CLI

Si no usas el skill (p. ej. en CI), puedes ejecutar las mismas dos órdenes manualmente y proporcionar tus propios `results/chunk_NNN.jsonl`:

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# Existen .codebeacon/semantic/pending/chunk_001.jsonl ...
# Para cada chunk pendiente, escribe un results/chunk_NNN.jsonl con el mismo
# nombre. Cada línea:
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### Desactivar

Pasa `--no-semantic` (o `--wiki-only`, o `--list-only`) al invocar el skill para saltarte por completo el paso AI. La capa de comentarios estructurados sigue funcionando cuando pasas `--semantic` a `scan` / `sync`.

---

## Comparativa

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| Análisis rutas / controladores | ✅ | ❌ | ✅ |
| Grafo servicios / DI | parcial | ✅ | ✅ |
| Resolución Interface → Impl | ❌ | ❌ | ✅ |
| Extracción entidades / ORM | ✅ | ❌ | ✅ |
| Análisis componentes frontend | ✅ | ❌ | ✅ |
| Detección de comunidades | ❌ | ✅ | ✅ |
| Exportación Obsidian Vault | ❌ | ✅ | ✅ |
| Servidor MCP | ✅ | ❌ | ✅ |
| Mapa de contexto (CLAUDE.md) | ✅ | ✅ | ✅ |
| Workspace multi-proyecto | parcial | ❌ | ✅ |
| Basado en Python | ❌ | ✅ | ✅ |

---

## Benchmarks

| Código fuente | Stack | Archivos | Nodos | Aristas | Comunidades | Tiempo de escaneo |
|--------------|-------|----------|-------|---------|-------------|-------------------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3 proyectos) | 444 | 382 | 553 | 175 | ~12s |

---

## Privacidad y seguridad

Todo el procesamiento AST es local. Al ejecutar codebeacon directamente, su código fuente nunca sale de su máquina. Sin telemetría ni llamadas de red durante el uso normal.

- El propio CLI **nunca llama a un proveedor LLM** — el paquete codebeacon no incluye cliente API, ni manejo de claves, ni nombre de modelo.
- `--semantic` activa **solo el análisis de comentarios estructurados** (Javadoc `@see` / `{@link}`, JSDoc `@see` / tipos de `@param`, Python `:class:` / `:func:` / `See Also`). 100 % local.
- **AI-semántico** (la capa LLM más profunda) lo dispara el skill `/codebeacon` de Claude Code. El agente lee `semantic-tasks.jsonl`, ejecuta el análisis con el **modelo de su sesión actual** y escribe `semantic-results.jsonl`. El CLI Python solo prepara el lote de tareas y fusiona los resultados; ni siquiera sabe qué modelo se utilizó. Pase `--no-semantic` al skill para omitir por completo el paso LLM.

---

## Contribuir

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

El punto de entrada más sencillo para agregar soporte de nuevos frameworks es escribir un archivo de consulta tree-sitter en `codebeacon/extract/queries/`. Consulte [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md).

---

## Licencia

MIT — ver [LICENSE](LICENSE).

---

## Agradecimientos

Construido sobre [tree-sitter](https://tree-sitter.github.io/tree-sitter/), [NetworkX](https://networkx.org/) y [graspologic](https://microsoft.github.io/graspologic/). Inspirado en los enfoques complementarios de [codesight](https://github.com/Houseofmvps/codesight) y [graphify](https://github.com/safishamsi/graphify).
