; ── Flask (Python) ────────────────────────────────────────────────────────────
; Grammar: tree-sitter-python
;
; Captures:
;   @route.decorator     - @app.route / @bp.route decorator
;   @route.object        - app/blueprint object name
;   @route.path          - path string
;   @route.methods       - methods list ["GET","POST"]
;   @route.func_name     - handler function name
;   @blueprint.name      - Blueprint variable name
;   @blueprint.url_prefix - url_prefix value
;   @blueprint.import_name - blueprint name string
;   @app.register_bp     - app.register_blueprint(bp, url_prefix="...")
;   @app.register_prefix - url_prefix in register_blueprint
;   @entity.class_name   - db.Model subclass name
;   @entity.field_name   - field name
;   @entity.field_type   - Column(...) type
;   @import.path         - import path

; ── @app.route("/path") / @blueprint.route("/path") ─────────────────────────

(decorated_definition
  (decorator
    (call
      function: (attribute
        object: (identifier) @route.object
        attribute: (identifier) @_route_attr
        (#eq? @_route_attr "route")
      )
      arguments: (argument_list
        (string) @route.path
        (keyword_argument
          name: (identifier) @_methods_key
          (#eq? @_methods_key "methods")
          value: (list
            (string) @route.methods
          )
        )?
      )
    )
  )
  definition: (function_definition
    name: (identifier) @route.func_name
  )
) @route.handler

; ── Blueprint declaration ─────────────────────────────────────────────────────

(assignment
  left: (identifier) @blueprint.name
  right: (call
    function: (identifier) @_bp
    (#eq? @_bp "Blueprint")
    arguments: (argument_list
      (string) @blueprint.import_name
      _
      (keyword_argument
        name: (identifier) @_upk
        (#eq? @_upk "url_prefix")
        value: (string) @blueprint.url_prefix
      )?
    )
  )
) @blueprint.decl

; ── app.register_blueprint(bp, url_prefix="/api") ────────────────────────────

(call
  function: (attribute
    object: (identifier) @_app
    attribute: (identifier) @_reg
    (#eq? @_reg "register_blueprint")
  )
  arguments: (argument_list
    (identifier) @app.register_bp
    (keyword_argument
      name: (identifier) @_upk
      (#eq? @_upk "url_prefix")
      value: (string) @app.register_prefix
    )?
  )
) @app.register

; ── SQLAlchemy / Flask-SQLAlchemy model ───────────────────────────────────────

(class_definition
  name: (identifier) @entity.class_name
  superclasses: (argument_list
    [
      (attribute
        attribute: (identifier) @_m
        (#match? @_m "^(Model|Base)$")
      )
      (identifier) @_m
      (#match? @_m "^(Model|Base)$")
    ]
  )
) @entity.class

; SQLAlchemy Column fields
(assignment
  left: (identifier) @entity.field_name
  right: (call
    function: [
      (identifier) @entity.field_type
      (attribute attribute: (identifier) @entity.field_type)
    ]
    (#match? @entity.field_type "^(Column|relationship|backref)$")
  )
) @entity.field

; ── imports ───────────────────────────────────────────────────────────────────

(import_from_statement
  module_name: _ @import.path
) @import.from

(import_statement
  name: _ @import.path
) @import.plain
