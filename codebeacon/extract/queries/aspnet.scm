; ── ASP.NET Core (C#) ─────────────────────────────────────────────────────────
; Grammar: tree-sitter-c-sharp
;
; C# grammar note:
;   - attribute_list: [HttpGet("{id}")] — wraps attribute nodes
;   - attribute: HttpGet("{id}") — name + attribute_argument_list
;   - identifier: attribute/class/method names
;   - string_literal_content: content inside string_literal
;
; Special handling in extract/routes.py:
;   - [Route("api/[controller]")] → replace [controller] with class name minus "Controller"
;   - Minimal API: app.MapGet("/users", handler)
;
; Captures:
;   @route.class_attr       - [Route("api/[controller]")] on class → path template
;   @route.class_name       - controller class name
;   @route.method_attr      - [HttpGet] / [HttpPost] etc. attribute name
;   @route.method_path      - path in [HttpGet("{id}")]
;   @route.method_name      - action method name
;   @route.map_method       - MapGet/MapPost etc. (minimal API)
;   @route.map_path         - path string (minimal API)
;   @service.class_name     - service class name
;   @service.interface      - implemented interface
;   @di.service_type        - AddScoped<IService, ServiceImpl> → interface type
;   @di.impl_type           - implementation type
;   @entity.class_name      - EF Core entity class (DbSet target)
;   @entity.dbset_name      - DbSet<User> property name
;   @import.path            - using namespace

; ── Controller class with [Route(...)] ───────────────────────────────────────

(class_declaration
  (attribute_list
    (attribute
      name: (identifier) @_route (#eq? @_route "Route")
      (attribute_argument_list
        (attribute_argument
          (string_literal
            (string_literal_content) @route.class_attr
          )
        )
      )
    )
  )
  name: (identifier) @route.class_name
) @route.controller_class

; Controller class without route (uses [ApiController] convention)
(class_declaration
  (attribute_list
    (attribute
      name: (identifier) @_api
      (#match? @_api "^(ApiController|Controller)$")
    )
  )
  name: (identifier) @route.class_name
) @route.controller_bare

; ── Method route attributes ───────────────────────────────────────────────────

; [HttpGet("{id}")] — with path
(method_declaration
  (attribute_list
    (attribute
      name: (identifier) @route.method_attr
      (#match? @route.method_attr "^(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete|HttpOptions|HttpHead|Route)$")
      (attribute_argument_list
        (attribute_argument
          (string_literal
            (string_literal_content) @route.method_path
          )
        )
      )
    )
  )
  name: (identifier) @route.method_name
) @route.method_with_path

; [HttpPost] — without path
(method_declaration
  (attribute_list
    (attribute
      name: (identifier) @route.method_attr
      (#match? @route.method_attr "^(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete|HttpOptions|HttpHead)$")
    )
  )
  name: (identifier) @route.method_name
) @route.method_bare

; ── Minimal API: app.MapGet("/users", handler) ───────────────────────────────

(expression_statement
  (invocation_expression
    expression: (member_access_expression
      name: (identifier) @route.map_method
      (#match? @route.map_method "^(MapGet|MapPost|MapPut|MapPatch|MapDelete|MapMethods|Map)$")
    )
    (argument_list
      (argument
        (string_literal
          (string_literal_content) @route.map_path
        )
      )
    )
  )
) @route.minimal_api

; ── Service class implementing interface ──────────────────────────────────────

(class_declaration
  name: (identifier) @service.class_name
  (base_list
    (identifier) @service.interface
  )
) @service.class

; ── DI registration: builder.Services.AddScoped<IFoo, FooImpl>() ─────────────

(invocation_expression
  expression: (member_access_expression
    name: (identifier) @_scope
    (#match? @_scope "^(AddScoped|AddSingleton|AddTransient|AddHostedService)$")
  )
  (argument_list)
) @di.registration

; Generic DI: AddScoped<IFoo, FooImpl>()
(invocation_expression
  expression: (generic_name
    (identifier) @_scope
    (#match? @_scope "^(AddScoped|AddSingleton|AddTransient)$")
    (type_argument_list
      (identifier) @di.service_type
      (identifier) @di.impl_type
    )
  )
) @di.generic_registration

; ── EF Core DbContext ─────────────────────────────────────────────────────────

(property_declaration
  type: (generic_name
    (identifier) @_dbset (#eq? @_dbset "DbSet")
    (type_argument_list
      (identifier) @entity.class_name
    )
  )
  name: (identifier) @entity.dbset_name
) @entity.dbset

; ── using directives ─────────────────────────────────────────────────────────

(using_directive
  (qualified_name) @import.path
) @import.using

(using_directive
  (identifier) @import.path
) @import.using_simple
