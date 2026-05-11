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
| C# | ASP.NET Core |
| Swift | Vapor |

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
  enabled: false               # sobrescribir con --semantic

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
codebeacon scan . --semantic              # extracción semántica con LLM
codebeacon scan . --list-only             # solo detectar frameworks
codebeacon scan /workspace --deep-dive    # salida por proyecto + workspace combinado

codebeacon init [ruta]                    # generar codebeacon.yaml
codebeacon sync                           # ejecutar desde codebeacon.yaml

codebeacon query <término> [--dir .codebeacon] [--limit N]   # buscar nodos por substring de etiqueta
codebeacon path <origen> <destino> [--dir .codebeacon]       # ruta más corta de dependencias

# Soporte multi-desarrollador (git plumbing)
codebeacon hook install [path]            # instala merge driver + hook post-commit incremental
codebeacon merge-driver <base> <cur> <other>  # invocado por git tras `hook install`; union-merge de beacon.json

codebeacon serve [--dir .codebeacon]      # servidor MCP (stdio)
codebeacon install                        # instalar skill de Claude Code
```

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

Todo el procesamiento es local. El código fuente nunca sale de su máquina. Sin telemetría ni llamadas de red durante el uso normal.

- La bandera `--semantic` (deshabilitada por defecto) activa dos modos de extracción:
  1. **Análisis de comentarios estructurados** (sin LLM) — infiere referencias cruzadas de Javadoc (`@see`, `{@link}`), docstrings de Python (`:class:`, `:func:`) y JSDoc (`@see`, tipos de `@param`)
  2. **Inferencia LLM** (opcional) — si `ANTHROPIC_API_KEY` está configurado, envía fragmentos de código a la API de Claude para inferencia de relaciones más profunda; úselo solo si lo habilita explícitamente

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
