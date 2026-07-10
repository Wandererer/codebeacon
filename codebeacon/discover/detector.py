"""Framework auto-detection and multi/single project determination."""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from codebeacon.common.types import ProjectInfo

# Separator joining a parent-dir prefix onto a colliding project name. Must be
# filesystem-safe (it becomes a wiki/obsidian folder) and free of the graph
# node-id delimiters ("::", "/", "@"), which rules out a slash.
_NAME_SEP = "-"


# ── Signature files → (framework, language) ─────────────────────────────────

SIGNATURE_MAP: list[tuple[str, str, str]] = [
    # (filename_or_glob, framework, primary_language)
    # Order matters: more specific first
    ("angular.json",        "angular",       "typescript"),
    ("nuxt.config.ts",      "nuxt",          "typescript"),
    ("nuxt.config.js",      "nuxt",          "typescript"),
    ("svelte.config.js",    "sveltekit",     "typescript"),
    ("svelte.config.ts",    "sveltekit",     "typescript"),
    ("build.gradle.kts",    "ktor",          "kotlin"),
    ("build.gradle",        "spring-boot",   "java"),   # could be Ktor too, check below
    ("pom.xml",             "spring-boot",   "java"),
    ("Package.swift",       "vapor",         "swift"),
    ("Cargo.toml",          "rust",          "rust"),    # actix/axum refined below
    ("composer.json",       "laravel",       "php"),
    ("Gemfile",             "rails",         "ruby"),
    ("go.mod",              "go",            "go"),      # gin/echo/fiber refined below
    ("package.json",        "node",          "typescript"),  # express/nest/next refined below
    ("requirements.txt",    "python",        "python"),  # fastapi/django/flask refined below
    ("pyproject.toml",      "python",        "python"),  # fastapi/django/flask refined below
    ("setup.py",            "python",        "python"),
    ("*.csproj",            "aspnet",        "csharp"),
]

# Refinement patterns: read content of specific files to narrow down framework
_PACKAGE_JSON_REFINEMENTS: list[tuple[str, str]] = [
    # (pattern_in_deps_or_scripts, framework)
    # Order matters: more specific first
    ("@nestjs/core",       "nestjs"),
    ('"next"',             "nextjs"),   # "next": "..." — avoid matching "nextjs" etc.
    ("nuxt",               "nuxt"),
    ("@sveltejs/kit",      "sveltekit"),
    ("@angular/core",      "angular"),
    ("fastify",            "fastify"),
    ("koa",                "koa"),
    ("express",            "express"),
    ('"react"',            "react"),    # plain React (CRA, Vite, etc.)
    ('"react-dom"',        "react"),
]

_REQUIREMENTS_REFINEMENTS: list[tuple[str, str]] = [
    ("fastapi",   "fastapi"),
    ("django",    "django"),
    ("flask",     "flask"),
    ("tornado",   "tornado"),
    ("aiohttp",   "aiohttp"),
]

_GO_MOD_REFINEMENTS: list[tuple[str, str]] = [
    ("github.com/gofiber/fiber", "fiber"),
    ("github.com/labstack/echo", "echo"),
    ("github.com/gin-gonic/gin", "gin"),
]

_CARGO_REFINEMENTS: list[tuple[str, str]] = [
    ("tauri",      "tauri"),
    ("axum",       "axum"),
    ("actix-web",  "actix"),
    ("rocket",     "rocket"),
    ("warp",       "warp"),
]

_BUILD_GRADLE_KOTLIN_REFINEMENTS: list[tuple[str, str]] = [
    ("ktor", "ktor"),
    ("spring", "spring-boot"),
]


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _refine_node_framework(project_dir: Path) -> str:
    pkg = project_dir / "package.json"
    content = _read_safe(pkg)
    for pattern, fw in _PACKAGE_JSON_REFINEMENTS:
        if pattern in content:
            return fw
    return "node"


