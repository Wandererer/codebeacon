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

; tree-sitter-c-sharp: invocation_expression uses fields `function:` and
; `arguments:`; the callee member_access_expression uses `name:`. The query
; previously used `expression:` and a positional argument_list → impossible
; pattern → the whole aspnet query failed to compile.
(expression_statement
  (invocation_expression
    function: (member_access_expression
      name: (identifier) @route.map_method
      (#match? @route.map_method "^(MapGet|MapPost|MapPut|MapPatch|MapDelete|MapMethods|Map)$")
    )
    arguments: (argument_list
      (argument
        (string_literal
          (string_literal_content) @route.map_path
        )
      )
    )
  )
) @route.minimal_api

; ── Service classes ───────────────────────────────────────────────────────────
;
; EVERY class is a node. The only service pattern used to require a base_list,
; so a class that implements nothing — BaseService, Startup, a C# 12
; primary-constructor service, either half of a partial class — never entered
; the graph at all. That was the precondition blocking everything below: DI
; cannot resolve onto a node that does not exist. Matches the treatment
; laravel.scm and rails.scm already give their languages.

(class_declaration
  name: (identifier) @service.class_name
) @service.class

; Base-list entries, one match each — `class A : BaseA, IFoo, IBar` yields
; three. Capturing only the first entry (and calling it an interface) both lost
; the rest and mislabelled a base CLASS as an implemented interface;
; services.py classifies each entry instead.
(class_declaration
  name: (identifier) @service.base_class_name
  (base_list
    [
      (identifier) @service.base
      (qualified_name name: (identifier) @service.base)
      (generic_name (identifier) @service.base)
    ]
  )
) @service.class_with_base

; ── DI — constructor injection ────────────────────────────────────────────────
; Mirrors spring_boot.scm's di.constructor. ASP.NET Core's primary DI mechanism
; had NO pattern at all: a textbook `public UserService(IRepo repo)` yielded an
; empty dependency list.

(constructor_declaration
  parameters: (parameter_list
    (parameter
      type: _ @di.ctor_param_type
      name: (identifier) @di.ctor_param_name
    )
  )
) @di.constructor

; C# 12 primary constructor: `public class OrderService(IRepo repo)`. The
; parameter_list is a direct child of the class_declaration, so this cannot
; reach a nested method's parameters.
(class_declaration
  name: (identifier) @service.class_name
  (parameter_list
    (parameter
      type: _ @di.ctor_param_type
      name: (identifier) @di.ctor_param_name
    )
  )
) @di.primary_constructor

; ── DI registration: builder.Services.AddScoped<IFoo, FooImpl>() ─────────────

(invocation_expression
  function: (member_access_expression
    name: (identifier) @_scope
    (#match? @_scope "^(AddScoped|AddSingleton|AddTransient|AddHostedService)$")
  )
  arguments: (argument_list)
) @di.registration

; Generic DI: builder.Services.AddScoped<IFoo, FooImpl>() — the AddScoped<...>
; is a generic_name in the `name:` field of the callee member_access_expression.
; Both type arguments accept a namespace-qualified name (Abc.IMailer) and a
; generic one (IRepo<User>); an identifier-only list captured neither, so those
; registrations were silently unregistered. Single-argument self-registrations
; (AddSingleton<IRepo>()) are deliberately not matched: they name no
; implementation, so there is no interface→impl edge to record.
(invocation_expression
  function: (member_access_expression
    name: (generic_name
      (identifier) @_scope
      (#match? @_scope "^(AddScoped|AddSingleton|AddTransient)$")
      (type_argument_list
        [
          (identifier)
          (qualified_name)
          (generic_name)
        ] @di.service_type
        [
          (identifier)
          (qualified_name)
          (generic_name)
        ] @di.impl_type
      )
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
