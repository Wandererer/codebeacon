# Vendored browser libraries

The HTML exports (`beacon.html`, `callflow.html`) used to pull these two
libraries from a CDN at view time. That contradicted codebeacon's local-first
posture in the worst way: when the fetch was blocked — air-gapped network,
offline laptop, corporate proxy, or simply opening the committed file from
`file://` — the page still loaded, but the diagram area stayed blank with no
error. Vendoring them makes the export work with no network at all.

They are copied once per output directory into `.codebeacon/_assets/` and
referenced relatively, rather than inlined, so each HTML page stays small and
one copy serves every page in the repo. `output.html_assets: cdn` restores the
CDN `<script>` tags for anyone who would rather not commit 3.6 MB.

| File | Library | Version | Source URL | License |
| --- | --- | --- | --- | --- |
| `d3.v7.min.js` | D3 | 7.9.0 | `https://d3js.org/d3.v7.min.js` | ISC (`LICENSE-d3.txt`) |
| `mermaid.min.js` | Mermaid | 10.9.8 | `https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js` | MIT (`LICENSE-mermaid.txt`) |

Fetched 2026-08-31. SHA-256:

```
f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539  d3.v7.min.js
8d607d7ef1d077a8aa202e18e62212bfa992c68bfeabc5cf45d51a128fe6675d  mermaid.min.js
```

To refresh, re-download from the source URLs above, update the version and
checksum rows here, and re-run `tests/test_audit_070_export.py`, which asserts
both files are present, non-empty, and readable through `importlib.resources`
from an installed wheel.
