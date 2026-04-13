# Translation Status

This file tracks the sync state of each translated README against the source `README.md`.

To check what changed since a translation was last synced:
```bash
git log --oneline -- README.md          # find commits that touched the source
git diff <based-on-commit>..HEAD -- README.md   # see what changed
```

| Language | File | Based on commit | Date | Maintainer |
|----------|------|-----------------|------|------------|
| English (source) | README.md | — | 2026-04-13 | @wanderer |
| 한국어 | README.ko.md | `initial` | 2026-04-13 | @wanderer |
| 日本語 | README.ja.md | `initial` | 2026-04-13 | — |
| 简体中文 | README.zh-CN.md | `initial` | 2026-04-13 | — |
| Español | README.es.md | `initial` | 2026-04-13 | — |
| Français | README.fr.md | `initial` | 2026-04-13 | — |
| Deutsch | README.de.md | `initial` | 2026-04-13 | — |
| Português (BR) | README.pt-BR.md | `initial` | 2026-04-13 | — |

## Translation rules

- Code blocks, CLI commands, file paths, and technical terms (`tree-sitter`, `NetworkX`, `Leiden`, `CLAUDE.md`, etc.) are **not translated**
- Table structure is identical across all languages; only prose cells are translated
- Badge URLs are identical in all files
- Each translated file starts with `<!-- translation-of: README.md | based-on-commit: <hash> -->`

## Updating a translation

1. Update the translation file
2. Update the `based-on-commit` header in the file
3. Update the date and commit hash in this table
4. Open a PR — tag it `translation`

## Becoming a maintainer

If you'd like to maintain a translation, open an issue or PR. Maintainers are credited in this table and in the repository's contributors list.
