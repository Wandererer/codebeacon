; ── Django (Python) ───────────────────────────────────────────────────────────
; Grammar: tree-sitter-python
;
; Convention note: Django routes live in urls.py, models in models.py.
; The extractor handles file-name-based dispatch before running these queries.
;
; Captures:
;   @route.path_call    - path("...", view) call
;   @route.path_str     - URL string
;   @route.view_name    - view function/class reference
;   @route.include_path - include("app.urls") string
;   @route.re_path_str  - re_path("regex") string
;   @entity.class_name  - models.Model subclass
;   @entity.field_name  - model field name
;   @entity.field_type  - model field type (e.g. CharField, ForeignKey)
;   @view.class_name    - CBV class name
;   @view.func_name     - FBV function name
;   @import.path        - import path

; ── urlpatterns path() entries ───────────────────────────────────────────────

(assignment
  left: (identifier) @_up
  (#eq? @_up "urlpatterns")
  right: (list
    (call
      function: (identifier) @_path_fn
      (#match? @_path_fn "^(path|re_path)$")
      arguments: (argument_list
        (string) @route.path_str
        [
          (identifier) @route.view_name
          (attribute
            attribute: (identifier) @route.view_name
          )
          (call
            function: (attribute
              attribute: (identifier) @_asv
              (#eq? @_asv "as_view")
            )
          )
        ]
      )
    )
  )
) @route.urlpatterns

; include() inside urlpatterns
(call
  function: (identifier) @_inc
  (#eq? @_inc "include")
  arguments: (argument_list
    (string) @route.include_path
  )
) @route.include

; ── Django model ──────────────────────────────────────────────────────────────

(class_definition
  name: (identifier) @entity.class_name
  superclasses: (argument_list
    [
      (attribute
        attribute: (identifier) @_model
        (#match? @_model "^(Model|AbstractModel|AbstractBaseModel)$")
      )
      (identifier) @_model
      (#match? @_model "^(Model|AbstractModel)$")
    ]
  )
  body: (block
    (expression_statement
      (assignment
        left: (identifier) @entity.field_name
        right: (call
          function: [
            (identifier) @entity.field_type
            (attribute
              attribute: (identifier) @entity.field_type
            )
          ]
          (#match? @entity.field_type "^(CharField|IntegerField|FloatField|BooleanField|DateField|DateTimeField|ForeignKey|OneToOneField|ManyToManyField|TextField|EmailField|URLField|SlugField|UUIDField|FileField|ImageField|JSONField|AutoField|BigAutoField|SmallIntegerField|PositiveIntegerField)$")
        )
      )
    )
  )
) @entity.model

; ── Class-based views ────────────────────────────────────────────────────────

(class_definition
  name: (identifier) @view.class_name
  superclasses: (argument_list
    [
      (identifier) @_view_base
      (attribute attribute: (identifier) @_view_base)
    ]
    (#match? @_view_base "^(View|ListView|DetailView|CreateView|UpdateView|DeleteView|TemplateView|APIView|GenericAPIView|ModelViewSet|ReadOnlyModelViewSet|ViewSet|FormView)$")
  )
) @view.cbv

; ── Function-based views (decorated with @login_required etc.) ───────────────

(decorated_definition
  definition: (function_definition
    name: (identifier) @view.func_name
    parameters: (parameters
      (identifier) @_req
      (#eq? @_req "request")
    )
  )
) @view.fbv_decorated

; ── imports ───────────────────────────────────────────────────────────────────

(import_from_statement
  module_name: _ @import.path
) @import.from

(import_statement
  name: _ @import.path
) @import.plain
