"""Browser libraries for the HTML exports, served locally by default.

``beacon.html`` needs D3 and ``callflow.html`` needs Mermaid. Loading them from
a CDN made both pages silently useless without internet access — the page
renders, the diagram area stays blank, and nothing says why — which is the
opposite of what a tool that positions itself as local-first and air-gap-safe
should do (graphify #2527).

So the two bundles ship inside the wheel (``codebeacon/export/vendor/``), get
copied ONCE per output directory into ``.codebeacon/_assets/``, and are
referenced relatively from each page. Copying beats inlining: ``callflow.html``
stays ~19 KB instead of becoming a 3.4 MB file that is fully rewritten on every
scan, and one copy serves every page in the repository.

``output.html_assets: cdn`` in ``codebeacon.yaml`` restores the CDN tags for
anyone who would rather not commit 3.6 MB of vendored JavaScript.
"""

from __future__ import annotations

import sys
from pathlib import Path

from codebeacon.common.io import write_text_if_changed


# Directory (relative to an output dir) the bundles are copied into.
_ASSETS_DIRNAME = "_assets"

# library key → (filename in codebeacon/export/vendor/, CDN URL fallback)
_LIBRARIES: dict[str, tuple[str, str]] = {
    "d3": ("d3.v7.min.js", "https://d3js.org/d3.v7.min.js"),
    "mermaid": (
        "mermaid.min.js",
        "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js",
    ),
}

_VENDOR_DIR = Path(__file__).with_name("vendor")


def vendored_path(library: str) -> Path:
    """Absolute path to a vendored bundle inside the installed package."""
    return _VENDOR_DIR / _LIBRARIES[library][0]


def cdn_url(library: str) -> str:
    """The CDN URL a page falls back to under ``html_assets: cdn``."""
    return _LIBRARIES[library][1]


def ensure_assets(output_dir: str | Path, libraries: tuple[str, ...]) -> list[str]:
    """Copy the named bundles into ``<output_dir>/_assets/``; return their names.

    Returns the filenames actually available, so a caller can fall back to the
    CDN for anything that could not be materialised. The copy is
    content-compared, so a rescan does not touch a bundle that is already there
    — these files are committed alongside the pages that use them.

    A bundle missing from the wheel or an unwritable output directory is a
    warning, never a raised exception: an HTML export is a convenience and must
    not take the scan down with it.
    """
    dest_dir = Path(output_dir) / _ASSETS_DIRNAME
    available: list[str] = []
    for library in libraries:
        filename, _url = _LIBRARIES[library]
        source = vendored_path(library)
        try:
            payload = source.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"    Warning: vendored {filename} unreadable ({exc}); "
                f"falling back to the CDN for this page.",
                file=sys.stderr,
            )
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            write_text_if_changed(dest_dir / filename, payload)
        except OSError as exc:
            print(
                f"    Warning: could not write {filename} into {dest_dir} ({exc}); "
                f"falling back to the CDN for this page.",
                file=sys.stderr,
            )
            continue
        available.append(filename)
    return available


def html_head_scripts(
    output_dir: str | Path,
    libraries: tuple[str, ...],
    mode: str = "local",
) -> str:
    """The ``<script src=…>`` tags a page should carry for ``libraries``.

    ``mode="local"`` (the default) materialises the bundles next to the page and
    emits relative ``_assets/…`` references, so the page works from ``file://``
    with no network. ``mode="cdn"`` emits the upstream URLs and copies nothing.
    Any library that could not be materialised silently degrades to its CDN URL
    rather than producing a page that references a file which is not there.
    """
    if mode == "cdn":
        return "\n".join(
            f'<script src="{cdn_url(lib)}"></script>' for lib in libraries
        )

    available = set(ensure_assets(output_dir, libraries))
    tags = []
    for lib in libraries:
        filename = _LIBRARIES[lib][0]
        if filename in available:
            tags.append(f'<script src="{_ASSETS_DIRNAME}/{filename}"></script>')
        else:
            tags.append(f'<script src="{cdn_url(lib)}"></script>')
    return "\n".join(tags)
