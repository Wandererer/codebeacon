; ── Svelte / SvelteKit (script section only) ──────────────────────────────────
; Grammar: tree-sitter-typescript (applied to extracted <script> section)
;
; Usage note:
;   .svelte files use SFC section extraction (same as Vue).
;   This .scm file applies to the extracted <script> section.
;
; Svelte 5 runes: $state(), $derived(), $effect() — captured as call_expression
; Svelte 4: export let prop — explicit prop declarations
; SvelteKit routes: file-system (src/routes/**/+page.svelte) → detector.py
; SvelteKit load: +page.ts export function load() { } — separate file
;
; Captures:
;   @component.name     - component name (derived from filename in routes.py)
;   @prop.name          - export let propName (Svelte 4)
;   @store.name         - writable/readable/derived store
;   @rune.name          - Svelte 5: $state/$derived/$effect call
;   @load.func          - SvelteKit load function name
;   @import.path        - import source

; ── export let prop (Svelte 4 props) ─────────────────────────────────────────

(export_statement
  (lexical_declaration
    (variable_declarator
      name: (identifier) @prop.name
    )
  )
) @prop.exported_let

; ── Svelte 5 runes ────────────────────────────────────────────────────────────

(variable_declarator
  name: (identifier) @_var
  value: (call_expression
    function: (identifier) @rune.name
    (#match? @rune.name "^\\$(state|derived|effect|props|bindable|inspect|host)$")
  )
) @rune.usage

; ── Svelte stores ─────────────────────────────────────────────────────────────

(variable_declarator
  name: (identifier) @store.name
  value: (call_expression
    function: (identifier) @_store_fn
    (#match? @_store_fn "^(writable|readable|derived|get)$")
  )
) @store.decl

; ── SvelteKit load function ───────────────────────────────────────────────────

(export_statement
  (function_declaration
    name: (identifier) @load.func
    (#match? @load.func "^(load|GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|fallback)$")
  )
) @load.export

; ── Component function / class (less common in Svelte but possible) ──────────

(export_statement
  (function_declaration
    name: (identifier) @component.name
    (#match? @component.name "^[A-Z]")
  )
) @component.func

; ── imports ───────────────────────────────────────────────────────────────────

(import_statement
  source: (string) @import.path
) @import.decl
