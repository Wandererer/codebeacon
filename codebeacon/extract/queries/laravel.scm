; ── Laravel (PHP) ─────────────────────────────────────────────────────────────
; Grammar: tree-sitter-php
;
; PHP grammar note:
;   - scoped_call_expression: Route::get(...)  (static method call)
;   - member_call_expression: Route::prefix("api")->group(...)
;   - class_constant_access_expression: UserController::class
;   - encapsed_string: PHP double-quoted string
;   - name nodes: identifiers in PHP
;
; Special handling in extract/routes.py:
;   - Route::resource("users", ...) → 7 CRUD routes expanded
;   - Route::prefix("api")->group(fn) → prefix propagation
;
; Captures:
;   @route.method         - get/post/put/patch/delete/any
;   @route.path           - path string content
;   @route.controller     - ControllerClass::class → class name
;   @route.resource_name  - Route::resource("users") → "users"
;   @route.prefix         - Route::prefix("api") value
;   @entity.class_name    - Eloquent Model subclass
;   @entity.relation_type - hasMany/belongsTo/hasOne etc.
;   @entity.relation_model - target model class
;   @service.class_name   - service/provider class
;   @di.interface         - $this->app->bind(Interface::class, ...)
;   @di.implementation    - bind target class
;   @import.path          - use Namespace\Class

; ── Route::get("/path", [Controller::class, "method"]) ───────────────────────

(expression_statement
  (scoped_call_expression
    name: (name) @_class (#eq? @_class "Route")
    (name) @route.method
    (#match? @route.method "^(get|post|put|patch|delete|options|any|match)$")
    (arguments
      (argument
        [
          (encapsed_string (string_content) @route.path)
          (string (string_content) @route.path)
        ]
      )
      (argument
        [
          (array_creation_expression
            (array_element_initializer
              (class_constant_access_expression
                (name) @route.controller
                (name) @_class_kw (#eq? @_class_kw "class")
              )
            )
          )
          (string (string_content) @route.closure_action)
        ]
      )?
    )
  )
) @route.call

; ── Route::resource("users", UserController::class) ──────────────────────────

(expression_statement
  (scoped_call_expression
    name: (name) @_class (#eq? @_class "Route")
    (name) @_res (#match? @_res "^(resource|apiResource|resources|apiResources)$")
    (arguments
      (argument
        [
          (encapsed_string (string_content) @route.resource_name)
          (string (string_content) @route.resource_name)
        ]
      )
      (argument
        (class_constant_access_expression
          (name) @route.resource_controller
          (name) @_ck (#eq? @_ck "class")
        )
      )
    )
  )
) @route.resource

; ── Route::prefix("api")->group(...) ─────────────────────────────────────────

(expression_statement
  (member_call_expression
    object: (scoped_call_expression
      name: (name) @_class (#eq? @_class "Route")
      (name) @_prefix (#eq? @_prefix "prefix")
      (arguments
        (argument
          [
            (encapsed_string (string_content) @route.prefix)
            (string (string_content) @route.prefix)
          ]
        )
      )
    )
    name: (name) @_group (#eq? @_group "group")
  )
) @route.prefix_group

; ── Route::middleware(...)->prefix(...)->group(...) chains ────────────────────
; Covered by member_call_expression nesting — prefix propagation in routes.py

; ── Eloquent Model subclass ───────────────────────────────────────────────────

(class_declaration
  name: (name) @entity.class_name
  (base_clause
    (qualified_name (name) @_base (#match? @_base "^(Model|Authenticatable)$"))
  )
) @entity.model

; Eloquent relations
(method_declaration
  name: (name) @entity.relation_type
  (#match? @entity.relation_type "^(hasMany|hasOne|belongsTo|belongsToMany|hasManyThrough|hasOneThrough|morphTo|morphMany|morphOne)$")
  (compound_statement
    (return_statement
      (member_call_expression
        name: (name) @_rel_fn
        (arguments
          (argument
            (class_constant_access_expression
              (name) @entity.relation_model
              (name) @_ck (#eq? @_ck "class")
            )
          )
        )
      )
    )
  )
) @entity.relation

; ── Service provider bindings ─────────────────────────────────────────────────

(member_call_expression
  object: (member_access_expression
    object: (variable_name (name) @_this (#eq? @_this "this"))
    name: (name) @_app (#eq? @_app "app")
  )
  name: (name) @_bind (#match? @_bind "^(bind|singleton|scoped|transient)$")
  (arguments
    (argument
      (class_constant_access_expression
        (name) @di.interface
        (name) @_ck (#eq? @_ck "class")
      )
    )
    (argument
      (class_constant_access_expression
        (name) @di.implementation
        (name) @_ck2 (#eq? @_ck2 "class")
      )
    )
  )
) @di.binding

; ── Plain service class ───────────────────────────────────────────────────────

(class_declaration
  name: (name) @service.class_name
) @service.class

; ── use statements ────────────────────────────────────────────────────────────

(namespace_use_declaration
  (namespace_use_clause
    (qualified_name) @import.path
  )
) @import.use
