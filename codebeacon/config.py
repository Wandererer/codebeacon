"""codebeacon.yaml loader and validator."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ProjectConfig:
    name: str
    path: str
    type: str = "auto"  # framework type or "auto" for detection


@dataclass
class OutputConfig:
    dir: str = ".codebeacon"
    wiki: bool = True
    obsidian: bool = True
    context_map_targets: list = field(default_factory=lambda: ["CLAUDE.md", ".cursorrules", "AGENTS.md"])
    # In a multi-project workspace, split per-project detail out of CLAUDE.md
    # into scoped .claude/rules/ files (keeps CLAUDE.md under ~200 lines). Set to
    # false to keep the old monolithic CLAUDE.md. Single-project output is
    # unaffected either way.
    rules_split: bool = True


@dataclass
class WaveConfig:
    auto: bool = True
    chunk_size: int = 300
    max_parallel: int = 5


@dataclass
class SemanticConfig:
    enabled: bool = False


@dataclass
class CodebeaconConfig:
    version: int
    projects: list  # list[ProjectConfig]
    output: OutputConfig = field(default_factory=OutputConfig)
    wave: WaveConfig = field(default_factory=WaveConfig)
    semantic: SemanticConfig = field(default_factory=SemanticConfig)
    deep_dive: bool = False  # generate per-project outputs + combined workspace
    config_file: str = ""  # path to the loaded yaml file


def _section_mapping(value, key: str) -> dict:
    """Return a config section as a mapping.

    A missing or explicitly-null section (``output:`` on its own line) becomes
    an empty dict so downstream ``.get`` calls fall back to defaults. A
    present-but-non-mapping scalar (``output: express``, ``semantic: on``) is a
    user mistake and raises ``ValueError`` — which the CLI catches and reports as
    a friendly "Error loading config" message instead of leaking an
    ``AttributeError`` traceback from ``str.get``/``bool.get``.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            f"'{key}' must be a mapping of settings, got "
            f"{type(value).__name__}: {value!r}"
        )
    return value