def _refine_python_framework(project_dir: Path) -> str:
    for fname in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile"):
        content = _read_safe(project_dir / fname)
        if content:
            lower = content.lower()
            for pattern, fw in _REQUIREMENTS_REFINEMENTS:
                if pattern in lower:
                    return fw
    return "python"


def _refine_go_framework(project_dir: Path) -> str:
    content = _read_safe(project_dir / "go.mod")
    for pattern, fw in _GO_MOD_REFINEMENTS:
        if pattern in content:
            return fw
    return "go"


def _refine_rust_framework(project_dir: Path) -> str:
    content = _read_safe(project_dir / "Cargo.toml")
    for pattern, fw in _CARGO_REFINEMENTS:
        if pattern in content:
            return fw
    return "rust"


def _refine_gradle_framework(project_dir: Path) -> tuple[str, str]:
    content = _read_safe(project_dir / "build.gradle.kts")
    if not content:
        content = _read_safe(project_dir / "build.gradle")
    lower = content.lower()
    for pattern, fw in _BUILD_GRADLE_KOTLIN_REFINEMENTS:
        if pattern in lower:
            if fw == "ktor":
                return ("ktor", "kotlin")
            return ("spring-boot", "java")
    return ("spring-boot", "java")


# Language families for multi-manifest tie-breaking: a signature's declared
# primary_language and the dominant source language only need to agree at the
# family level (a package.json says "typescript" but the code may be plain JS;
# build.gradle says "java" but may be Kotlin).
_LANG_FAMILY: dict[str, str] = {
    "typescript": "js", "javascript": "js",
    "java": "jvm", "kotlin": "jvm",
    "python": "python", "go": "go", "ruby": "ruby",
    "php": "php", "csharp": "csharp", "rust": "rust", "swift": "swift",
}


def _resolve_signature(
    project_dir: Path, sig: str, fw: str, lang: str
) -> tuple[str, str, str]:
    """Refine a chosen signature into a concrete (framework, language, path)."""
    if sig == "*.csproj":
        csproj_files = list(project_dir.glob("*.csproj"))
        return ("aspnet", "csharp", str(csproj_files[0]))
    sig_path = project_dir / sig
    if fw == "node":
        return (_refine_node_framework(project_dir), "typescript", str(sig_path))
    if fw == "python":
        return (_refine_python_framework(project_dir), "python", str(sig_path))
    if fw == "go":
        return (_refine_go_framework(project_dir), "go", str(sig_path))
    if fw == "rust":
        return (_refine_rust_framework(project_dir), "rust", str(sig_path))
    if sig in ("build.gradle.kts", "build.gradle"):
        fw, lang = _refine_gradle_framework(project_dir)
        return (fw, lang, str(sig_path))
    return (fw, lang, str(sig_path))


def detect_framework(project_dir: str | Path) -> tuple[str, str, str]:
    """Detect the framework, language and signature file for a project directory.

    Returns (framework, language, signature_file).
    Returns ("unknown", "unknown", "") if nothing detected.
    """
    project_dir = Path(project_dir)

    # Collect every signature present at this root, in priority order
    # (csproj first, then SIGNATURE_MAP). A single manifest keeps the old
    # first-match-wins behavior exactly.
    present: list[tuple[str, str, str]] = []
    if list(project_dir.glob("*.csproj")):
        present.append(("*.csproj", "aspnet", "csharp"))
    for sig, fw, lang in SIGNATURE_MAP:
        if sig.startswith("*"):
            # glob handled above
            continue
        if (project_dir / sig).exists():
            present.append((sig, fw, lang))

    if not present:
        # No signature file found — try to guess from code files
        return ("unknown", "unknown", "")

    # Multi-manifest tie-break, NARROWED to the incidental-manifest case it
    # targets: only fire when the highest-priority signature is package.json.
    # In practice that manifest is often stray dev-tooling (prettier/husky/
    # tailwind) sitting on top of a Python backend, so plain first-match-wins
    # would misdetect the repo as node. Every strong backend manifest precedes
    # package.json in SIGNATURE_MAP (go.mod, Gemfile, pom.xml, build.gradle,
    # Cargo.toml, composer.json, Package.swift, *.csproj, …), so a Rails/Spring/
    # Go repo with a colocated, file-heavy JS frontend keeps its backend
    # framework by order regardless of source-file counts — the language vote
    # never overrides it.
    if len(present) > 1 and present[0][0] == "package.json":
        dominant = _detect_language_from_files(project_dir)
        dom_family = _LANG_FAMILY.get(dominant)
        if dom_family is not None:
            for cand in present:
                if _LANG_FAMILY.get(cand[2]) == dom_family:
                    sig, fw, lang = cand
                    return _resolve_signature(project_dir, sig, fw, lang)

    sig, fw, lang = present[0]
    return _resolve_signature(project_dir, sig, fw, lang)


