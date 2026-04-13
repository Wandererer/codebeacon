; ── Angular (TypeScript) ─────────────────────────────────────────────────────
; Grammar: tree-sitter-typescript
;
; TypeScript decorator note:
;   - decorator: @Component({...})
;   - call_expression: Component({...}) inside decorator
;   - object: { selector: "...", templateUrl: "..." }
;   - property_identifier: key names
;
; Angular-specific:
;   - @Component({ selector, templateUrl/template, styleUrls })
;   - @Injectable({ providedIn: "root" })
;   - @NgModule({ declarations, imports, providers, bootstrap })
;   - RouterModule.forRoot(routes) / RouterModule.forChild(routes)
;   - constructor(private service: ServiceType) → DI
;
; Captures:
;   @component.class_name   - @Component class name
;   @component.selector     - selector: "app-root"
;   @component.template_url - templateUrl: "./foo.component.html"
;   @service.class_name     - @Injectable class name
;   @service.inject_type    - constructor injected type
;   @module.class_name      - @NgModule class name
;   @module.providers       - providers array items
;   @route.path             - Routes array { path: "users" }
;   @route.component        - Routes array { component: UserComponent }
;   @route.lazy_load        - loadComponent/loadChildren
;   @import.path            - import source

; ── @Component({...}) class ───────────────────────────────────────────────────

(class_declaration
  (decorator
    (call_expression
      function: (identifier) @_comp (#eq? @_comp "Component")
      arguments: (arguments
        (object
          (pair
            key: (property_identifier) @_sel (#eq? @_sel "selector")
            value: (string
              (string_fragment) @component.selector
            )
          )
        )
      )
    )
  )
  name: (type_identifier) @component.class_name
) @component.class

; templateUrl capture
(decorator
  (call_expression
    function: (identifier) @_comp2 (#eq? @_comp2 "Component")
    arguments: (arguments
      (object
        (pair
          key: (property_identifier) @_turl
          (#eq? @_turl "templateUrl")
          value: (string
            (string_fragment) @component.template_url
          )
        )
      )
    )
  )
) @component.template_url_decorator

; ── @Injectable({ providedIn: "root" }) class ────────────────────────────────

(class_declaration
  (decorator
    (call_expression
      function: (identifier) @_inj (#eq? @_inj "Injectable")
    )
  )
  name: (type_identifier) @service.class_name
) @service.injectable

; Constructor DI
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

; ── @NgModule({...}) class ────────────────────────────────────────────────────

(class_declaration
  (decorator
    (call_expression
      function: (identifier) @_mod (#eq? @_mod "NgModule")
      arguments: (arguments
        (object
          (pair
            key: (property_identifier) @_providers (#eq? @_providers "providers")
            value: (array
              (identifier) @module.providers
            )
          )
        )
      )
    )
  )
  name: (type_identifier) @module.class_name
) @module.ngmodule

; ── Angular Router routes array ───────────────────────────────────────────────

; Routes array: { path: "users", component: UserListComponent }
(array
  (object
    (pair
      key: (property_identifier) @_path (#eq? @_path "path")
      value: (string
        (string_fragment) @route.path
      )
    )
  )
) @route.routes

; component reference in route
(object
  (pair
    key: (property_identifier) @_path2 (#eq? @_path2 "path")
    value: (string (string_fragment) @route.path)
  )
  (pair
    key: (property_identifier) @_comp3
    (#match? @_comp3 "^(component|redirectTo)$")
    value: (identifier) @route.component
  )
) @route.route_entry

; Lazy loading: loadComponent: () => import("./foo").then(m => m.FooComponent)
(object
  (pair
    key: (property_identifier) @_ll
    (#match? @_ll "^(loadComponent|loadChildren)$")
    value: _ @route.lazy_load
  )
) @route.lazy

; ── imports ───────────────────────────────────────────────────────────────────

(import_statement
  source: (string) @import.path
) @import.decl
