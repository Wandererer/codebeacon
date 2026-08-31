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

## Novedades en 0.7.1

La mayor release de auditoría hasta la fecha: un barrido dual de paridad con upstream (graphify v0.9.13–v0.9.53 / issues #1777–#3235, más codesight #50–#55) verificado contra codebeacon con reproducción obligatoria — **~70 defectos confirmados corregidos** por diez fixers en paralelo, cada corrección sometida a mutation testing y después revisada de forma adversarial por el lead con ejecuciones de integración sobre la CLI real. Suite: 885 → 1.481 tests.

- **El grafo JS/TS prácticamente se ha duplicado** — las funciones flecha exportadas en minúscula, los `const` y los miembros de objetos literales (`export const useAuthStore = …`, `authUtils.clear`) por fin se convierten en nodos: en una app Next.js real de 865 archivos, los nodos de componente pasaron de **960 → 2.237** y los archivos que no aportaban nada bajaron de 406 a 108. Los imports ahora se resuelven primero por **ruta** (especificadores relativos, alias de `tsconfig`/`jsconfig` con cadenas `extends` y `${configDir}`, sufijos de paquete) antes de recurrir a las etiquetas — así `from codebeacon.graph.build import …` ya no puede enlazarse a un símbolo `build` sin relación, y la lista "High-Impact Files" de CLAUDE.md refleja la realidad. También se capturan la herencia `class X extends Y` de JS puro y las aristas de `await import()` dinámico.
- **Los prefijos de ruta se componen como en los frameworks reales** — verificado contra servidores FastAPI/Express/Flask en ejecución: `include_router(prefix=)` se compone con el prefijo propio del router, los includes en forma de atributo (`app.include_router(pkg.router, …)`, `@pkg.router.get`) ya no se esfuman, los montajes en cascada dentro del mismo archivo se despliegan, un router montado dos veces produce las dos rutas, y el `register_blueprint(url_prefix=)` de Flask *sobrescribe* correctamente. Límite conocido: una cadena de montajes que cruza **archivos** sigue sin componerse.
- **La resolución de DI interfaz→implementación ahora funciona de verdad** — un límite de serialización en el pipeline de extracción venía descartando en silencio `implements`/`extends` desde 0.6.x, así que la funcionalidad entera estaba muerta de extremo a extremo mientras la wiki se veía bien. Corregido, con la caché invalidada y con tests de frontera que atraviesan el pipeline real. El binding de DI también está ahora sujeto a evidencia: se acabaron las fabricaciones entre lenguajes o entre proyectos (un service de Spring ya no puede "inyectar" un componente de React), los casos ambiguos con varias implementaciones solo se enlazan mediante la convención de nombres `*Impl` con una confianza `AMBIGUOUS` explícita, y una arista duplicada registra su segunda relación en un nuevo atributo `also` en lugar de sobrescribir.
- **La identidad de los nodos es determinista y tiene en cuenta la extensión** — `Button.tsx` y `Button.jsx` son dos nodos (antes uno absorbía al otro en silencio — el 6,3 % de las declaraciones en el propio repo de codebeacon); los IDs de nodo ya no dependen del orden de finalización de los hilos ni del directorio de checkout, así que los nombres de archivo de wiki/obsidian dejan de bailar entre ejecuciones. Las etiquetas que colisionan reciben el sufijo de ruta distintivo más corto. (Los IDs de los nodos previamente colapsados cambiarán una vez al actualizar.)
- **La capa de ignore se ajusta mucho más a git** — los `.gitignore` anidados se aplican a su propio subárbol (el `app/.gitignore` de un monorepo ya no queda ignorado, algo que antes arrastraba decenas de miles de archivos de build al scan), se respeta `.git/info/exclude`, los worktrees enlazados se detectan estructuralmente en vez de duplicar el corpus, y los archivos de ignore con BOM / UTF-16 / codificación NFD se decodifican en lugar de perder reglas en silencio. Los nombres de directorio ambiguos (`env/`, `build/`, `public/`, `coverage/`, …) solo se podan con evidencia que lo corrobore — un testbench UVM `env/` o un paquete de Python llamado `coverage/` se queda en el grafo. El matching es ~19× más rápido, y un nuevo diagnóstico `ignored.json` registra *por qué* se omitió cada subárbol.
- **La guarda de shrink ahora protege los caminos que importan** — antes se desarmaba con la mera presencia de `--update`, es decir, justo en los caminos desatendidos (watch, hooks de git, CI); un error de permisos podía reducir a la mitad tu grafo commiteado sin decir nada. Ahora atribuye cada nodo eliminado a su archivo fuente (borrado / recién ignorado / **sin explicación** — solo el último rechaza, con un flag `--force` de verdad), permanece armada en todas partes, trata un subárbol ilegible como "desconocido, no eximir", y avisa cuando las aristas se desploman aunque los nodos se hayan mantenido.
- **`scan → knowledge → scan` ya no se atasca** — el flujo documentado de 0.7.0 o salía con código 1 ("refusing to shrink") o descartaba en silencio tu capa de notas. La guarda ahora es consciente del tier y la capa de knowledge se **reaplica automáticamente después de cada scan**; borrar una nota poda exactamente esa nota. Los `[[wikilinks]]` que escribes por fin crean aristas (se parseaban y luego se tiraban — 100 % de pérdida), las notas llevan `node_kind`/frontmatter, y los archivos generados (CLAUDE.md, KNOWLEDGE.md) ya no se reingieren como notas.
- **Un índice commiteado se mantiene limpio** — un reescaneo sin cambios ahora reescribe **cero** archivos commiteados (antes: todos ellos, un churn de ~31k archivos aguas arriba): `built_at_ts` se deriva del commit, los exports solo escriben cuando cambia el contenido, y la caché AST local de la máquina se auto-ignora en git. Los exports HTML (`beacon.html`, `callflow.html`) incluyen su JS **offline por defecto** (d3 + mermaid vendorizados bajo `_assets/`) — en línea con la postura air-gapped; pon `output.html_assets: cdn` para conservar el comportamiento anterior. Las rutas absolutas de la máquina de build ya no se filtran a ningún artefacto.
- **Respuestas MCP en las que puedes confiar programáticamente** — los fallos de herramienta devuelven `isError: true` con el mensaje accionable (en lugar de prosa de error con forma de éxito, o un error de protocolo que el cliente se traga); la resolución de nombres prefiere la coincidencia exacta antes que las subcadenas, así que `blast_radius("User")` ya no responde sobre `UserServiceImpl`; cada herramienta respeta un `token_budget` (2.000 tokens por defecto) y anuncia el truncamiento respecto al total real.
- **Barrido de robustez y seguridad** — el XML de `.csproj` se parsea con un filtro DOCTYPE/ENTITY; el texto que ve el modelo (salida MCP, CLAUDE.md) neutraliza los tokens de control de plantillas de chat por su forma (`<|…|>`, `[INST]`); `hook install` funciona en worktrees de git y nunca deja un repo a medio configurar; `install`/`upgrade` hacen copia de seguridad de un SKILL.md editado a mano en vez de aplastarlo, y un marcador sin cerrar ya no puede borrar el contenido de usuario que hay debajo; un CLAUDE.md en cp949/latin-1 no tumba el scan; `codebeacon … | head` termina limpiamente; el modo watch ya no se vuelve a disparar a sí mismo con los eventos inotify de Linux; el clustering de Leiden usa una semilla fija, así que las comunidades dejan de derivar un 12 % por reescaneo.

Notas de actualización: los IDs de nodo de las declaraciones previamente colapsadas cambian una vez; los `task_id` semánticos se invalidan una vez (las tareas ahora hashean el archivo entero, corrigiendo "las ediciones más allá del carácter 4.000 nunca se reanalizaban"); la caché AST se invalida una vez (sello de esquema); nuevo atributo de arista `also`, nuevo valor de confianza `AMBIGUOUS`, nuevo marcador `verification` en los externos acuñados por semantic. Si tu repositorio ya tenía `.codebeacon/cache/` en un commit, ejecuta una vez `git rm --cached -r .codebeacon/cache` — el nuevo `.gitignore` auto-ignorante no puede dejar de rastrear archivos ya rastreados.

---

## Novedades en 0.7.0

Una release de capacidades más que un barrido de bugs: codebeacon estrena un file-watcher en vivo, enlaza tus notas de diseño en el grafo de código, incorpora dos nuevos front-ends (un lanzador npm para el servidor MCP y una GitHub Action) y ajusta lo que indexa por defecto. Cada funcionalidad sigue siendo local-first — el scan central sigue sin necesitar red, ni nube, ni modelo.

- **`codebeacon watch` mantiene el índice en vivo** — un file-watcher con debounce (`codebeacon watch [path] [--debounce 2.0] [--once] [--exclude PATTERN]`) resincroniza el grafo cada vez que cambian los archivos fuente vigilados. Una ráfaga de ediciones — un `git checkout` de 500 archivos, un cambio de rama — se fusiona en una única resincronización, y el watcher reutiliza exactamente las mismas reglas de ignore del scanner, de modo que escribir el índice nunca lo despierta en un bucle sobre su propia salida `.codebeacon/`. Necesita el nuevo extra opcional: `pip install 'codebeacon[watch]'` (watchdog).
- **Las notas de diseño se enlazan en el grafo de código** — `codebeacon knowledge` ahora escribe sus notas (ADRs, notas de reunión, retros, specs) *dentro* de `beacon.json` cuando ya existe un índice: una referencia explícita a una ruta de archivo se convierte en una arista `references` de confianza, y una mención de símbolo distintiva (`PaymentService`, nunca un `User` pelado) se convierte en una arista `mentions` `AMBIGUOUS` — de modo que un agente que lee el grafo aprende *por qué* un service tiene la forma que tiene. Como `codebeacon scan` reconstruye el grafo de código solo a partir del fuente y descarta esta capa, **vuelve a ejecutar `codebeacon knowledge` después de un scan** para restaurar los enlaces.
- **Herramienta MCP `beacon_knowledge`** — una nueva herramienta busca notas por palabra clave y/o lista las notas enlazadas a un nodo de código dado, exponiendo el rastro de decisiones detrás del código directamente por MCP.
- **Lanzador npm para el servidor MCP** — `@codebeacon/mcp` permite que los clientes MCP arranquen el servidor de la forma npx-first que esperan (`"command": "npx", "args": ["-y", "@codebeacon/mcp"]`). El shim de Node sin dependencias resuelve un codebeacon funcional vía PATH → `uvx` → `pipx run` → `python3 -m codebeacon` y reenvía stdio sin tocarlo. Ver [`npm/README.md`](npm/README.md). (Se distribuye con 0.7.0; aún no publicado en npm.)
- **GitHub Action para contexto de PR** — una action compuesta comenta en cada pull request con la porción afectada de tu grafo de conocimiento commiteado: los artículos de wiki que toca el cambio, el radio de impacto aguas arriba, y cualquier archivo hub de alto impacto que edite — una comprobación de deriva de arquitectura para la revisión en la era de la IA. Requiere un índice `.codebeacon/` commiteado, `fetch-depth: 0` y `permissions: pull-requests: write`. Ver [`action/README.md`](action/README.md) y [`action/examples/pr-context.yml`](action/examples/pr-context.yml).
- **El CLAUDE.md de workspace se mantiene por debajo de ~200 líneas** — en un workspace multi-proyecto, el `CLAUDE.md` raíz ahora conserva solo la visión general compartida y mueve el detalle por proyecto a archivos `.claude/rules/codebeacon-<project>.md` con alcance acotado, cuyo frontmatter `paths:` los carga solo cuando se tocan los archivos de ese proyecto (siguiendo la propia guía de Anthropic para archivos de contexto). La salida de un solo proyecto no cambia; pon `output.context_map.rules_split: false` para el antiguo archivo monolítico. Las filas de proyecto duplicadas también se colapsan.
- **Los fixtures de test se ignoran por defecto** — `tests/fixtures/`, `test/fixtures/` y `__fixtures__/` a cualquier profundidad ahora se ignoran por defecto, de modo que las entradas de test sintéticas de un proyecto dejan de inyectar rutas y services falsos en el grafo (el propio self-scan de codebeacon había reportado un `main.py` de fixtures como cinco "rutas"). Es la regla de menor precedencia, así que una línea `!tests/fixtures/` en `.codebeaconignore` las vuelve a incluir, y apuntar un scan *a* un directorio de fixtures sigue recogiéndolo.
- **La extracción de rutas de Warp ahora es real** — las rutas de combinadores de filtros de Warp se extraen de verdad: los segmentos `warp::path!(...)` y `warp::path("x")`, los combinadores de método (`warp::get()` / `post()` / …) y los handlers `.map` / `.and_then` se correlacionan por su binding contenedor en rutas completas. Límites honestos (detallados en la cabecera de la query): los filtros unidos por `.or(...)` dentro de un mismo binding colapsan en una única ruta concatenada, y los segmentos de llamada a filtro `warp::path::param()` y los handlers de closure quedan sin resolver.

---

## Novedades en 0.6.9

La release de auditoría más grande hasta la fecha: un doble barrido de paridad con el upstream (la primera auditoría completa del tracker de codesight, más graphify v0.9.4–v0.9.12 / issues hasta el #1776) combinado con una caza de bugs multiagente independiente sobre el propio codebeacon. Cada candidato se reprodujo antes de corregirlo, cada corrección se probó con mutation testing, y una segunda revisión adversarial atacó luego las propias correcciones — atrapando 18 agujeros más antes de la publicación. **48 bugs reales corregidos.**

- **Tu CLAUDE.md ahora está a salvo** — en un CLAUDE.md escrito a mano (p. ej. desde `/init`), el paso de fusión podía confundir las secciones `## Architecture` / `## Common Commands` propias del usuario con salida de codebeacon y borrarlas. El borrado ahora solo se ejecuta en archivos que se identifican inequívocamente como generados por codebeacon, y está anclado al bloque generado — tus secciones sobreviven. `codebeacon.yaml` también se escribe ahora de forma atómica (y a través de symlinks, preservando los modos de archivo), así que una escritura interrumpida no puede destruir una configuración curada a mano.
- **Los archivos ya no desaparecen del índice en silencio** — las extensiones en mayúsculas (`App.PY`, `Page.TSX`) se omitían; los módulos de código con nombre de credencial (`api_key_manager.go`, `access_token_service.py`) los descartaba la heurística de archivos secretos; un solo byte no UTF-8 en un `.gitignore` hacía caer todo el scan; y un repo con checkout bajo una carpeta llamada `build/` o `dist/` veía **borrado su grafo entero** porque el filtro de artefactos matcheaba directorios ancestros. Todo corregido; los symlinks omitidos reciben ahora un único aviso agrupado en vez de silencio.
- **El manejo de `.gitignore` ahora coincide exactamente con git** — la semántica de negación (`dir/` + `!dir/keep.txt`) se somete a differential testing contra `git check-ignore` en cada forma de regla; un archivo bajo un directorio excluido ya no puede volver a incluirse, igual que en git. El idiomático de rescate estándar `dir/*` + `!dir/keep` funciona como antes.
- **Los proyectos con el mismo nombre coexisten** — dos (o tres) subproyectos todos llamados `frontend` solían colapsar en uno: los IDs de nodo en colisión descartaban rutas en silencio, y sus carpetas de wiki/obsidian se sobrescribían entre sí. Los nombres duplicados ahora se desambiguan automáticamente con un prefijo del directorio padre.
- **La extracción de rutas recibió una revisión de corrección** — los prefijos de montaje `app.use('/api', router)` de Express se aplican y el encadenado `router.route(x).get().post()` produce todos los verbos; los prefijos de `register_blueprint` de Flask / `include_router` de FastAPI ya no dependen de dónde aparecen en el archivo; el `@RequestMapping(method = RequestMethod.X)` de Spring registra el verbo real en vez de `ANY`; los segmentos catch-all de Next.js (`[...slug]`) ya no se corrompen y las rutas paralelas `@slot` se eliminan de las URLs; el canónico `class X extends Model` de Laravel por fin produce una entidad (antes solo matcheaban las bases totalmente cualificadas — y `ViewModel` ya no se cuela).
- **Aristas fantasma del grafo eliminadas** — un import en minúsculas como `CONFIG` ya no se pliega por mayúsculas/minúsculas sobre una clase `Config` no relacionada (el falso patrón god-node), los imports nunca enlazan cruzando una frontera de lenguaje (`import time` → `time.ts`), los bindings de DI prefieren el proyecto que registra en vez de la primera clase homónima en cualquier parte, y un servicio + entidad homónimos en un mismo directorio ya no colapsan en un único nodo.
- **Las exportaciones son a prueba de Windows y a prueba de cuelgues** — los nombres de nota de obsidian eliminan el conjunto completo de caracteres ilegales en Windows (las rutas `<string:id>` de Flask rompían la exportación en Windows) y protegen contra nombres de dispositivo reservados; las etiquetas `None` ya no hacen caer los exportadores de wiki, del HTML de call-flow ni de obsidian; los git hooks se escriben con finales de línea LF para que se ejecuten en Windows; y los nombres de proyecto largos ya no pueden reventar los límites del sistema de archivos a mitad de la exportación.
- **Una entrada defectuosa ya no puede matar procesos de larga duración** — el servidor MCP sobrevive a mensajes JSON-RPC malformados en vez de morir; un `beacon.json` o una caché de AST corruptos (incluyendo UTF-8 inválido y colecciones nulas/malformadas) se respaldan y se reportan en vez de hacer caer `affected`, `serve` o el driver de fusión.
- **Salida reproducible byte a byte** — el orden de los nodos ya no sigue el orden de finalización de los hilos y las anotaciones de entidad compartida se ordenan, así que escanear dos veces un árbol sin cambios produce `beacon.json`, wiki y CLAUDE.md byte-idénticos. El backend de clustering Leiden (silenciosamente roto por un cambio de la API de graspologic — *nunca* llegó a ejecutarse) vuelve a estar en servicio.
- **La configuración que escribes es la configuración que se ejecuta** — los ajustes documentados de `codebeacon.yaml` (`wave.*`, `output.wiki/obsidian`, `context_map.targets`, `semantic.enabled`) se parseaban y luego se ignoraban; ahora sí gobiernan el pipeline, `--list-only` se respeta dentro de workspaces, y `codebeacon upgrade` da el comando correcto para instalaciones con uv venv. Consistencia extra: la tabla de Projects, la columna de Notes y la sección de Architecture de CLAUDE.md ahora coinciden en un único recuento de "Services", igual que el wiki.

---

## Novedades en 0.6.8

Una auditoría de paridad con graphify del upstream v0.8.41–v0.9.3 (issues reportados hasta el #1568). Cada candidato se reprodujo contra codebeacon antes de corregirlo y se volvió a comprobar con una ronda de revisión adversarial; se confirmaron **7 bugs reales**, encabezados por una trampa de pérdida de datos y una fuga de privacidad.

- **`--obsidian-dir` ya no puede borrar tus notas** — apuntando a un vault de Obsidian existente, la exportación barría *todos* los `.md` debajo antes de regenerar, pudiendo vaciar un vault real. codebeacon ahora rechaza cualquier directorio que no posea (solo se adopta un directorio genuinamente vacío, o uno que lleve su marcador `.codebeacon-vault.json`) y omite la exportación con un mensaje claro en vez de borrar.
- **`.gitignore` ya no queda deshabilitado en silencio por `.codebeaconignore`** — añadir un `.codebeaconignore` solía *reemplazar* el `.gitignore` del repo, así que un archivo excluido solo por `.gitignore` (un `prod-dump.sql`, `customer-data.*` de nombre neutro) podía terminar indexado en los artefactos `.codebeacon/` que se commitean. Ahora ambos se fusionan (`.codebeaconignore` gana en conflicto); añadirlo solo puede excluir *más*.
- **Sin rutas absolutas de máquina en los artefactos commiteados** — los valores `source_file` de edges/links (el grueso de `beacon.json`) y las líneas `Source:` en las notas de wiki/obsidian conservaban rutas absolutas `/Users/tu/...`, así que el índice commiteado no era portable y filtraba rutas locales. Ahora todas son relativas al proyecto (edges incluidos, y también los archivos `shares_db_entity` entre proyectos).
- **Símbolos con el mismo nombre en directorios distintos ya no se sobrescriben las notas** — los nombres de archivo de wiki/obsidian se derivaban de la etiqueta sin normalizar mayúsculas/minúsculas, así que en macOS/Windows `UserService` y `userService` colisionaban y una nota se perdía en silencio. Ahora los nombres de archivo llevan sal anti-colisión y normalización de mayúsculas; las etiquetas solo de puntuación (`@`) recurren a `unnamed` en vez de un `@.md` roto.
- **Un `beacon.json` corrupto ya no provoca un cuelgue** — `codebeacon affected`, el servidor MCP y las ejecuciones `--wiki-only` ahora respaldan un grafo corrupto/truncado y muestran un mensaje claro de "vuelve a ejecutar scan" en vez de un traceback en crudo.
- **Se capturan más componentes de React** — `react.scm` pasaba por alto los componentes de expresión de función (`const X = function() {…}`), los HOC importados sin calificar (`const X = forwardRef(…)` sin el prefijo `React.`) y los componentes `function X()` no exportados. Los tres se extraen ahora.
- **Los enlaces del wiki nunca quedan rotos** — un enlace a una página que nunca se escribió se degrada a texto plano, y un enlace a un artículo en un bucket hermano (un servicio → su entidad) se repara a la ruta relativa correcta en vez de apuntar a un archivo inexistente.

---

## Novedades en 0.6.7

Seguimiento de la auditoría de paridad con graphify de 0.6.6: la deriva de gramática ahora falla de forma ruidosa en lugar de silenciosa, y las negaciones en el archivo de ignore ya no ralentizan los escaneos.

- **La deriva de gramática es un fallo ruidoso, no un grafo vacío silencioso** — cuando una query de tree-sitter no compila contra una gramática que *debería* soportar (p. ej. un nodo renombrado en una futura actualización de gramática), `run_query` ahora lanza una excepción y el archivo se registra como `ExtractionFailure` en lugar de extraer silenciosamente nada. Junto con los topes superiores de 0.6.6 y el test «cada query compila contra cada gramática que declara soportar», la deriva se detecta ahora de tres formas independientes.
- **Una sola negación `!` en `.codebeaconignore` ya no fuerza un recorrido completo del árbol** — una regla de negación en cualquier sitio desactivaba el pruning de directorios *en todas partes*, así que el escáner descendía a cada directorio excluido (`node_modules`, `build`, …) aunque la negación no pudiera rescatar nada allí. Ahora un directorio ignorado solo se conserva si una negación realmente podría reincluir un archivo *debajo de él*; las reglas `!` no relacionadas no cuestan nada.
- **Los globs de ignore se compilan una sola vez** — el matcher estilo gitignore memoiza la regex compilada por patrón en lugar de reconstruirla en cada comprobación de ruta (descubrimiento más rápido en árboles profundos con archivos de ignore grandes). La semántica no cambia.

---

## Novedades en 0.6.6

Una auditoría de paridad con graphify de upstream v0.8.37–v0.8.40 (e issues reportados hasta #1362): un barrido de «verificar y luego refutar de forma adversaria» sobre 32 candidatos confirmó **6 bugs reales**. Lo principal: tres extractores de framework producían silenciosamente *nada*.

- **Las apps de Express/Koa/Fastify en TypeScript ahora extraen rutas** — `express.scm` fijaba el nodo de nombre de clase de JavaScript, que es un «Impossible pattern» bajo la gramática de TypeScript, así que toda la query no compilaba y el error se tragaba: **las apps de Express en TS extraían 0 rutas**. (Las apps de JavaScript funcionaban, y la única fixture de test era `.js`, así que pasó desapercibido.) La misma causa afectaba a `vue.scm` (SFC de Vue con `<script>` plano → 0 componentes). Ambos usan ahora un comodín de nodo neutral a la gramática que compila en JS y TS.
- **Los archivos Kotlin en proyectos Spring ya no dan error** — `spring_boot.scm` es una query de gramática Java pero se permitía ejecutarla contra Kotlin, emitiendo `Invalid node type: marker_annotation` y descartando cada archivo `.kt`. Kotlin ahora se bloquea limpiamente (Kotlin Spring Boot necesitaría su propia query).
- **Las gramáticas de tree-sitter están fijadas con topes superiores** — `pyproject.toml` fijaba las gramáticas sin límite superior (`>=0.23`), así que un futuro release de gramática que renombrara nodos del AST podría romper las queries de nuevo en silencio. Cada gramática tiene ahora un tope de rango compatible, y un nuevo test verifica que cada `.scm` distribuida compila contra cada gramática que declara soportar.
- **La caché de extracción está versionada** — tras actualizar codebeacon, un `--update` incremental podía reutilizar resultados extraídos por la versión *antigua* para archivos sin cambios (un hash de contenido no detecta que el extractor cambió). La caché ahora lleva la versión de codebeacon y se descarta si no coincide.
- **Los nombres acentuados / no ASCII se resuelven en macOS** — `codebeacon query` / `path` / MCP y `affected` ahora normalizan etiquetas y rutas a Unicode NFC, de modo que un nombre copiado de un nombre de archivo de macOS (guardado como NFD) coincide con la etiqueta NFC del grafo (p. ej. `Auditoría`).
- Además: una `cache.json` corrupta se respalda y se reconstruye en lugar de resetearse y sobrescribirse en silencio.

---

## Novedades en 0.6.5

`codebeacon upgrade` ahora funciona en cualquier entorno — antes asumía una instalación pip normal y fallaba silenciosamente en máquinas donde no lo era.

- **Detección del gestor de instalación** — el comando upgrade detecta cómo se instaló codebeacon y ejecuta la herramienta correspondiente: `pip install --upgrade` para instalaciones pip, `pipx upgrade codebeacon` para pipx, `uv tool upgrade codebeacon` para uv. Los venvs de pipx/uv tool vienen *sin* módulo `pip`, así que la antigua llamada incondicional a `python -m pip` moría antes de hacer nada.
- **Verificación del upgrade** — tras actualizar, un intérprete nuevo relee la versión instalada y reporta `0.6.4 -> 0.6.5`. Si la versión no cambió pero PyPI tiene una release más nueva, recibes una advertencia de que el `codebeacon` en tu PATH puede pertenecer a otro entorno de Python — en lugar de un falso "Upgrade complete".
- **Fallos accionables** — un entorno sin pip imprime los comandos exactos a ejecutar; un rechazo PEP 668 `externally-managed-environment` explica la solución (pipx o un virtualenv) en vez de volcar un error pip crudo. El comando también muestra de entrada la versión actual frente a la última en PyPI.

---

## Novedades en 0.6.4

Limpieza del deep-dive — las salidas aterrizan donde las buscas, más dos bugs de pérdida silenciosa de datos encontrados al verificarlo en un workspace de 47 proyectos.

- **El deep-dive escribe exactamente en dos niveles** — cada *raíz de repo* (un directorio con su propio `.git` o `codebeacon.yaml`) y la *raíz del escaneo*. Las carpetas de framework de un monorepo (`mono/landing`, `mono/server`) ya no generan cada una su propio `.codebeacon/` + CLAUDE.md; su grafo combinado vive en `mono/.codebeacon/`, y la raíz del escaneo lleva el grafo completo del workspace, así cualquier proyecto puede encontrarse desde un solo lugar. Ejecutar deep-dive *dentro* de un monorepo ahora produce una única salida raíz en lugar de una por subcarpeta.
- **Las claves de caché tienen namespace por framework** — un grupo de repos comparte una caché, y un proyecto padre que recorría primero los archivos de un proyecto anidado (`desktop/` como sveltekit sobre `desktop/src-tauri`) envenenaba la caché con resultados vacíos que el proyecto anidado (tauri) luego reutilizaba, perdiendo en silencio todas sus rutas y entidades.
- **Corregida la condición de carrera al cargar gramáticas** — dos workers de extracción en paralelo que tocaban una gramática de tree-sitter sin cachear construían cada uno su propia instancia de `Language`; los archivos del hilo perdedor fallaban entonces una comprobación de identidad y extraían **nada** — sin advertencia, sin registro de fallo, solo un par de archivos a los que aleatoriamente les faltaban todas sus rutas en escaneos grandes. La primera carga ahora está bloqueada a una única instancia compartida (verificada estable a lo largo de 20 escaneos completos consecutivos).

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
