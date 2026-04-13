; ── NestJS (TypeScript) ───────────────────────────────────────────────────────
; Grammar: tree-sitter-typescript
;
; TypeScript AST note:
;   In tree-sitter-typescript, class-level decorators (@Controller, @Injectable,
;   @Entity) are siblings of class_declaration inside export_statement, not
;   children of class_declaration.
;   Method-level decorators (@Get, @Post) are siblings of method_definition
;   inside class_body, connected via the `.` (immediate sibling) anchor.
;
; Captures:
;   @route.controller_prefix - @Controller("prefix") value
;   @route.class_name        - controller class name
;   @route.method_decorator  - @Get/@Post/@Put/@Delete/@Patch
;   @route.method_name       - handler method name
;   @route.path_value        - path string literal
;   @service.class_name      - @Injectable() class name
;   @service.inject_type     - constructor injected type
;   @module.providers        - providers array items
;   @entity.class_name       - @Entity() class name
;   @import.path             - import source

; ── @Controller("prefix") class ──────────────────────────────────────────────

; export_statement wraps the decorator + class_declaration
(export_statement
  (decorator
    (call_expression
      function: (identifier) @_ctrl
      (#eq? @_ctrl "Controller")
      arguments: (arguments
        (string) @route.controller_prefix
      )
    )
  )
  declaration: (class_declaration
    name: (type_identifier) @route.class_name
  )
) @route.controller_with_prefix

; @Controller() without prefix
(export_statement
  (decorator
    (call_expression
      function: (identifier) @_ctrl2
      (#eq? @_ctrl2 "Controller")
      arguments: (arguments)
    )
  )
  declaration: (class_declaration
    name: (type_identifier) @route.class_name
  )
) @route.controller_no_prefix

; Non-exported @Controller
(class_declaration
  (decorator
    (call_expression
      function: (identifier) @_ctrl3
      (#eq? @_ctrl3 "Controller")
      arguments: (arguments
        (string) @route.controller_prefix
      )
    )
  )
  name: (type_identifier) @route.class_name
) @route.controller_with_prefix_noexport

; ── HTTP method decorators on methods (sibling pattern) ─────────────────────

; Decorator + method_definition as adjacent siblings in class_body
(class_body
  (decorator
    (call_expression
      function: (identifier) @route.method_decorator
      (#match? @route.method_decorator "^(Get|Post|Put|Delete|Patch|Options|Head|All)$")
      arguments: (arguments
        (string) @route.path_value
      )
    )
  )
  .
  (method_definition
    name: (property_identifier) @route.method_name
  )
) @route.handler

; Decorator without path argument
(class_body
  (decorator
    (call_expression
      function: (identifier) @route.method_decorator
      (#match? @route.method_decorator "^(Get|Post|Put|Delete|Patch|Options|Head|All)$")
      arguments: (arguments)
    )
  )
  .
  (method_definition
    name: (property_identifier) @route.method_name
  )
) @route.handler_no_path

; ── @Injectable() service ────────────────────────────────────────────────────

(export_statement
  (decorator
    (call_expression
      function: (identifier) @_inj
      (#eq? @_inj "Injectable")
    )
  )
  declaration: (class_declaration
    name: (type_identifier) @service.class_name
  )
) @service.injectable

; Non-exported @Injectable
(class_declaration
  (decorator
    (call_expression
      function: (identifier) @_inj2
      (#eq? @_inj2 "Injectable")
    )
  )
  name: (type_identifier) @service.class_name
) @service.injectable_noexport

; Constructor DI (inside any class)
; required_parameter uses field "pattern" for the identifier, not "name"
(method_definition
  name: (property_identifier) @_ctor
  (#eq? @_ctor "constructor")
  parameters: (formal_parameters
    (required_parameter
      pattern: (identifier) @_pname
      type: (type_annotation
        (type_identifier) @service.inject_type
      )
    )
  )
) @service.constructor_di

; ── @Module({ providers: [...] }) ────────────────────────────────────────────

(export_statement
  (decorator
    (call_expression
      function: (identifier) @_mod
      (#eq? @_mod "Module")
      arguments: (arguments
        (object
          (pair
            key: (property_identifier) @_providers_key
            (#eq? @_providers_key "providers")
            value: (array
              (identifier) @module.providers
            )
          )
        )
      )
    )
  )
) @module.class

; ── @Entity() / @Schema() ───────────────────────────────────────────────────

(export_statement
  (decorator
    (call_expression
      function: (identifier) @_ent
      (#match? @_ent "^(Entity|Schema)$")
    )
  )
  declaration: (class_declaration
    name: (type_identifier) @entity.class_name
  )
) @entity.class

; ── imports ───────────────────────────────────────────────────────────────────

(import_statement
  source: (string) @import.path
) @import.decl
