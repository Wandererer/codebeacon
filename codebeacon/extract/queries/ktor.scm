; ── Ktor (Kotlin) ─────────────────────────────────────────────────────────────
; Grammar: tree-sitter-kotlin
;
; Kotlin grammar note:
;   - call_expression: f(args) — can have trailing lambda
;   - annotated_lambda / lambda_literal: trailing { } block
;   - value_arguments: (args)
;   - value_argument → string_literal → string_content: path string
;   - identifier: function name (get, post, route, routing)
;   - qualified_identifier: import paths
;
; Ktor routing DSL nesting:
;   routing {
;     get("/a") { }          → GET /a
;     route("/prefix") {
;       get("/b") { }        → GET /prefix/b
;     }
;   }
; Path composition is done by extract/routes.py by tracking nesting depth
; using start_point line numbers. This file captures individual route/method calls.
;
; Captures:
;   @route.method         - get/post/put/patch/delete (HTTP method)
;   @route.path           - path string content
;   @route.route_prefix   - route("prefix") path — prefix scope
;   @route.call_line      - line number for nesting (via @route.call node)
;   @service.koin_type    - Koin: single/factory/scoped class
;   @entity.table_name    - Exposed Table object name
;   @entity.column_name   - Exposed column name
;   @import.path          - import qualified path

; ── routing { get("/path") { } } ─────────────────────────────────────────────

; Direct HTTP method call: get("/path") { }
(call_expression
  (call_expression
    (identifier) @route.method
    (#match? @route.method "^(get|post|put|patch|delete|options|head)$")
    (value_arguments
      (value_argument
        (string_literal
          (string_content) @route.path
        )
      )
    )
  )
  (annotated_lambda)?
) @route.method_call

; Also handle: get("/path") without trailing lambda
(call_expression
  (identifier) @route.method
  (#match? @route.method "^(get|post|put|patch|delete|options|head)$")
  (value_arguments
    (value_argument
      (string_literal
        (string_content) @route.path
      )
    )
  )
) @route.method_call_simple

; ── route("/prefix") { } — creates a path prefix scope ───────────────────────

(call_expression
  (call_expression
    (identifier) @_route_fn
    (#eq? @_route_fn "route")
    (value_arguments
      (value_argument
        (string_literal
          (string_content) @route.route_prefix
        )
      )
    )
  )
  (annotated_lambda)
) @route.prefix_scope

; ── Koin DI: single { UserService(get()) } ───────────────────────────────────

(call_expression
  (identifier) @_koin_scope
  (#match? @_koin_scope "^(single|factory|scoped|viewModel|worker)$")
  (annotated_lambda
    (lambda_literal
      (call_expression
        (identifier) @service.koin_type
        (value_arguments)?
      )
    )
  )
) @service.koin_binding

; ── Exposed ORM: object Users : Table() ──────────────────────────────────────

(object_declaration
  (identifier) @entity.table_name
  (delegation_specifier
    (constructor_invocation
      (user_type (identifier) @_table (#match? @_table "^(Table|IntIdTable|LongIdTable|UUIDTable|IdTable)$"))
    )
  )
) @entity.table

; Exposed columns: val id = integer("id")
(property_declaration
  (variable_declaration
    (simple_identifier) @entity.column_name
  )
  (call_expression
    (identifier) @entity.column_type
    (#match? @entity.column_type "^(integer|long|varchar|text|bool|double|float|decimal|uuid|reference|optReference|enumeration|enumerationByName|date|datetime|timestamp)$")
    (value_arguments
      (value_argument
        (string_literal
          (string_content) @entity.column_key
        )
      )
    )
  )
) @entity.column

; ── Data class (Kotlin entity / DTO) ─────────────────────────────────────────

(class_declaration
  (modifiers
    (class_modifier) @_data
    (#eq? @_data "data")
  )
  (simple_identifier) @entity.class_name
) @entity.data_class

; ── Regular class (service) ───────────────────────────────────────────────────

(class_declaration
  (simple_identifier) @service.class_name
) @service.class

; ── imports ───────────────────────────────────────────────────────────────────

(import
  (qualified_identifier) @import.path
) @import.decl
