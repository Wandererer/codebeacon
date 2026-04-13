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

; ── router.route("/path").get(handler).post(handler) ─────────────────────────

(call_expression
  function: (member_expression
    object: (call_expression
      function: (member_expression
        object: (identifier) @route.object
        property: (property_identifier) @_route_kw
        (#eq? @_route_kw "route")
      )
      arguments: (arguments
        .
        (string) @route.path
      )
    )
    property: (property_identifier) @route.method
    (#match? @route.method "^(get|post|put|patch|delete|options|head|all)$")
  )
) @route.chained

; ── app.use("/prefix", router) — prefix mounting ─────────────────────────────

(expression_statement
  (call_expression
    function: (member_expression
      object: (identifier) @_obj
      property: (property_identifier) @_use
      (#eq? @_use "use")
    )
    arguments: (arguments
      .
      (string) @route.use_prefix
      .
      _
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

(export_statement
  declaration: (class_declaration
    name: (identifier) @service.name
  )
) @service.export_class

(class_declaration
  name: (identifier) @service.name
) @service.class

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
