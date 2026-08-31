; ── Express / Koa / Fastify (JavaScript/TypeScript) ──────────────────────────
; Grammar: tree-sitter-javascript / tree-sitter-typescript
;
; Captures:
;   @route.method     - "get", "post", "put", "delete", "patch", "all"
;   @route.path       - path string literal
;   @route.object     - router/app object name (for prefix tracking)
;   @route.use_prefix - path passed to app.use() for prefix mounting
;   @service.name     - exported class name
;   @import.path      - import/require path

; ── app.METHOD("/path", handler) ─────────────────────────────────────────────

(expression_statement
  (call_expression
    function: (member_expression
      object: (identifier) @route.object
      property: (property_identifier) @route.method
      (#match? @route.method "^(get|post|put|patch|delete|del|options|head|all|use)$")
    )
    arguments: (arguments
      .
      (string) @route.path
    )
  )
) @route.call

; ── router.route("/path").get(handler).post(handler)... ──────────────────────
; A verb chain is left-nested: ((router.route(p)).get(h)).post(h). Anchoring on
; identifier.route(p) matched ONLY the innermost .get(...) node and dropped every
; later verb. Instead capture the .route(p) anchor once, then capture EVERY
; chained verb call (receiver is itself a call_expression); routes.py correlates
; each verb to the anchor whose byte range it encloses.

(call_expression
  function: (member_expression
    object: (identifier) @route.chain_object
    property: (property_identifier) @_route_kw
    (#eq? @_route_kw "route")
  )
  arguments: (arguments
    .
    (string) @route.chain_path
  )
) @route.chain_anchor

(call_expression
  function: (member_expression
    object: (call_expression)
    property: (property_identifier) @route.chain_method
    (#match? @route.chain_method "^(get|post|put|patch|delete|options|head|all)$")
  )
) @route.chain_verb

; ── app.use("/prefix", router) — prefix mounting ─────────────────────────────
; The mounting object is captured too: routers mount into routers
; (`mid.use("/x", inner); app.use("/root", mid)`), so routes.py resolves the
; chain transitively instead of treating every mount as rooted at the app.

(expression_statement
  (call_expression
    function: (member_expression
      object: (identifier) @route.mount_parent
      property: (property_identifier) @_use
      (#eq? @_use "use")
    )
    arguments: (arguments
      .
      (string) @route.use_prefix
      .
      (identifier) @route.mount_router
    )
  )
) @route.use_mount

; ── const router = express.Router() / Router() ───────────────────────────────

(variable_declarator
  name: (identifier) @route.router_name
  value: (call_expression
    function: [
      (identifier) @_r (#eq? @_r "Router")
      (member_expression property: (property_identifier) @_r (#eq? @_r "Router"))
    ]
  )
) @route.router_decl

; ── Fastify: fastify.register(plugin, { prefix: "/api" }) ────────────────────

(call_expression
  function: (member_expression
    object: (identifier) @_app
    property: (property_identifier) @_reg
    (#eq? @_reg "register")
  )
  arguments: (arguments
    _
    (object
      (pair
        key: (property_identifier) @_k
        (#eq? @_k "prefix")
        value: (string) @route.use_prefix
      )
    )
  )
) @route.fastify_register

; ── Exported class (service) ──────────────────────────────────────────────────
; The class-name node differs by grammar (JS: identifier, TS: type_identifier).
; Hardcoding (identifier) made this query an "Impossible pattern" under the
; TypeScript/TSX grammars (allowed by QUERY_GRAMMAR_ALLOWLIST), so run_query
; silently returned [] and TS Express/Koa/Fastify apps yielded 0 routes.
; The (_) wildcard compiles and captures the name under both grammars.

(export_statement
  declaration: (class_declaration
    name: (_) @service.name
  )
) @service.export_class

(class_declaration
  name: (_) @service.name
) @service.class

; ── Class heritage (extends / implements) ─────────────────────────────────────
; Only the NestJS and Angular queries captured heritage, so a plain JS/TS class
; carried extends=[] and the interface→implementation DI path had no producer
; for the express/node/react family.
;
; The heritage CONTAINER is captured, not its parts, because the two grammars
; disagree on both halves and this query is allowlisted for all three:
;   - the class name is (identifier) in JS but (type_identifier) in TS/TSX, so
;     naming either one makes the pattern an "Impossible pattern" under the
;     other and run_query raises GrammarQueryError for every file of it;
;   - TS wraps heritage in extends_clause/implements_clause, JS puts the
;     expression directly under class_heritage and has no extends_clause node
;     at all.
; The (_) wildcard plus a container capture compiles identically under
; javascript, typescript and tsx (verified against all three); services.py
; walks the container, where the shape difference is cheap to handle.

(class_declaration
  name: (_) @service.heritage_class
  (class_heritage) @service.heritage
) @service.heritage_decl

; ── CommonJS member exports ───────────────────────────────────────────────────
; `exports.x = fn` / `module.exports.y = wrap(fn)`. Only exported CLASSES had a
; pattern, so a CommonJS module's entire public surface produced no nodes.
;
; Two separate patterns rather than one alternation on the object: a shared
; predicate applies to the WHOLE pattern, so an alternation here would force
; the bare-`exports` branch to satisfy a predicate on a capture it never binds.
; A computed `exports[key] = …` is a subscript_expression and is excluded by
; construction — its name is not knowable statically.

(assignment_expression
  left: (member_expression
    object: (identifier) @_exports
    (#eq? @_exports "exports")
    property: (property_identifier) @service.cjs_export
  )
  right: (_) @service.cjs_value
) @service.cjs_assign

(assignment_expression
  left: (member_expression
    object: (member_expression
      object: (identifier) @_module
      (#eq? @_module "module")
      property: (property_identifier) @_exports2
      (#eq? @_exports2 "exports")
    )
    property: (property_identifier) @service.cjs_export
  )
  right: (_) @service.cjs_value
) @service.cjs_assign

; ── imports ───────────────────────────────────────────────────────────────────

; ES module: import ... from "..."
(import_statement
  source: (string) @import.path
) @import.es

; CommonJS: require("...")
(call_expression
  function: (identifier) @_req
  (#eq? @_req "require")
  arguments: (arguments
    (string) @import.path
  )
) @import.cjs
