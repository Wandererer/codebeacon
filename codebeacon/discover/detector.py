"""Framework auto-detection and multi/single project determination."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from codebeacon.common.types import ProjectInfo


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


def detect_framework(project_dir: str | Path) -> tuple[str, str, str]:
    """Detect the framework, language and signature file for a project directory.

    Returns (framework, language, signature_file).
    Returns ("unknown", "unknown", "") if nothing detected.
    """
    project_dir = Path(project_dir)

    # Check for *.csproj (glob-style)
    csproj_files = list(project_dir.glob("*.csproj"))
    if csproj_files:
        return ("aspnet", "csharp", str(csproj_files[0]))

    for sig, fw, lang in SIGNATURE_MAP:
        if sig.startswith("*"):
            # glob handled above
            continue
        sig_path = project_dir / sig
        if sig_path.exists():
            # Refine generic frameworks
            if fw == "node":
                fw = _refine_node_framework(project_dir)
                return (fw, "typescript", str(sig_path))
            if fw == "python":
                fw = _refine_python_framework(project_dir)
                return (fw, "python", str(sig_path))
            if fw == "go":
                fw = _refine_go_framework(project_dir)
                return (fw, "go", str(sig_path))
            if fw == "rust":
                fw = _refine_rust_framework(project_dir)
                return (fw, "rust", str(sig_path))
            if sig in ("build.gradle.kts", "build.gradle"):
                fw, lang = _refine_gradle_framework(project_dir)
                return (fw, lang, str(sig_path))
            return (fw, lang, str(sig_path))

    # No signature file found — try to guess from code files
    return ("unknown", "unknown", "")


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
        if (directory / sig).exists():
            return True
    # Check for *.csproj
    if list(directory.glob("*.csproj")):
        return True
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
        for entry in directory.rglob("*"):
            if entry.is_file() and entry.suffix in ext_to_lang:
                lang = ext_to_lang[entry.suffix]
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
        return _multi_from_paths(paths)

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
        return subprojects

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
        # App Router: app/**/page.{ts,tsx,js,jsx} → route
        app_dir = root / "app"
        if app_dir.exists():
            for f in app_dir.rglob("page.tsx"):
                routes.append(_app_router_path(f, app_dir))
            for f in app_dir.rglob("page.ts"):
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
        if f.is_file() and f.suffix in {".tsx", ".ts", ".jsx", ".js", ".vue"}:
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
    route = re.sub(r"\[\.\.\.(\w+)\]", "*", route)
    route = re.sub(r"\[(\w+)\]", r":\1", route)
    return route or "/"
