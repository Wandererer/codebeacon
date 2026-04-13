; ── Gin / Echo / Fiber (Go) ───────────────────────────────────────────────────
; Grammar: tree-sitter-go
;
; Go struct tag parsing note:
;   GORM struct tags are raw string literals: `gorm:"primaryKey"`.
;   These are parsed by extract/entities.py using regex on the raw text,
;   not by tree-sitter queries (tree-sitter-go does not parse struct tags).
;
; Captures:
;   @route.method       - GET/POST/PUT/DELETE/PATCH/Any etc.
;   @route.path         - path string
;   @route.object       - router/group variable name
;   @route.group_prefix - r.Group("/api") prefix string
;   @route.handler_name - handler function identifier
;   @service.struct_name  - struct name (service)
;   @service.field_type   - field type (for DI via struct embedding)
;   @entity.struct_name   - GORM model struct name
;   @entity.field_name    - struct field name
;   @entity.field_tag     - raw struct tag string (for GORM parsing)
;   @import.path          - import path string

; ── r.GET("/path", handler) ──────────────────────────────────────────────────

(expression_statement
  (call_expression
    function: (selector_expression
      operand: (identifier) @route.object
      field: (field_identifier) @route.method
      (#match? @route.method "^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|Any|Handle|UseWithErr|Use)$")
    )
    arguments: (argument_list
      (interpreted_string_literal) @route.path
      (identifier) @route.handler_name
    )
  )
) @route.call

; Case-insensitive method names (Echo: e.GET, Fiber: app.Get)
(expression_statement
  (call_expression
    function: (selector_expression
      operand: (identifier) @route.object
      field: (field_identifier) @route.method
      (#match? @route.method "^(Get|Post|Put|Patch|Delete|Options|Head|All|Add)$")
    )
    arguments: (argument_list
      (interpreted_string_literal) @route.path
      (identifier) @route.handler_name
    )
  )
) @route.call_lower

; ── r.Group("/prefix") ───────────────────────────────────────────────────────

(short_var_declaration
  left: (expression_list
    (identifier) @route.group_name
  )
  right: (expression_list
    (call_expression
      function: (selector_expression
        operand: (identifier) @_router
        field: (field_identifier) @_group
        (#eq? @_group "Group")
      )
      arguments: (argument_list
        (interpreted_string_literal) @route.group_prefix
      )
    )
  )
) @route.group_decl

; ── Service struct ────────────────────────────────────────────────────────────

(type_declaration
  (type_spec
    name: (type_identifier) @service.struct_name
    type: (struct_type
      (field_declaration_list
        (field_declaration
          type: (pointer_type
            (type_identifier) @service.field_type
          )
        )
      )
    )
  )
) @service.struct

(type_declaration
  (type_spec
    name: (type_identifier) @service.struct_name
    type: (struct_type
      (field_declaration_list
        (field_declaration
          type: (type_identifier) @service.field_type
        )
      )
    )
  )
) @service.struct_plain

; ── GORM entity struct ────────────────────────────────────────────────────────

(type_declaration
  (type_spec
    name: (type_identifier) @entity.struct_name
    type: (struct_type
      (field_declaration_list
        (field_declaration
          name: (field_identifier) @entity.field_name
          type: _ @entity.field_type
          tag: (raw_string_literal) @entity.field_tag
        )
      )
    )
  )
) @entity.struct

; Struct with no tags (still useful for type extraction)
(type_declaration
  (type_spec
    name: (type_identifier) @entity.struct_name
    type: (struct_type)
  )
) @entity.struct_bare

; ── imports ───────────────────────────────────────────────────────────────────

(import_declaration
  (import_spec_list
    (import_spec
      path: (interpreted_string_literal) @import.path
    )
  )
) @import.block

(import_declaration
  (import_spec
    path: (interpreted_string_literal) @import.path
  )
) @import.single
