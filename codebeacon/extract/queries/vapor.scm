; ── Vapor (Swift) ────────────────────────────────────────────────────────────
; Grammar: tree-sitter-swift
;
; Swift grammar note:
;   - call_expression + navigation_expression: app.get("path") { ... }
;   - navigation_suffix with simple_identifier: method name
;   - call_suffix + value_arguments: route path arguments
;   - line_string_literal: Swift double-quoted string
;   - line_str_text: string content
;   - property_declaration: let x = app.grouped("prefix")
;   - attribute: @ID, @Field property wrappers
;
; Note: Swift paths can be multiple string arguments: app.get("users", ":id")
; extract/routes.py joins them with "/"
;
; Captures:
;   @route.object       - app / group variable
;   @route.method       - get/post/put/patch/delete/on
;   @route.path_segment - path string segment(s)
;   @route.grouped_name - grouped variable name
;   @route.grouped_prefix - grouped path string
;   @entity.class_name  - Fluent Model class
;   @entity.field_name  - @Field property name
;   @entity.field_key   - @Field(key: "column") value
;   @entity.id_name     - @ID property name
;   @service.func_name  - routes configuration function
;   @import.name        - import module name

; ── app.get("path") { ... } ──────────────────────────────────────────────────

(call_expression
  (navigation_expression
    (simple_identifier) @route.object
    (navigation_suffix
      (simple_identifier) @route.method
      (#match? @route.method "^(get|post|put|patch|delete|on|grouped)$")
    )
  )
  (call_suffix
    (value_arguments
      (value_argument
        (line_string_literal
          (line_str_text) @route.path_segment
        )
      )
    )
    (lambda_literal)?
  )
) @route.call

; ── let users = app.grouped("users") ─────────────────────────────────────────

(property_declaration
  (pattern
    (simple_identifier) @route.grouped_name
  )
  (call_expression
    (navigation_expression
      (simple_identifier) @_app
      (navigation_suffix
        (simple_identifier) @_grouped
        (#eq? @_grouped "grouped")
      )
    )
    (call_suffix
      (value_arguments
        (value_argument
          (line_string_literal
            (line_str_text) @route.grouped_prefix
          )
        )
      )
    )
  )
) @route.grouped_decl

; ── Fluent Model class ────────────────────────────────────────────────────────

(class_declaration
  (type_modifiers (attribute (user_type (type_identifier) @_final (#eq? @_final "final"))))?
  (simple_identifier) @entity.class_name
  (type_inheritance_clause
    (inheritance_specifier
      (user_type
        (type_identifier) @_base
        (#match? @_base "^(Model|Content|Authenticatable)$")
      )
    )
  )
) @entity.model

; @Field(key: "column_name") var fieldName: Type
(property_declaration
  (modifiers
    (attribute
      (user_type (type_identifier) @_attr (#eq? @_attr "Field"))
      (attribute_argument_clause
        (value_argument
          (simple_identifier) @_key (#eq? @_key "key")
          (line_string_literal (line_str_text) @entity.field_key)
        )
      )
    )
  )
  (pattern (simple_identifier) @entity.field_name)
) @entity.field

; @ID(key: .id) var id
(property_declaration
  (modifiers
    (attribute
      (user_type (type_identifier) @_id (#eq? @_id "ID"))
    )
  )
  (pattern (simple_identifier) @entity.id_name)
) @entity.id_field

; ── Routes function ───────────────────────────────────────────────────────────

(function_declaration
  (simple_identifier) @service.func_name
) @service.func

; ── imports ───────────────────────────────────────────────────────────────────

(import_declaration
  (identifier
    (simple_identifier) @import.name
  )
) @import.decl