def _has_project_signature(directory: Path) -> bool:
    """Return True if directory looks like a project root (has a build/config file)."""
    signature_files = [
        "pom.xml", "build.gradle", "build.gradle.kts",
        "package.json", "requirements.txt", "pyproject.toml", "setup.py",
        "go.mod", "Gemfile", "composer.json", "Cargo.toml",
        "Package.swift", "angular.json",
        "nuxt.config.ts", "nuxt.config.js",
        "svelte.config.js", "svelte.config.ts",
    ]
    for sig in signature_files:
        try:
            if (directory / sig).exists():
                return True
        except OSError:
            # Permission-restricted siblings (e.g. macOS semaphore dirs in /tmp)
            # would otherwise crash the whole discover pass.
            continue
    # Check for *.csproj
    try:
        if list(directory.glob("*.csproj")):
            return True
    except OSError:
        pass
    return False


def _detect_language_from_files(directory: Path) -> str:
    """Detect dominant language by counting code files."""
    counts: dict[str, int] = {}
    ext_to_lang = {
        ".java": "java", ".kt": "kotlin",
        ".py": "python",
        ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
        ".go": "go",
        ".rb": "ruby",
        ".php": "php",
        ".cs": "csharp",
        ".rs": "rust",
        ".swift": "swift",
    }
    try:
        # os.walk with pruning, not rglob: an unbounded rglob descends into
        # node_modules / .git / dist, which on a Node repo means enumerating
        # tens of thousands of vendored files (and skews the language vote
        # toward vendored JS) just to answer "what language is this project".
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = [
                d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in ext_to_lang:
                    lang = ext_to_lang[ext]
                    counts[lang] = counts.get(lang, 0) + 1
    except (PermissionError, OSError):
        pass

    if not counts:
        return "unknown"
    return max(counts, key=lambda k: counts[k])


_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build", "target",
    ".next", ".nuxt", "coverage", ".venv", "venv", "env", ".tox",
}



def _iter_subdirs(directory: Path) -> list[Path]:
    """Return immediate subdirectories, skipping common non-project dirs."""
    try:
        return [
            d for d in sorted(directory.iterdir())
            if d.is_dir() and not d.name.startswith(".") and d.name not in _SKIP_DIRS
        ]
    except (PermissionError, OSError):
        return []


def _disambiguate_project_names(projects: list[ProjectInfo]) -> list[ProjectInfo]:
    """Make every project ``name`` unique in place.

    A project's name is its identity for every downstream surface — the graph
    node-ID prefix and ``project`` attr, the wiki/obsidian folder, the
    contextmap stats key and ``project_roots`` — all of which key off it and
    silently last-wins on a clash. Two projects sharing a directory name
    (e.g. appA/frontend + appB/frontend) would otherwise conflate: merged
    folders, collapsed route nodes, summed stat rows, leaked absolute paths.

    Colliding names get a parent-dir prefix (``appA-frontend``); a short path
    hash breaks any residual (second-order) clash. Unique names are untouched.
    """
    counts = Counter(p.name for p in projects)
    if all(c == 1 for c in counts.values()):
        return projects

    # Pass 1: parent-dir prefix for names shared by 2+ projects.
    for p in projects:
        if counts[p.name] > 1:
            parent = Path(p.path).parent.name
            if parent:
                p.name = f"{parent}{_NAME_SEP}{p.name}"

    # Pass 2: any name still shared (e.g. x/foo/frontend + y/foo/frontend, or a
    # rewrite that collided with an already-unique name) gets a path hash so the
    # result is guaranteed unique.
    recounts = Counter(p.name for p in projects)
    for p in projects:
        if recounts[p.name] > 1:
            digest = hashlib.sha1(p.path.encode("utf-8")).hexdigest()[:6]
            p.name = f"{p.name}{_NAME_SEP}{digest}"
    return projects


