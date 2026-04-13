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
; Captures:
;   @route.proc_macro     - get/post/put/patch/delete (Actix proc macro name)
;   @route.path           - path string content
;   @route.func_name      - handler function name
;   @route.axum_method    - Axum: get/post/put/delete (from axum::routing::get)
;   @route.axum_path      - Axum: path string in Router::new().route(path, ...)
;   @entity.struct_name   - struct with derive macros
;   @entity.derive_trait  - Queryable/DeriveEntityModel/Serialize etc.
;   @entity.field_name    - struct field name
;   @entity.field_type    - struct field type
;   @service.struct_name  - AppState / service struct
;   @import.path          - use path

; ── Actix: #[get("/users")] async fn handler() ───────────────────────────────

(function_item
  .
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
  name: (identifier) @route.func_name
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

; ── #[derive(Queryable, Serialize, ...)] struct ──────────────────────────────

(struct_item
  .
  (attribute_item
    (attribute
      (identifier) @_derive (#eq? @_derive "derive")
      (token_tree
        (identifier) @entity.derive_trait
        (#match? @entity.derive_trait "^(Queryable|DeriveEntityModel|DeriveRelation|FromRow|Model|Serialize|Deserialize|sqlx)$")
      )
    )
  )
  name: (type_identifier) @entity.struct_name
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
