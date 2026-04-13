# codebeacon query files

Each `.scm` file defines tree-sitter queries for one framework or language.
Queries are loaded at runtime by `extract/base.py → load_query_file(grammar)`.

## Adding a new framework

### 1. Identify the grammar

Map the file extension to a tree-sitter grammar in `extract/base.py`:

```python
# EXT_TO_GRAMMAR
".ex": "elixir",

# _GRAMMAR_MODULES
"elixir": "tree_sitter_elixir",
```

If the grammar package exposes a non-standard function (like `language_typescript()`
instead of `language()`), add special handling in `get_language()`.

### 2. Explore the AST

Use the tree-sitter playground or this snippet to understand node types:

```python
from codebeacon.extract.base import parse_source, node_text

src = b'your framework code here'
root, lang = parse_source(src, 'your_grammar')

def walk(n, d=0):
    print(' '*d + n.type + ' ' + repr(node_text(n)[:40]))
    for c in n.named_children: walk(c, d+2)
walk(root)
```

### 3. Write the .scm file

Name it after the **grammar** (not the framework):

| Framework   | Grammar    | File            |
|-------------|------------|-----------------|
| Spring Boot | java       | spring_boot.scm |
| NestJS      | typescript | nestjs.scm      |
| Gin/Echo    | go         | gin.scm         |
| Ktor        | kotlin     | ktor.scm        |
| Actix/Axum  | rust       | actix.scm       |

**Capture naming convention:**

| Prefix       | Meaning                              |
|--------------|--------------------------------------|
| `@route.*`   | Route path, method, handler          |
| `@service.*` | Service class, DI relationships      |
| `@entity.*`  | ORM models, fields, relations        |
| `@component.*` | Frontend components, props         |
| `@di.*`      | DI bindings (unresolved refs)        |
| `@module.*`  | Module-level groupings               |
| `@hook.*`    | Hooks / composables usage            |
| `@import.*`  | Import/require statements            |

**Grammar quirks to watch:**

- **Java**: `marker_annotation` (no args) vs `annotation` (with args) — use `[...]` alternation
- **PHP**: `scoped_call_expression` for `Class::method()`, `encapsed_string` for strings
- **Rust**: `attribute_item` wraps `attribute`, proc macro args in `token_tree` (unparsed)
- **Kotlin**: trailing lambdas via `annotated_lambda` / `lambda_literal`
- **Swift**: route paths are multi-argument: `app.get("a", "b")` — join in extractor
- **Vue/Svelte**: SFC files use section extraction; queries apply to `<script>` content only

### 4. Wire up the extractor

Add dispatch in the relevant extractor module:

```python
# extract/routes.py
elif framework == "phoenix":
    return _extract_phoenix_routes(file_path, root, lang)
```

### 5. Add fixtures and tests

```
tests/fixtures/phoenix/
    router.ex
    user_controller.ex

tests/test_routes.py
    def test_phoenix_routes():
        ...
```

## Query file structure

Each file should include:
1. Header comment: framework name, grammar, important AST notes
2. Capture documentation table
3. Grouped sections (routes → services → entities → imports)
4. `; ──` separators between sections

## tree-sitter 0.25 API note

```python
from tree_sitter import Query, QueryCursor

q = Query(language, pattern_string)
cursor = QueryCursor(q)
for pattern_idx, captures in cursor.matches(root_node):
    for capture_name, nodes in captures.items():
        for node in nodes:
            print(capture_name, node.text)
```

`Language.query()` is deprecated in 0.25 — always use `Query(language, pattern)`.
