; ── React / Next.js (TSX / TypeScript) ───────────────────────────────────────
; Grammar: tree-sitter-typescript (for .ts) / tree-sitter-tsx (for .tsx)
;
; Component detection heuristic:
;   - Exported function/arrow-function whose name starts with uppercase
;   - Function returning JSX (jsx_element, jsx_self_closing_element) — TSX grammar
;   - React.memo(Component), React.forwardRef(Component) wrappers
;
; Next.js routes: handled by convention in detector.py (file path → route).
; This file captures component names and hooks for the graph.
;
; Captures:
;   @component.func_name  - exported function component name
;   @component.arrow_name - arrow function component name (const Foo = ...)
;   @component.memo_name  - React.memo(Component) → inner component
;   @hook.name            - used hooks (useState, useEffect, custom useX)
;   @prop.name            - prop destructuring pattern names
;   @route.pages_path     - file-system route (extracted from filename in routes.py)
;   @server.directive     - "use server" / "use client" directive
;   @import.path          - import source

; ── Exported function component ───────────────────────────────────────────────

(export_statement
  (function_declaration
    name: (identifier) @component.func_name
  )
) @component.export_func

(export_statement
  (function_declaration
    name: (identifier) @component.func_name
    (#match? @component.func_name "^[A-Z]")
  )
) @component.export_func_upper

; export default function Component
(export_statement
  "default"
  (function_declaration
    name: (identifier) @component.func_name
  )
) @component.export_default_func

; ── Arrow function component: export const Foo = (...) => ────────────────────

(export_statement
  (lexical_declaration
    (variable_declarator
      name: (identifier) @component.arrow_name
      (#match? @component.arrow_name "^[A-Z]")
      value: (arrow_function)
    )
  )
) @component.export_arrow

; Non-exported: const Foo = () => (used as sub-component)
(lexical_declaration
  (variable_declarator
    name: (identifier) @component.arrow_name
    (#match? @component.arrow_name "^[A-Z]")
    value: (arrow_function)
  )
) @component.local_arrow

; ── React.memo / React.forwardRef ────────────────────────────────────────────

(export_statement
  (lexical_declaration
    (variable_declarator
      name: (identifier) @component.memo_name
      value: (call_expression
        function: (member_expression
          object: (identifier) @_react (#eq? @_react "React")
          property: (property_identifier) @_hoc
          (#match? @_hoc "^(memo|forwardRef|lazy)$")
        )
      )
    )
  )
) @component.hoc

; Non-exported: const Foo = React.forwardRef(...) / React.memo(...)
; Covers shadcn/ui style: const Card = React.forwardRef<HTMLDivElement, ...>(...)
(lexical_declaration
  (variable_declarator
    name: (identifier) @component.memo_name
    (#match? @component.memo_name "^[A-Z]")
    value: (call_expression
      function: (member_expression
        object: (identifier) @_react_l (#eq? @_react_l "React")
        property: (property_identifier) @_hoc_l
        (#match? @_hoc_l "^(memo|forwardRef|lazy)$")
      )
    )
  )
) @component.hoc_local

; ── Hook usage ────────────────────────────────────────────────────────────────

(call_expression
  function: (identifier) @hook.name
  (#match? @hook.name "^use[A-Z]")
) @hook.call

(call_expression
  function: (member_expression
    object: (identifier) @_react (#eq? @_react "React")
    property: (property_identifier) @hook.name
    (#match? @hook.name "^use[A-Z]")
  )
) @hook.react_call

; ── "use client" / "use server" directive (Next.js App Router) ───────────────

(expression_statement
  (string
    (string_fragment) @server.directive
    (#match? @server.directive "^use (client|server)$")
  )
) @server.directive_stmt

; ── imports ───────────────────────────────────────────────────────────────────

(import_statement
  source: (string) @import.path
) @import.decl
