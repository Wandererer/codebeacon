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
;   @export.name          - exported const/let/var symbol of any case
;   @export.owner/.member - exported object literal + its callable members
;   @export.spec          - `export { x, y as z }` specifier (non re-export)
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

; ── Bare-imported HOC: import { forwardRef, memo } from 'react' ───────────────
; const Button = forwardRef((props, ref) => ...) — callee is a bare identifier,
; not a React.* member_expression, so the patterns above miss it (graphify #1322).

(export_statement
  (lexical_declaration
    (variable_declarator
      name: (identifier) @component.memo_name
      value: (call_expression
        function: (identifier) @_hoc_bare
        (#match? @_hoc_bare "^(memo|forwardRef|lazy)$")
      )
    )
  )
) @component.hoc_bare_export

(lexical_declaration
  (variable_declarator
    name: (identifier) @component.memo_name
    (#match? @component.memo_name "^[A-Z]")
    value: (call_expression
      function: (identifier) @_hoc_bare_l
      (#match? @_hoc_bare_l "^(memo|forwardRef|lazy)$")
    )
  )
) @component.hoc_bare_local

; ── Function-expression component: const Foo = function () { return <jsx/> } ──
; (arrow patterns above only match value: (arrow_function); graphify #1322)

(export_statement
  (lexical_declaration
    (variable_declarator
      name: (identifier) @component.arrow_name
      (#match? @component.arrow_name "^[A-Z]")
      value: (function_expression)
    )
  )
) @component.export_fnexpr

(lexical_declaration
  (variable_declarator
    name: (identifier) @component.arrow_name
    (#match? @component.arrow_name "^[A-Z]")
    value: (function_expression)
  )
) @component.local_fnexpr

; ── Non-exported function-declaration component: function Foo () { ... } ──────
; The function_declaration patterns above are all export_statement-wrapped, so a
; local (non-exported) uppercase function component was never captured.

(function_declaration
  name: (identifier) @component.func_name
  (#match? @component.func_name "^[A-Z]")
) @component.local_func

; ── Exported module symbols (any case) ────────────────────────────────────────
; Every pattern above gates the name on ^[A-Z], so a module whose exports are
; hooks, stores, utils or constants produced ZERO nodes — `export const
; useAuthStore = create(...)`, `export const DEMO_MODE = true`, `export const
; authUtils = {...}` were all invisible, and an importer of such a file had
; nothing to bind to (graphify #2110 / #931-5: 46.9% of internal import edges in
; a real Next.js app pointed at a file codebeacon rendered as empty).
;
; The ungated `export_statement (function_declaration …)` pattern at the top of
; this file is the precedent: an exported lowercase `function formatDate()` has
; always been noded. These patterns extend that to the other export spellings.
; Only EXPORTED declarations are ungated — a file-local lowercase const is an
; implementation detail, not module surface, and noding those would bury the
; graph in noise.
;
; Grammar note: lexical_declaration (const/let) and variable_declaration (var)
; are separate node types; both exist in the JS, TS and TSX grammars, as do
; object / pair / method_definition / export_clause / export_specifier, so these
; patterns compile against all three (react.scm is allowlisted for all three).

(export_statement
  [
    (lexical_declaration
      (variable_declarator
        name: (identifier) @export.name
      )
    )
    (variable_declaration
      (variable_declarator
        name: (identifier) @export.name
      )
    )
  ]
) @export.decl

; ── Object-literal API surface: export const repo = { find() {}, … } ─────────
; Only CALLABLE members are noded (methods, arrow/function-expression values):
; those are the module's API surface. Data pairs (`{ url: "…", timeout: 30 }`)
; are configuration, not symbols, and noding them buries the graph in noise.
; The container const is still noded by @export.decl above — emitting the
; members must not replace it (upstream's early-return trap).

(export_statement
  (lexical_declaration
    (variable_declarator
      name: (identifier) @export.owner
      value: (object
        [
          (method_definition
            name: (property_identifier) @export.member
          )
          (pair
            key: (property_identifier) @export.member
            value: [(arrow_function) (function_expression)]
          )
        ]
      )
    )
  )
) @export.object

; ── Deferred export clause: const x = …; export { x, y as z } ────────────────
; The declare-then-export-at-the-bottom idiom (very common in hook/util modules)
; leaves the declaration itself unexported, so the patterns above never see it.
; The interpreter drops re-exports (`export { X } from './m'` — those symbols
; belong to the other file, and dependencies.py already emits a re_exports edge)
; and TypeScript type-only exports.

(export_statement
  (export_clause
    (export_specifier) @export.spec
  )
) @export.clause

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
