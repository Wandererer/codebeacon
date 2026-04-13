; ── FastAPI (Python) ──────────────────────────────────────────────────────────
; Grammar: tree-sitter-python
;
; Captures:
;   @route.decorator     - @app.get / @router.post etc. decorator node
;   @route.object        - app/router object name
;   @route.method        - HTTP method (get/post/put/delete/patch)
;   @route.path          - path string
;   @route.func_name     - handler function name
;   @route.prefix        - APIRouter(prefix="...") value
;   @service.func_name   - Depends() dependency function name
;   @service.class_name  - class with methods using Depends
;   @entity.class_name   - BaseModel / SQLAlchemy Base subclass
;   @entity.field_name   - model field name
;   @entity.field_type   - model field type annotation
;   @router.include      - app.include_router(router, prefix="...")
;   @import.path         - import path

; ── @app.get("/path") / @router.post("/path") ────────────────────────────────

(decorated_definition
  (decorator
    (call
      function: (attribute
        object: (identifier) @route.object
        attribute: (identifier) @route.method
        (#match? @route.method "^(get|post|put|delete|patch|options|head)$")
      )
      arguments: (argument_list
        (string) @route.path
      )
    )
  )
  definition: (function_definition
    name: (identifier) @route.func_name
  )
) @route.handler

; ── APIRouter(prefix="/api/v1") ───────────────────────────────────────────────

(assignment
  left: (identifier) @route.router_name
  right: (call
    function: (identifier) @_apiRouter
    (#eq? @_apiRouter "APIRouter")
    arguments: (argument_list
      (keyword_argument
        name: (identifier) @_prefix_key
        (#eq? @_prefix_key "prefix")
        value: (string) @route.prefix
      )
    )
  )
) @route.router_decl

; ── app.include_router(router, prefix="...") ─────────────────────────────────

; With prefix keyword argument
(call
  function: (attribute
    object: (identifier) @_app
    attribute: (identifier) @_include
    (#eq? @_include "include_router")
  )
  arguments: (argument_list
    (identifier) @router.include_router
    (keyword_argument
      name: (identifier) @_pk
      (#eq? @_pk "prefix")
      value: (string) @router.include_prefix
    )
  )
) @router.include

; Without prefix keyword argument
(call
  function: (attribute
    object: (identifier) @_app2
    attribute: (identifier) @_include2
    (#eq? @_include2 "include_router")
  )
  arguments: (argument_list
    (identifier) @router.include_router
  )
) @router.include_no_prefix

; ── Depends() function dependency ────────────────────────────────────────────

; Functions that take parameters (potential service functions)
(function_definition
  name: (identifier) @service.func_name
  parameters: (parameters
    (typed_parameter
      (identifier) @_param
    )
  )
) @service.function

; Depends() in function signature
(call
  function: (identifier) @_depends
  (#eq? @_depends "Depends")
  arguments: (argument_list
    (identifier) @service.depends_func
  )
) @service.depends

; ── BaseModel / SQLAlchemy subclass (entity) ─────────────────────────────────

; Direct identifier base class: class User(BaseModel)
(class_definition
  name: (identifier) @entity.class_name
  superclasses: (argument_list
    (identifier) @_base
    (#match? @_base "^(BaseModel|Base|DeclarativeBase|SQLModel)$")
  )
) @entity.class

; Attribute base class: class User(db.Model)
(class_definition
  name: (identifier) @entity.class_name
  superclasses: (argument_list
    (attribute
      attribute: (identifier) @_base
      (#match? @_base "^(Model|Base)$")
    )
  )
) @entity.class_attr

; Entity fields (type-annotated class attributes)
(class_definition
  body: (block
    (expression_statement
      (assignment
        left: (identifier) @entity.field_name
        type: (type
          (identifier) @entity.field_type
        )
      )
    )
  )
) @entity.with_fields

; ── imports ───────────────────────────────────────────────────────────────────

(import_from_statement
  module_name: _ @import.path
) @import.from

(import_statement
  name: _ @import.path
) @import.plain
