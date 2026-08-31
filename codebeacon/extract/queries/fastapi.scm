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
;   @router.include_call - ANY <x>.include_router(...) call (args walked in Python)
;   @route.alias_name    - `local = pkg.router` alias left-hand side
;   @route.alias_target  - the aliased router expression
;   @import.path         - import path

; ── @app.get("/path") / @router.post("/path") ────────────────────────────────
; The decorator object accepts an attribute as well as a bare identifier:
; `@consumer.consumer_router.get("/ping")` is idiomatic and an identifier-only
; object made the whole route invisible (not merely un-prefixed).

(decorated_definition
  (decorator
    (call
      function: (attribute
        object: [
          (identifier)
          (attribute)
        ] @route.object
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
;
; ONE broad pattern per physical call, deliberately. The previous pair of
; patterns (with-prefix / without-prefix) BOTH matched a prefixed call, so any
; naive "collect every include match" reading double-counted it and emitted a
; phantom unprefixed route. Enumerating the argument shapes in .scm instead
; (identifier / attribute / `router=` keyword, x includer identifier /
; attribute) explodes combinatorially. routes.py::_parse_include_router walks
; the argument list to pull includer, child router and prefix.

(call
  function: (attribute
    attribute: (identifier) @_include
    (#eq? @_include "include_router")
  )
) @router.include_call

; ── `router = pkg.some_router` alias ─────────────────────────────────────────
; A router imported through its module and re-bound locally is decorated under
; the local name but mounted under the attribute expression, so without this
; the two never meet and the mount prefix is lost. Restricted to attribute
; right-hand sides: a bare `a = b` rebinding is too common to be worth the
; match noise, and routers are conventionally reached through their module.

(assignment
  left: (identifier) @route.alias_name
  right: (attribute) @route.alias_target
) @route.alias

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

; `from pkg import name` — also capture each imported name so the edge can
; bind the real symbol/submodule, not just the module path (graphify #1146).
(import_from_statement
  module_name: _ @import.path
  name: (dotted_name) @import.item
) @import.from_item

(import_from_statement
  module_name: _ @import.path
  name: (aliased_import name: (dotted_name) @import.item)
) @import.from_item

; A plain `import x` and an aliased `import x as y` are different node
; shapes. The wildcard captured the WHOLE aliased_import, so the emitted
; target was the literal string "widget as w" — matching no node label, which
; dropped the import edge entirely rather than merely mislabelling it.
; Capturing the dotted_name in both shapes mirrors how the from-import case
; above already handles its alias.

(import_statement
  name: (dotted_name) @import.path
) @import.plain

(import_statement
  name: (aliased_import
    name: (dotted_name) @import.path
  )
) @import.plain
