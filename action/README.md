# codebeacon PR context — GitHub Action

Comment on pull requests with the affected slice of your committed
[codebeacon](https://github.com/codebeacon/codebeacon) knowledge graph. It is an
**architecture-drift check for AI-era code review**: instead of reviewing a diff
in isolation, the comment points at the exact wiki articles the change touches,
the upstream blast radius, and any high-impact hub files the PR edits — so
review stays anchored to the parts of the system that actually move.

## Usage

Add `.github/workflows/pr-context.yml` (see [`examples/pr-context.yml`](examples/pr-context.yml)):

```yaml
name: codebeacon PR context
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
  pull-requests: write        # required to post/update the comment
jobs:
  pr-context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0       # required — full history so the base is diffable
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: codebeacon/codebeacon/action@v1
        with:
          base: ${{ github.base_ref }}
```

## Requires a committed index

This Action does **not** scan your repo — that would be too slow for CI and
would need your full toolchain on the runner. codebeacon's model is that the
knowledge graph is a **git-committable artifact**: you generate it once (and
refresh it as the code evolves) and commit it.

```bash
pip install codebeacon
codebeacon scan .
git add .codebeacon && git commit -m "chore: add codebeacon index"
```

If `.codebeacon/beacon.json` is missing, the Action posts a one-time comment
explaining these steps rather than failing the build.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `base` | `${{ github.base_ref }}` | Git ref to diff the PR against. |
| `beacon-dir` | `.codebeacon` | Path to the committed index directory. |
| `depth` | `3` | Upstream blast-radius walk depth (callers of callers…). |
| `limit` | `50` | Max wiki articles listed in the comment. |
| `comment` | `true` | Post/update a PR comment. Set `false` to only compute. |
| `install` | `pip` | How to install codebeacon: `pip`, or `skip` if pre-installed. |
| `fail-on-error` | `false` | Fail the job on internal errors. A context commenter should not break a build, so this defaults off. |

## What the comment looks like

```markdown
<!-- codebeacon-pr-context -->

## 🔦 codebeacon — PR context

Architecture-drift check: the knowledge-graph slice this PR touches, so
review stays anchored to the parts of the system that actually move.

**4** changed file(s) → **2** matched node(s) → **7** upstream node(s) in the
blast radius (depth 3).

### ⚠️ Structure signals

This PR changes high-impact hub file(s) — widely imported, so the change
ripples across the codebase. Worth extra review care:

- `codebeacon/common/safety.py` — imported by 9 file(s)

### Affected wiki articles (3)

Read these first — they document the affected slice:

- `.codebeacon/wiki/codebeacon/services/AffectedPaths.md`
- `.codebeacon/wiki/codebeacon/services/Cli.md`
- ...
```

## Update-in-place, not duplicate

The comment body begins with the marker `<!-- codebeacon-pr-context -->`. On
each push the Action lists the PR's comments, finds the one carrying that
marker, and **PATCHes it** — so a busy PR gets one always-current comment
instead of a growing stack. If no marked comment exists yet, it creates one.

## Behaviour on edge cases

| Situation | Behaviour |
| --- | --- |
| No changed files resolved | No comment; job exits 0. |
| No committed index | One-time setup-guidance comment; exits 0. |
| Diff touches only docs/config/tests | Comment says "no architectural impact detected". |
| Affected nodes have no wiki article | Comment notes the empty article set; still shows counts. |
| Internal error | Logged; exits 0 unless `fail-on-error: true`. |
| Shallow checkout (no `fetch-depth: 0`) | Base can't be resolved → no comment; logs a hint to set `fetch-depth: 0`. |
