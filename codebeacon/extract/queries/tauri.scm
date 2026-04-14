; ── Tauri v2 (Rust) ──────────────────────────────────────────────────────────
; Grammar: tree-sitter-rust
;
; In tree-sitter-rust, outer attributes (#[...]) are SIBLINGS of the
; declaration they annotate, not children.  The interpreter correlates
; attribute_item + function_item/struct_item by source-file position.
;
; Captures:
;   @route.tauri_attr      - #[tauri::command] attribute_item
;   @route.func            - function_item following a command attribute
;   @route.func_name       - command function name
;   @service.struct_name   - struct name (managed state)
;   @service.struct        - struct_item node
;   @entity.derive_attr    - #[derive(...)] attribute_item
;   @entity.derive_args    - token_tree inside derive(...)
;   @entity.struct         - struct_item node
;   @entity.struct_name    - struct name
;   @entity.field_name     - struct field name
;   @entity.field_type     - struct field type
;   @import.path           - use declaration path

; ── #[tauri::command] attribute (matched separately; interpreter pairs with next fn) ─

(attribute_item
  (attribute
    (scoped_identifier
      path: (identifier) @_ns (#eq? @_ns "tauri")
      name: (identifier) @_cmd (#eq? @_cmd "command")))) @route.tauri_attr

; ── All function_item nodes (interpreter picks ones preceded by command attr) ─

(function_item
  name: (identifier) @route.func_name) @route.func

; ── #[derive(...)] attribute (interpreter checks for Serialize/Deserialize) ──

(attribute_item
  (attribute
    (identifier) @_derive (#eq? @_derive "derive")
    arguments: (token_tree) @entity.derive_args)) @entity.derive_attr

; ── Struct definitions ───────────────────────────────────────────────────────

(struct_item
  name: (type_identifier) @entity.struct_name) @entity.struct

; ── Struct fields ────────────────────────────────────────────────────────────

(field_declaration
  name: (field_identifier) @entity.field_name
  type: (_) @entity.field_type) @entity.field

; ── Imports ──────────────────────────────────────────────────────────────────

(use_declaration
  argument: (scoped_identifier) @import.path) @import.decl

(use_declaration
  argument: (scoped_use_list) @import.path) @import.use_list

(use_declaration
  argument: (identifier) @import.path) @import.simple