def discover_projects(paths: list[str]) -> list[ProjectInfo]:
    """Main entry point: given a list of input paths, return discovered projects.

    Logic:
    - 2+ paths → treat each as a separate project (multi mode)
    - 1 path with signature → single project mode
    - 1 path without signature → scan up to 2-depth subdirs for projects (multi mode)
      Handles monorepos where projects live in subdirectories (e.g. WaveLog/server,
      aptscore/frontend, murmur/landing).
    """
    if len(paths) > 1:
        return _disambiguate_project_names(_multi_from_paths(paths))

    single_path = Path(paths[0]).resolve()

    if not single_path.exists():
        raise FileNotFoundError(f"Path does not exist: {single_path}")

    if not single_path.is_dir():
        raise ValueError(f"Path must be a directory: {single_path}")

    if _has_project_signature(single_path):
        return [_build_project_info(single_path, multi=False)]

    # No signature at root: scan up to 2 levels deep.
    # Level 1: direct subdirs (e.g. DiveAI/, WaveLog/, aptscore/)
    # Level 2: if a subdir has no signature itself, scan its children
    #           (e.g. WaveLog/server, aptscore/frontend, murmur/landing)
    subprojects: list[ProjectInfo] = []
    seen_paths: set[str] = set()
    for subdir in _iter_subdirs(single_path):
        if _has_project_signature(subdir):
            subprojects.append(_build_project_info(subdir, multi=True))
            seen_paths.add(str(subdir))
            # Scan children for embedded sub-projects with their own signature
            # (e.g. Tauri: desktop/ has svelte.config.js + desktop/src-tauri/ has Cargo.toml)
            for nested in _iter_subdirs(subdir):
                if str(nested) not in seen_paths and _has_project_signature(nested):
                    subprojects.append(_build_project_info(nested, multi=True))
                    seen_paths.add(str(nested))
        else:
            for nested in _iter_subdirs(subdir):
                if str(nested) not in seen_paths and _has_project_signature(nested):
                    subprojects.append(_build_project_info(nested, multi=True))
                    seen_paths.add(str(nested))

    if subprojects:
        return _disambiguate_project_names(subprojects)

    # No project signatures found anywhere: try generic mode
    lang = _detect_language_from_files(single_path)
    if lang == "unknown":
        raise ValueError(
            f"No projects found under {single_path}.\n"
            "Make sure the path contains source code or a project file "
            "(pom.xml, package.json, go.mod, etc.)"
        )

    return [ProjectInfo(
        name=single_path.name,
        path=str(single_path),
        framework="generic",
        language=lang,
        signature_file="",
        is_multi=False,
    )]


def classify_repo_type(root: str | Path, projects: list[ProjectInfo]) -> str:
    """Classify the repo structure into one of: meta, microservices, monorepo, single.

    - meta:          `.gitmodules` exists → git submodules aggregate independent
                     projects (org-wide umbrella repos).
    - microservices: 2+ projects AND either (a) infra orchestration at root
                     (k8s/, kubernetes/, helm/), or (b) 2+ projects ship a Dockerfile.
    - monorepo:      2+ projects without microservice signals.
    - single:        one project.
    """
    root = Path(root)

    if (root / ".gitmodules").is_file():
        return "meta"

    if len(projects) <= 1:
        return "single"

    for infra in ("k8s", "kubernetes", "helm"):
        if (root / infra).is_dir():
            return "microservices"

    dockerfile_count = 0
    for p in projects:
        if (Path(p.path) / "Dockerfile").is_file():
            dockerfile_count += 1
            if dockerfile_count >= 2:
                return "microservices"

    return "monorepo"


