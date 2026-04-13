; ── Spring Boot (Java) tree-sitter queries ──────────────────────────────────
; Grammar: tree-sitter-java
;
; Java grammar note:
;   - marker_annotation: @Override, @RestController (no arguments)
;   - annotation: @RequestMapping("/path") (with arguments)
;   Both appear as children of `modifiers`.
;
; Captures used by routes.py / services.py / entities.py:
;   @route.class_annotation  - @RequestMapping on class
;   @route.method_annotation - @GetMapping/@PostMapping/etc on method
;   @route.class_name        - controller class name
;   @route.method_name       - handler method name
;   @route.path_value        - path string literal
;   @service.annotation      - @Service/@Component etc. name
;   @service.class_name      - service class name
;   @service.interface       - implemented interface name
;   @entity.class_name       - entity class name
;   @entity.table_name       - @Table(name="...") value
;   @di.field_type           - @Autowired field type
;   @di.field_name           - @Autowired field name
;   @di.ctor_param_type      - constructor injection param type
;   @di.ctor_param_name      - constructor injection param name
;   @import.path             - import path

; ── Controller class ─────────────────────────────────────────────────────────

(class_declaration
  (modifiers
    [
      (annotation name: (identifier) @route.class_annotation)
      (marker_annotation name: (identifier) @route.class_annotation)
    ]
    (#match? @route.class_annotation "^(RestController|Controller)$")
  )
  name: (identifier) @route.class_name
) @route.controller_class

; Class-level @RequestMapping path
(class_declaration
  (modifiers
    (annotation
      name: (identifier) @_rm
      (#eq? @_rm "RequestMapping")
      arguments: (annotation_argument_list
        [
          (string_literal) @route.class_path
          (element_value_pair
            key: (identifier) @_key
            (#match? @_key "^(value|path)$")
            value: [
              (string_literal) @route.class_path
              (array_initializer (string_literal) @route.class_path)
            ]
          )
        ]
      )
    )
  )
) @route.class_mapping

; ── Method-level route annotations ───────────────────────────────────────────

; With arguments (annotation)
(method_declaration
  (modifiers
    (annotation
      name: (identifier) @route.method_annotation
      (#match? @route.method_annotation "^(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)$")
    )
  )
  name: (identifier) @route.method_name
) @route.handler_method

; Without arguments (marker_annotation) — e.g. @GetMapping with no path
(method_declaration
  (modifiers
    (marker_annotation
      name: (identifier) @route.method_annotation
      (#match? @route.method_annotation "^(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)$")
    )
  )
  name: (identifier) @route.method_name
) @route.handler_method

; Method annotation WITH path value
(method_declaration
  (modifiers
    (annotation
      name: (identifier) @_ann
      (#match? @_ann "^(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)$")
      arguments: (annotation_argument_list
        [
          (string_literal) @route.path_value
          (element_value_pair
            key: (identifier) @_key
            (#match? @_key "^(value|path)$")
            value: [
              (string_literal) @route.path_value
              (array_initializer (string_literal) @route.path_value)
            ]
          )
        ]
      )
    )
  )
  name: (identifier) @route.method_name_with_path
) @route.method_with_path

; ── Service / Component / Repository ─────────────────────────────────────────

(class_declaration
  (modifiers
    [
      (annotation name: (identifier) @service.annotation)
      (marker_annotation name: (identifier) @service.annotation)
    ]
    (#match? @service.annotation "^(Service|Component|Repository|RestController|Controller)$")
  )
  name: (identifier) @service.class_name
) @service.class

; Implemented interfaces
(class_declaration
  name: (identifier) @service.class_name
  (super_interfaces
    (type_list
      (type_identifier) @service.interface
    )
  )
) @service.with_interface

; ── Entity ────────────────────────────────────────────────────────────────────

(class_declaration
  (modifiers
    (marker_annotation
      name: (identifier) @entity.annotation
      (#eq? @entity.annotation "Entity")
    )
  )
  name: (identifier) @entity.class_name
) @entity.class

; @Table(name = "...") — separate query (not inside class_declaration to avoid nesting issues)
(annotation
  name: (identifier) @_tbl
  (#eq? @_tbl "Table")
  arguments: (annotation_argument_list
    (element_value_pair
      key: (identifier) @_name_key
      (#eq? @_name_key "name")
      value: (string_literal) @entity.table_name
    )
  )
) @entity.table_annotation

; ── DI — @Autowired field injection ──────────────────────────────────────────

(field_declaration
  (modifiers
    [
      (annotation name: (identifier) @_aw (#eq? @_aw "Autowired"))
      (marker_annotation name: (identifier) @_aw (#eq? @_aw "Autowired"))
    ]
  )
  type: (type_identifier) @di.field_type
  (variable_declarator
    name: (identifier) @di.field_name
  )
) @di.autowired_field

; ── DI — Constructor injection ───────────────────────────────────────────────

(constructor_declaration
  parameters: (formal_parameters
    (formal_parameter
      type: (type_identifier) @di.ctor_param_type
      name: (identifier) @di.ctor_param_name
    )
  )
) @di.constructor

; ── Entity fields ─────────────────────────────────────────────────────────────

(field_declaration
  (modifiers
    [
      (annotation name: (identifier) @entity.field_annotation)
      (marker_annotation name: (identifier) @entity.field_annotation)
    ]
    (#match? @entity.field_annotation "^(Id|Column|ManyToOne|OneToMany|ManyToMany|OneToOne|JoinColumn|GeneratedValue)$")
  )
  type: _ @entity.field_type
  (variable_declarator
    name: (identifier) @entity.field_name
  )
) @entity.field

; ── Imports ───────────────────────────────────────────────────────────────────

(import_declaration
  (scoped_identifier) @import.path
) @import.decl
