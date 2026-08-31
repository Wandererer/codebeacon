; ── Rails (Ruby) ──────────────────────────────────────────────────────────────
; Grammar: tree-sitter-ruby
;
; Special handling note:
;   - `resources :users` → 7 CRUD routes expanded by extract/routes.py
;   - `db/schema.rb` parsed separately for table columns
;   - `routes.rb` is dispatched to this query by the extractor
;
; Captures:
;   @route.resources_name   - resources :users name
;   @route.http_method      - get/post/put/patch/delete
;   @route.path             - path string
;   @route.to               - "controller#action" string
;   @route.namespace        - namespace/scope block
;   @route.member_action    - member/collection route method
;   @entity.class_name      - ApplicationRecord subclass
;   @entity.relation_type   - has_many/belongs_to/has_one/has_and_belongs_to_many
;   @entity.relation_target - relation target name (symbol)
;   @service.class_name     - plain Ruby service class
;   @import.path            - require path

; ── resources :model_name ────────────────────────────────────────────────────

(call
  method: (identifier) @_res
  (#match? @_res "^(resources|resource)$")
  arguments: (argument_list
    (simple_symbol) @route.resources_name
  )
) @route.resources

; resources :users, only: [:index, :show]
(call
  method: (identifier) @_res
  (#match? @_res "^(resources|resource)$")
  arguments: (argument_list
    (simple_symbol) @route.resources_name
    (pair
      key: (hash_key_symbol) @_only
      (#match? @_only "^(only|except)$")
      value: (array
        (simple_symbol) @route.resources_filter
      )
    )
  )
) @route.resources_filtered

; ── get/post/put/patch/delete "path", to: "ctrl#action" ──────────────────────

(call
  method: (identifier) @route.http_method
  (#match? @route.http_method "^(get|post|put|patch|delete|match|root)$")
  arguments: (argument_list
    (string) @route.path
    (pair
      key: (hash_key_symbol) @_to
      (#eq? @_to "to")
      value: (string) @route.to
    )?
  )
) @route.explicit

; ── namespace/scope blocks ────────────────────────────────────────────────────

(call
  method: (identifier) @route.namespace
  (#match? @route.namespace "^(namespace|scope|constraints|concern)$")
  arguments: (argument_list
    (string)? @route.namespace_path
    (simple_symbol)? @route.namespace_path
  )
  block: _
) @route.namespace_block

; ── ApplicationRecord / ActiveRecord model ────────────────────────────────────
;
; Two SEPARATE patterns, not one alternation. Both bases were previously listed
; as branches of a single `[...]` alternation carrying both predicates, and
; tree-sitter applies a pattern's predicates to the whole pattern: the
; bare-constant branch then had to satisfy `#eq? "Base"` as well, which is
; impossible, so `class Post < ApplicationRecord` — the canonical Rails model —
; matched NOTHING and no Rails app ever produced an entity from it.
;
; The scope_resolution branch is also anchored on its scope. Matching the tail
; constant alone promoted any `class Report < Reporting::Base` to an
; ActiveRecord model purely because the superclass path ends in `Base`, the
; same tail-name over-match laravel.scm's Eloquent allowlist already guards
; against.

; class Post < ApplicationRecord
(class
  name: (constant) @entity.class_name
  superclass: (superclass
    (constant) @_base
    (#match? @_base "^(ApplicationRecord|ActiveRecord)$")
  )
) @entity.model

; class Widget < ActiveRecord::Base
(class
  name: (constant) @entity.class_name
  superclass: (superclass
    (scope_resolution
      scope: (constant) @_scope
      (#eq? @_scope "ActiveRecord")
      name: (constant) @_base
      (#eq? @_base "Base")
    )
  )
) @entity.model

; Associations
(call
  method: (identifier) @entity.relation_type
  (#match? @entity.relation_type "^(has_many|has_one|belongs_to|has_and_belongs_to_many)$")
  arguments: (argument_list
    (simple_symbol) @entity.relation_target
  )
) @entity.association

; ── Plain service class ───────────────────────────────────────────────────────

(class
  name: (constant) @service.class_name
) @service.class

; ── require ───────────────────────────────────────────────────────────────────

(call
  method: (identifier) @_req
  (#match? @_req "^(require|require_relative)$")
  arguments: (argument_list
    (string) @import.path
  )
) @import.require