def _multi_from_paths(paths: list[str]) -> list[ProjectInfo]:
    """Treat each path as an independent project."""
    projects = []
    for p in paths:
        resolved = Path(p).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {resolved}")
        projects.append(_build_project_info(resolved, multi=True))
    return projects


def _build_project_info(directory: Path, multi: bool) -> ProjectInfo:
    framework, language, sig_file = detect_framework(directory)
    if framework == "unknown":
        lang = _detect_language_from_files(directory)
        return ProjectInfo(
            name=directory.name,
            path=str(directory),
            framework="generic",
            language=lang or "unknown",
            signature_file="",
            is_multi=multi,
        )
    return ProjectInfo(
        name=directory.name,
        path=str(directory),
        framework=framework,
        language=language,
        signature_file=sig_file,
        is_multi=multi,
    )


def extract_convention_routes(project: ProjectInfo) -> list[str]:
    """Extract file-system based routes for Next.js / Nuxt / SvelteKit.

    Returns a list of route path strings. Actual RouteInfo objects are built in extract/routes.py.
    This is a discovery-time stub that returns raw route strings.
    """
    root = Path(project.path)
    routes: list[str] = []

    if project.framework in ("nextjs", "next"):
        # Pages Router: pages/**/*.{ts,tsx,js,jsx} → route
        pages_dir = root / "pages"
        if pages_dir.exists():
            routes.extend(_fs_routes_from_dir(pages_dir, pages_dir))
        # App Router: app/**/page.{ts,tsx,js,jsx} → route. JS-based projects use
        # page.js/page.jsx, so globbing only .ts/.tsx silently dropped them.
        app_dir = root / "app"
        if app_dir.exists():
            for ext in ("tsx", "ts", "jsx", "js"):
                for f in app_dir.rglob(f"page.{ext}"):
                    routes.append(_app_router_path(f, app_dir))

    elif project.framework == "nuxt":
        pages_dir = root / "pages"
        if pages_dir.exists():
            routes.extend(_fs_routes_from_dir(pages_dir, pages_dir))

    elif project.framework == "sveltekit":
        routes_dir = root / "src" / "routes"
        if routes_dir.exists():
            for f in routes_dir.rglob("+page.svelte"):
                route = "/" + str(f.parent.relative_to(routes_dir)).replace(os.sep, "/")
                if route == "/.":
                    route = "/"
                routes.append(route)

    return routes


def _fs_routes_from_dir(file_dir: Path, base_dir: Path) -> list[str]:
    """Convert Next.js / Nuxt pages directory files to route strings."""
    routes = []
    for f in file_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in {".tsx", ".ts", ".jsx", ".js", ".vue"}:
            rel = f.relative_to(base_dir)
            parts = list(rel.parts)
            # Remove extension from last part
            last = parts[-1]
            stem = last.rsplit(".", 1)[0]
            # Skip _app, _document, _error in Next.js
            if stem.startswith("_"):
                continue
            parts[-1] = stem
            # index → ""
            if parts[-1] == "index":
                parts = parts[:-1]
            route = "/" + "/".join(parts)
            # Convert [param] → :param, [...slug] → *
            route = re.sub(r"\[\.\.\.(\w+)\]", "*", route)
            route = re.sub(r"\[(\w+)\]", r":\1", route)
            routes.append(route)
    return routes


def _app_router_path(page_file: Path, app_dir: Path) -> str:
    rel = page_file.parent.relative_to(app_dir)
    parts = list(rel.parts)
    route = "/" + "/".join(parts) if parts else "/"
    route = re.sub(r"\(.*?\)/", "", route)   # route groups: (group)/
    route = re.sub(r"/@[^/]+", "", route)    # parallel-route slots: @team/ etc.
    route = re.sub(r"\[\.\.\.(\w+)\]", "*", route)
    route = re.sub(r"\[(\w+)\]", r":\1", route)
    return route or "/"
