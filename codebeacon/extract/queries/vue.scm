; ── Vue / Nuxt (script section only) ──────────────────────────────────────────
; Grammar: tree-sitter-typescript (applied to extracted <script> section)
;
; Usage note:
;   .vue SFC files are NOT parsed directly. extract/base.py extracts the
;   <script> section text and parses it with TypeScript grammar.
;   This .scm file describes queries for that extracted script section.
;
; Vue 3 Composition API patterns:
;   - defineComponent({ name, setup, components, props })
;   - <script setup> — top-level statements are component options
;   - defineProps<{ name: string }>() / defineProps({ name: String })
;   - defineEmits
;   - const router = useRouter() / const route = useRoute()
;
; Vue Router: const routes = [{ path: "/users", component: UserList }]
; Nuxt: file-system routing handled in detector.py
;
; Captures:
;   @component.name        - defineComponent({ name: "..." }) value
;   @component.class_name  - export default class ComponentName
;   @component.setup_name  - <script setup> — use filename as component name
;   @route.path            - Vue Router route path string
;   @route.component       - Vue Router component identifier
;   @prop.name             - defineProps({ name: ... }) key
;   @composable.name       - used composable (useX function calls)
;   @import.path           - import source

; ── defineComponent({ name: "ComponentName", ... }) ─────────────────────────

(call_expression
  function: (identifier) @_dc
  (#eq? @_dc "defineComponent")
  arguments: (arguments
    (object
      (pair
        key: (property_identifier) @_name_key
        (#eq? @_name_key "name")
        value: (string
          (string_fragment) @component.name
        )
      )
    )
  )
) @component.define

; ── export default class ComponentName ───────────────────────────────────────

(export_statement
  "default"
  (class_declaration
    name: (type_identifier) @component.class_name
  )
) @component.class

(export_statement
  "default"
  (call_expression
    function: (identifier) @_dc2
    (#eq? @_dc2 "defineComponent")
  )
) @component.define_anon

; ── defineProps({ ... }) / defineProps<T>() ──────────────────────────────────

(call_expression
  function: (identifier) @_dp
  (#eq? @_dp "defineProps")
  arguments: (arguments
    (object
      (pair
        key: (property_identifier) @prop.name
      )
    )
  )
) @component.props_object

; ── Vue Router routes array ───────────────────────────────────────────────────

(variable_declarator
  name: (identifier) @_routes
  (#eq? @_routes "routes")
  value: (array
    (object
      (pair
        key: (property_identifier) @_path_key
        (#eq? @_path_key "path")
        value: (string
          (string_fragment) @route.path
        )
      )
    )
  )
) @route.routes_array

; Route component reference
(object
  (pair
    key: (property_identifier) @_path_key2
    (#eq? @_path_key2 "path")
    value: (string
      (string_fragment) @route.path
    )
  )
  (pair
    key: (property_identifier) @_comp_key
    (#match? @_comp_key "^(component|components)$")
    value: (identifier) @route.component
  )
) @route.route_entry

; ── Composable usage (useX) ───────────────────────────────────────────────────

(call_expression
  function: (identifier) @composable.name
  (#match? @composable.name "^use[A-Z]")
) @composable.call

; ── imports ───────────────────────────────────────────────────────────────────

(import_statement
  source: (string) @import.path
) @import.decl
