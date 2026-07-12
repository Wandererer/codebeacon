; ── Actix-web / Axum (Rust) ───────────────────────────────────────────────────
; Grammar: tree-sitter-rust
;
; Rust grammar note:
;   - attribute_item: #[get("/users")]
;   - attribute: get("/users") — identifier + token_tree
;   - token_tree: the (...) argument list (unparsed by tree-sitter)
;   - string_literal / string_content: path string
;   - function_item: async fn handler
;   - struct_item: struct definition
;   - field_declaration: struct field
;
; Proc macro note:
;   #[derive(Queryable, Serialize)] — captured by @entity.derive_trait
;   Diesel table! macro handled by regexp in entities.py
;
; Warp note (filter combinators — no attribute item or router table):
;   warp::path!("users" / u32).and(warp::get()).and_then(get_user)
;   A route's path, HTTP method, and handler are three unrelated nodes strung
;   along one method-call chain, so no single pattern captures a whole route.
;   The pieces are captured independently and correlated in _interpret_actix by
;   the innermost enclosing let_declaration/block (@route.warp_scope). Honest
;   limits: filters joined by `.or(...)` inside ONE binding collapse into a
;   single concatenated route; `warp::path::param()` / generic (non-string)
;   segments and closure (non-identifier) handlers are not resolved.
;
; Captures:
;   @route.proc_macro     - get/post/put/patch/delete (Actix proc macro name)
;   @route.path           - path string content
;   @route.func_name      - handler function name
;   @route.axum_method    - Axum: get/post/put/delete (from axum::routing::get)
;   @route.axum_path      - Axum: path string in Router::new().route(path, ...)
;   @route.warp_path_macro   - Warp: warp::path!("a" / Type) macro node
;   @route.warp_macro_tokens - Warp: the macro's (…) token_tree (parsed in extractor)
;   @route.warp_path_call    - Warp: warp::path("seg") single-segment filter call
;   @route.warp_seg          - Warp: the path("seg") segment string content
;   @route.warp_method_call  - Warp: warp::get()/post()/… method combinator call
;   @route.warp_method       - Warp: the combinator name (get/post/put/…)
;   @route.warp_handler_call - Warp: .map()/.and_then() call with an identifier arg
;   @route.warp_handler      - Warp: bare-identifier handler name
;   @route.warp_scope        - Warp: enclosing let_declaration/block for correlation
;   @entity.struct_name   - struct with derive macros
;   @entity.derive_trait  - Queryable/DeriveEntityModel/Serialize etc.
;   @entity.field_name    - struct field name
;   @entity.field_type    - struct field type
;   @service.struct_name  - AppState / service struct
;   @import.path          - use path

; ── Actix: #[get("/users")] async fn handler() ───────────────────────────────

; tree-sitter-rust: attribute_item is a SIBLING preceding function_item, not a
; child of it. The `(...) . (...)` grouping with the `.` anchor matches an
; attribute_item immediately followed by a function_item. The old form nested
; the attribute inside function_item → impossible pattern → whole query failed.
(
  (attribute_item
    (attribute
      (identifier) @route.proc_macro
      (#match? @route.proc_macro "^(get|post|put|patch|delete|options|head)$")
      (token_tree
        (string_literal
          (string_content) @route.path
        )
      )
    )
  )
  .
  (function_item
    name: (identifier) @route.func_name
  )
) @route.actix_handler

; ── Axum: Router::new().route("/users", get(handler)) ────────────────────────

(call_expression
  function: (field_expression
    field: (field_identifier) @_route_fn
    (#eq? @_route_fn "route")
  )
  arguments: (arguments
    (string_literal
      (string_content) @route.axum_path
    )
    (call_expression
      function: (identifier) @route.axum_method
      (#match? @route.axum_method "^(get|post|put|patch|delete|options|head)$")
      arguments: (arguments
        (identifier) @route.axum_handler
      )
    )
  )
) @route.axum_route

; ── Warp: warp::path!("users" / u32).and(warp::get()).and_then(handler) ───────
; Warp has no attribute item or router table; a route is a filter *chain*. The
; four piece-patterns below fire independently wherever they appear; the two
; @route.warp_scope patterns capture the let_declaration / block boundaries that
; _interpret_actix uses to bucket the pieces of one chain back together.

; warp::path!("seg" / Type) macro — multi-segment path (parsed from token_tree)
(macro_invocation
  macro: (scoped_identifier
    path: (identifier) @_warp_ns (#eq? @_warp_ns "warp")
    name: (identifier) @_warp_mac (#eq? @_warp_mac "path")
  )
  (token_tree) @route.warp_macro_tokens
) @route.warp_path_macro

; warp::path("seg") — single-segment filter (composed via .and(warp::path(...)))
(call_expression
  function: (scoped_identifier
    path: (identifier) @_warp_ns2 (#eq? @_warp_ns2 "warp")
    name: (identifier) @_warp_fn (#eq? @_warp_fn "path")
  )
  arguments: (arguments
    (string_literal
      (string_content) @route.warp_seg
    )
  )
) @route.warp_path_call

; warp::get()/post()/put()/patch()/delete()/options()/head() method combinator
(call_expression
  function: (scoped_identifier
    path: (identifier) @_warp_ns3 (#eq? @_warp_ns3 "warp")
    name: (identifier) @route.warp_method
    (#match? @route.warp_method "^(get|post|put|patch|delete|options|head)$")
  )
) @route.warp_method_call

; .map(handler) / .and_then(handler) — only a bare-identifier handler resolves;
; a closure (|..| ...) argument is intentionally left unlinked.
(call_expression
  function: (field_expression
    field: (field_identifier) @_warp_link
    (#match? @_warp_link "^(map|and_then)$")
  )
  arguments: (arguments
    (identifier) @route.warp_handler
  )
) @route.warp_handler_call

; Chain scopes: the innermost enclosing binding/block owns a chain's pieces.
(let_declaration) @route.warp_scope
(block) @route.warp_scope

; ── #[derive(Queryable, Serialize, ...)] struct ──────────────────────────────

; Same sibling relationship as the proc-macro handler above: the
; #[derive(...)] attribute_item precedes the struct_item.
(
  (attribute_item
    (attribute
      (identifier) @_derive (#eq? @_derive "derive")
      (token_tree
        (identifier) @entity.derive_trait
        (#match? @entity.derive_trait "^(Queryable|DeriveEntityModel|DeriveRelation|FromRow|Model|Serialize|Deserialize|sqlx)$")
      )
    )
  )
  .
  (struct_item
    name: (type_identifier) @entity.struct_name
  )
) @entity.struct

; All struct fields
(struct_item
  name: (type_identifier) @entity.struct_name
  body: (field_declaration_list
    (field_declaration
      name: (field_identifier) @entity.field_name
      type: _ @entity.field_type
    )
  )
) @entity.struct_with_fields

; ── All attribute_items on functions (for proc macro detection) ───────────────

(attribute_item
  (attribute
    (identifier) @route.attr_name
    (#match? @route.attr_name "^(get|post|put|patch|delete|options|head|route|web)$")
  )
) @route.attr

; ── AppState / service struct ─────────────────────────────────────────────────

(struct_item
  name: (type_identifier) @service.struct_name
) @service.struct

; ── use declarations ─────────────────────────────────────────────────────────

(use_declaration
  argument: _ @import.path
) @import.use