def _dump_yaml_atomic(config_path: Path, data) -> None:
    """Serialize ``data`` to ``config_path`` atomically.

    ``open(path, "w")`` truncates the target the instant it opens, so a crash or
    disk-full *during* ``yaml.dump`` would leave a user's hand-curated
    codebeacon.yaml empty or half-written. Write to a sibling temp file and
    ``os.replace`` it into place instead — the same all-or-nothing guarantee
    beacon.json already gets (see codebeacon/graph/write.py).

    ``os.replace`` does not follow a final-component symlink: replacing a
    symlinked codebeacon.yaml (a shared/canonical config linked into the repo)
    would drop a regular file over the link and leave the canonical target
    stale. Resolve the link first and write/replace against the *real* target so
    the symlink stays intact and the true file is updated — the temp is placed
    next to ``real`` to guarantee same-filesystem ``os.replace``. Copy the
    existing target's mode onto the temp before replacing so a user's
    ``chmod 600`` survives the rewrite (a fresh temp otherwise carries
    umask-default 0644).
    """
    real = Path(os.path.realpath(config_path))
    tmp_path = real.with_name(real.name + ".tmp")
    with open(tmp_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if real.exists():
        shutil.copymode(real, tmp_path)
    os.replace(tmp_path, real)


def load_config(path: str | Path) -> CodebeaconConfig:
    """Load and validate codebeacon.yaml from the given path."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid config file: {path}")

    version = raw.get("version", 1)
    if version != 1:
        raise ValueError(f"Unsupported config version: {version}. Expected 1.")

    projects_raw = raw.get("projects", [])
    if not isinstance(projects_raw, list) or not projects_raw:
        raise ValueError("Config must contain at least one project under 'projects:'")

    projects = []
    for p in projects_raw:
        # A bare `-` in the YAML list arrives as None; a scalar entry as str.
        # Both must surface as a config error, not a TypeError traceback.
        if not isinstance(p, dict):
            raise ValueError(f"Invalid project entry (expected mapping): {p!r}")
        # A present-but-blank `name:`/`path:` (YAML null) is treated the same as
        # a missing key: required fields with no meaningful default, so a config
        # error rather than letting None flow into a downstream f-string format
        # spec (cli.py) and blow up with a bare TypeError.
        name = p.get("name")
        proj_path = p.get("path")
        if name is None or proj_path is None:
            raise ValueError(f"Project entry missing 'name' or 'path': {p}")
        # A present-but-blank `type:` falls back to auto-detection, matching how
        # an omitted key already behaves.
        ptype = p.get("type")
        if ptype is None:
            ptype = "auto"
        # Resolve path relative to config file location
        if not os.path.isabs(proj_path):
            proj_path = str(path.parent / proj_path)
        projects.append(ProjectConfig(
            name=name,
            path=proj_path,
            type=ptype,
        ))

    # `.get(key, {})` is not enough on two counts: a section present-but-empty
    # (`output:` on its own line) loads as None, and None.get(...) crashes; a
    # present-but-non-mapping scalar (`output: express`) would raise a raw
    # AttributeError. _section_mapping normalizes null → {} and rejects scalars
    # with a ValueError the CLI reports cleanly.
    output_raw = _section_mapping(raw.get("output"), "output")
    context_map = _section_mapping(output_raw.get("context_map"), "output.context_map")
    output = OutputConfig(
        dir=output_raw.get("dir", ".codebeacon"),
        wiki=output_raw.get("wiki", True),
        obsidian=output_raw.get("obsidian", True),
        context_map_targets=context_map.get("targets", ["CLAUDE.md", ".cursorrules", "AGENTS.md"]),
        rules_split=context_map.get("rules_split", True),
    )

    wave_raw = _section_mapping(raw.get("wave"), "wave")
    wave = WaveConfig(
        auto=wave_raw.get("auto", True),
        chunk_size=wave_raw.get("chunk_size", 300),
        max_parallel=wave_raw.get("max_parallel", 5),
    )

    semantic_raw = _section_mapping(raw.get("semantic"), "semantic")
    semantic = SemanticConfig(
        enabled=semantic_raw.get("enabled", False),
    )

    return CodebeaconConfig(
        version=version,
        projects=projects,
        output=output,
        wave=wave,
        semantic=semantic,
        deep_dive=bool(raw.get("deep_dive", False)),
        config_file=str(path),
    )


def find_config(start_dir: str | Path, walk_up: bool = False) -> Optional[Path]:
    """Search for codebeacon.yaml starting from start_dir.

    Args:
        start_dir: directory to begin the search
        walk_up:   when True, walk parent directories until a config is found
                   or the filesystem root is reached
    """
    current = Path(start_dir).resolve()
    while True:
        for name in ("codebeacon.yaml", "codebeacon.yml"):
            candidate = current / name
            if candidate.exists():
                return candidate
        if not walk_up:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def generate_config(
    projects: list,
    output_dir: str,
    config_path: str | Path,
    deep_dive: bool = False,
) -> None:
    """Write an auto-generated codebeacon.yaml for multi-project scans."""
    config_path = Path(config_path)
    data = {
        "version": 1,
        "projects": [
            {"name": p.name, "path": p.path, "type": p.framework}
            for p in projects
        ],
        "output": {"dir": output_dir},
        "wave": {"auto": True, "chunk_size": 300, "max_parallel": 5},
        "semantic": {"enabled": False},
    }
    if deep_dive:
        data["deep_dive"] = True
    _dump_yaml_atomic(config_path, data)


def discover_new_projects(config: CodebeaconConfig) -> list:
    """Re-scan the workspace around the loaded config for newly added projects.

    Compares the freshly discovered project list (rooted at the yaml's parent
    directory) against the projects already tracked in ``config.projects``,
    using resolved absolute paths for de-duplication. Returns ``ProjectInfo``
    entries that are NOT yet in the yaml so callers can append them.
    """
    from codebeacon.discover.detector import discover_projects

    workspace_root = Path(config.config_file).parent
    try:
        found = discover_projects([str(workspace_root)])
    except (FileNotFoundError, ValueError):
        return []

    known_paths = {Path(p.path).resolve() for p in config.projects}
    new_projects: list = []
    for p in found:
        resolved = Path(p.path).resolve()
        if resolved in known_paths:
            continue
        # Skip projects nested inside a project already tracked in the yaml —
        # the parent entry already covers them, so adding a child would
        # double-count files and clutter the config (e.g. `dring-mobile/android`
        # inside a `dring-mobile` rails app).
        if any(known == resolved or known in resolved.parents for known in known_paths):
            continue
        new_projects.append(p)
    return new_projects


def append_projects_to_yaml(config_path: str | Path, new_projects: list) -> None:
    """Append discovered projects to an existing codebeacon.yaml in place.

    Preserves all unrelated keys (output, wave, semantic, deep_dive, etc.) and
    existing project entries. Re-serializes via pyyaml so any comments in the
    original file are lost — acceptable trade-off because the file is normally
    machine-generated by :func:`generate_config`.
    """
    config_path = Path(config_path)
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    projects_list = raw.get("projects") or []
    for p in new_projects:
        projects_list.append({
            "name": p.name,
            "path": p.path,
            "type": p.framework,
        })
    raw["projects"] = projects_list

    _dump_yaml_atomic(config_path, raw)
