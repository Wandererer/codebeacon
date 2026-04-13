"""codebeacon.yaml loader and validator."""

from __future__ import annotations

import os
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
    graph_html: bool = True
    context_map_targets: list = field(default_factory=lambda: ["CLAUDE.md", ".cursorrules", "AGENTS.md"])


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
    config_file: str = ""  # path to the loaded yaml file


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
        if "name" not in p or "path" not in p:
            raise ValueError(f"Project entry missing 'name' or 'path': {p}")
        # Resolve path relative to config file location
        proj_path = p["path"]
        if not os.path.isabs(proj_path):
            proj_path = str(path.parent / proj_path)
        projects.append(ProjectConfig(
            name=p["name"],
            path=proj_path,
            type=p.get("type", "auto"),
        ))

    output_raw = raw.get("output", {})
    context_map = output_raw.get("context_map", {})
    output = OutputConfig(
        dir=output_raw.get("dir", ".codebeacon"),
        wiki=output_raw.get("wiki", True),
        obsidian=output_raw.get("obsidian", True),
        graph_html=output_raw.get("graph_html", True),
        context_map_targets=context_map.get("targets", ["CLAUDE.md", ".cursorrules", "AGENTS.md"]),
    )

    wave_raw = raw.get("wave", {})
    wave = WaveConfig(
        auto=wave_raw.get("auto", True),
        chunk_size=wave_raw.get("chunk_size", 300),
        max_parallel=wave_raw.get("max_parallel", 5),
    )

    semantic_raw = raw.get("semantic", {})
    semantic = SemanticConfig(
        enabled=semantic_raw.get("enabled", False),
    )

    return CodebeaconConfig(
        version=version,
        projects=projects,
        output=output,
        wave=wave,
        semantic=semantic,
        config_file=str(path),
    )


def find_config(start_dir: str | Path) -> Optional[Path]:
    """Search for codebeacon.yaml starting from start_dir."""
    start_dir = Path(start_dir)
    candidates = [
        start_dir / "codebeacon.yaml",
        start_dir / "codebeacon.yml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def generate_config(projects: list, output_dir: str, config_path: str | Path) -> None:
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
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
