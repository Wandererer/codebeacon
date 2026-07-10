"""Regression tests for the 0.6.9 cli/config/pipeline audit (group F-I).

| # | Site                        | Bug                                                     |
|---|-----------------------------|---------------------------------------------------------|
| C1| cli._cmd_scan               | --list-only silently ran a full sync when a config existed |
| C2| cli._cmd_sync + pipeline    | codebeacon.yaml wave/output/semantic parsed but never applied |
| C3| config.load_config          | blank `name:`/`type:` (YAML null) → TypeError in cli listing |
| C4| config yaml writers         | non-atomic open("w") truncation destroyed a hand-curated yaml |
| C5| config.load_config          | scalar output:/wave:/semantic: → uncaught AttributeError |
| C6| cli._cmd_upgrade            | no-pip fallback advised pipx/uv-tool for a `uv venv` install |
"""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest
import yaml

from codebeacon import cli


# ── C1. --list-only never auto-switches to sync / writes anything ────────────

class TestScanListOnly:
    def _ws(self, tmp_path):
        ws = tmp_path / "ws"
        (ws / "myproj").mkdir(parents=True)
        (ws / "myproj" / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (ws / "codebeacon.yaml").write_text(
            "version: 1\n"
            "projects:\n"
            "  - name: myproj\n"
            "    path: myproj\n"
            "    type: python\n"
            "output:\n"
            "  dir: .codebeacon\n",
            encoding="utf-8",
        )
        return ws

    def test_list_only_does_not_switch_to_sync(self, monkeypatch, tmp_path):
        ws = self._ws(tmp_path)
        calls: list = []
        monkeypatch.setattr(cli, "_cmd_sync", lambda args: calls.append(args) or 0)
        before = (ws / "codebeacon.yaml").read_text(encoding="utf-8")

        rc = cli._cmd_scan(
            argparse.Namespace(paths=[str(ws)], list_only=True, watch=False)
        )

        assert rc == 0
        assert calls == []  # the sync auto-switch must not fire under --list-only
        assert not (ws / ".codebeacon").exists()
        assert not (ws / "CLAUDE.md").exists()
        # a read-only listing must not rewrite the config either
        assert (ws / "codebeacon.yaml").read_text(encoding="utf-8") == before

    def test_without_list_only_still_switches_to_sync(self, monkeypatch, tmp_path):
        """Guard against over-correcting: a normal scan over a config dir must
        still hand off to sync."""
        ws = self._ws(tmp_path)
        calls: list = []
        monkeypatch.setattr(cli, "_cmd_sync", lambda args: calls.append(args) or 0)

        rc = cli._cmd_scan(
            argparse.Namespace(paths=[str(ws)], list_only=False, watch=False)
        )

        assert rc == 0
        assert len(calls) == 1  # auto-switched to sync as before


# ── C2. codebeacon.yaml settings actually reach the pipeline ─────────────────

class TestConfigWiredIntoPipeline:
    def _write_cfg(self, tmp_path, *, output=None, wave=None, semantic=None):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        data: dict = {
            "version": 1,
            "projects": [{"name": "app", "path": "./app", "type": "python"}],
        }
        if output is not None:
            data["output"] = output
        if wave is not None:
            data["wave"] = wave
        if semantic is not None:
            data["semantic"] = semantic
        cfg = tmp_path / "codebeacon.yaml"
        cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
        return cfg

    def _run_sync_capture(self, monkeypatch, cfg, *, cli_semantic=False):
        captured: dict = {}

        def rec(projects, output_dir, args):
            captured["args"] = args
            return 0

        monkeypatch.setattr(cli, "run_pipeline", rec)
        rc = cli._cmd_sync(argparse.Namespace(
            config=str(cfg), no_rediscover=True, semantic=cli_semantic,
        ))
        assert rc == 0
        return captured["args"]

    def test_output_and_wave_settings_reach_pipeline(self, monkeypatch, tmp_path):
        cfg = self._write_cfg(
            tmp_path,
            output={"dir": ".codebeacon", "wiki": False, "obsidian": False,
                    "context_map": {"targets": ["CLAUDE.md"]}},
            wave={"auto": True, "chunk_size": 50, "max_parallel": 2},
            semantic={"enabled": True},
        )
        args = self._run_sync_capture(monkeypatch, cfg)
        assert args.output_wiki is False
        assert args.output_obsidian is False
        assert args.context_map_targets == ["CLAUDE.md"]
        assert args.wave_chunk_size == 50
        assert args.wave_max_parallel == 2
        # semantic.enabled in the yaml turns semantic on even with no CLI flag
        assert args.semantic is True

    def test_cli_semantic_flag_overrides_config_disabled(self, monkeypatch, tmp_path):
        cfg = self._write_cfg(tmp_path, semantic={"enabled": False})
        args = self._run_sync_capture(monkeypatch, cfg, cli_semantic=True)
        assert args.semantic is True  # explicit CLI flag wins over yaml default

    def test_semantic_off_when_neither_source_enables_it(self, monkeypatch, tmp_path):
        cfg = self._write_cfg(tmp_path, semantic={"enabled": False})
        args = self._run_sync_capture(monkeypatch, cfg, cli_semantic=False)
        assert args.semantic is False

    def test_run_pipeline_honors_gates_and_wave_size(self, monkeypatch, tmp_path):
        """End-to-end: the gates on `args` actually skip exporters and resize
        waves inside run_pipeline."""
        pytest.importorskip("tree_sitter_python")
        from codebeacon.common.types import ProjectInfo
        from codebeacon.pipeline import run_pipeline
        import codebeacon.wave as wavemod

        proj = tmp_path / "app"
        proj.mkdir()
        (proj / "main.py").write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/p')\n"
            "def p():\n"
            "    return {}\n",
            encoding="utf-8",
        )
        out = tmp_path / ".codebeacon"

        seen: dict = {}
        real_auto_wave = wavemod.auto_wave

        def spy(*a, **k):
            seen["chunk_size"] = k.get("chunk_size")
            seen["max_parallel"] = k.get("max_parallel")
            return real_auto_wave(*a, **k)

        monkeypatch.setattr(wavemod, "auto_wave", spy)

        projects = [ProjectInfo(
            name="app", path=str(proj), framework="fastapi",
            language="python", signature_file="",
        )]
        args = argparse.Namespace(
            wiki_only=False, update=False, semantic=False, exclude=[],
            obsidian_dir=None, max_failure_rate=1.0,
            output_wiki=False, output_obsidian=False,
            context_map_targets=["CLAUDE.md"],
            wave_chunk_size=7, wave_max_parallel=3,
        )
        rc = run_pipeline(projects, str(out), args)
        assert rc == 0

        # wave sizing came from args, not the hardcoded 300/5
        assert seen == {"chunk_size": 7, "max_parallel": 3}
        # output.wiki:false / obsidian:false skipped those exporters
        assert not (out / "wiki").exists()
        assert not (out / "obsidian").exists()
        # context_map.targets limited the write to CLAUDE.md only
        assert (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / ".cursorrules").exists()
        assert not (tmp_path / "AGENTS.md").exists()

    def test_defaults_preserved_when_args_lack_gate_fields(self, monkeypatch, tmp_path):
        """A plain scan Namespace (no output_*/wave_* fields) must keep every
        exporter on and the default wave size — the getattr fallbacks."""
        pytest.importorskip("tree_sitter_python")
        from codebeacon.common.types import ProjectInfo
        from codebeacon.pipeline import run_pipeline
        import codebeacon.wave as wavemod

        proj = tmp_path / "app"
        proj.mkdir()
        (proj / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        out = tmp_path / ".codebeacon"

        seen: dict = {}
        real_auto_wave = wavemod.auto_wave

        def spy(*a, **k):
            seen["chunk_size"] = k.get("chunk_size")
            return real_auto_wave(*a, **k)

        monkeypatch.setattr(wavemod, "auto_wave", spy)

        projects = [ProjectInfo(
            name="app", path=str(proj), framework="python",
            language="python", signature_file="",
        )]
        args = argparse.Namespace(
            wiki_only=False, update=False, semantic=False, exclude=[],
            obsidian_dir=None, max_failure_rate=1.0,
        )
        rc = run_pipeline(projects, str(out), args)
        assert rc == 0
        assert seen["chunk_size"] == 300  # default preserved
        assert (out / "wiki").exists()
        assert (tmp_path / "CLAUDE.md").exists()


# ── C3. blank name:/type: are config errors, not TypeError tracebacks ────────

class TestConfigBlankScalars:
    def _write(self, tmp_path, body: str):
        p = tmp_path / "codebeacon.yaml"
        p.write_text(body, encoding="utf-8")
        return p

    def test_blank_type_defaults_to_auto(self, tmp_path):
        from codebeacon.config import load_config
        cfg = load_config(self._write(tmp_path, (
            "version: 1\n"
            "projects:\n"
            "  - name: proj\n"
            "    path: .\n"
            "    type:\n"     # present but null
        )))
        proj = cfg.projects[0]
        assert proj.type == "auto"
        # the exact cli.py listing format that used to raise TypeError
        effective = proj.type if proj.type != "auto" else "fastapi"
        assert f"  {proj.name:<20}  {effective:<15}  {proj.path}"

    def test_blank_name_raises_value_error(self, tmp_path):
        from codebeacon.config import load_config
        with pytest.raises(ValueError):
            load_config(self._write(tmp_path, (
                "version: 1\n"
                "projects:\n"
                "  - name:\n"     # present but null
                "    path: proj\n"
                "    type: fastapi\n"
            )))

    def test_blank_path_raises_value_error(self, tmp_path):
        from codebeacon.config import load_config
        with pytest.raises(ValueError):
            load_config(self._write(tmp_path, (
                "version: 1\n"
                "projects:\n"
                "  - name: proj\n"
                "    path:\n"     # present but null
            )))

    def test_sync_on_blank_name_exits_cleanly(self, monkeypatch, tmp_path, capsys):
        """The real user-facing failure: `codebeacon sync` must report a
        friendly config error and exit 1, not crash with a TypeError."""
        (tmp_path / "proj").mkdir()
        cfg = self._write(tmp_path, (
            "version: 1\n"
            "projects:\n"
            "  - name:\n"
            "    path: proj\n"
            "    type: fastapi\n"
        ))
        # the pipeline must never be reached for a malformed config
        monkeypatch.setattr(cli, "run_pipeline", lambda *a, **k: 0)
        rc = cli._cmd_sync(argparse.Namespace(
            config=str(cfg), no_rediscover=True, semantic=False,
        ))
        assert rc == 1
        assert "Error loading config" in capsys.readouterr().err


# ── C4. yaml writers are atomic — a failed write never destroys the file ─────

class TestAtomicYamlWrite:
    ORIGINAL = (
        "version: 1\n"
        "# ---- HAND-CURATED; DO NOT LOSE ----\n"
        "projects:\n"
        "  - name: keep-me\n"
        "    path: /w/keep-me\n"
        "    type: spring-boot\n"
    )

    def test_append_failure_preserves_original(self, monkeypatch, tmp_path):
        import codebeacon.config as config
        cfg = tmp_path / "codebeacon.yaml"
        cfg.write_text(self.ORIGINAL, encoding="utf-8")

        def boom(data, stream, **kw):
            stream.write("# half-written\n")   # partial bytes, like a real interrupt
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(config.yaml, "dump", boom)
        new = [SimpleNamespace(name="scratch", path="/tmp/scratch", framework="python")]
        with pytest.raises(OSError):
            config.append_projects_to_yaml(cfg, new)

        # the original hand-curated config survived intact
        assert cfg.read_text(encoding="utf-8") == self.ORIGINAL
        assert "keep-me" in cfg.read_text(encoding="utf-8")

    def test_generate_config_failure_preserves_existing(self, monkeypatch, tmp_path):
        import codebeacon.config as config
        cfg = tmp_path / "codebeacon.yaml"
        cfg.write_text(self.ORIGINAL, encoding="utf-8")

        def boom(data, stream, **kw):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(config.yaml, "dump", boom)
        projects = [SimpleNamespace(name="p", path="/w/p", framework="python")]
        with pytest.raises(OSError):
            config.generate_config(projects, ".codebeacon", cfg)

        assert cfg.read_text(encoding="utf-8") == self.ORIGINAL

    def test_append_success_still_updates_and_leaves_no_temp(self, tmp_path):
        import codebeacon.config as config
        cfg = tmp_path / "codebeacon.yaml"
        cfg.write_text(self.ORIGINAL, encoding="utf-8")
        config.append_projects_to_yaml(
            cfg, [SimpleNamespace(name="added", path="/w/added", framework="go")]
        )
        text = cfg.read_text(encoding="utf-8")
        assert "keep-me" in text and "added" in text
        assert not (tmp_path / "codebeacon.yaml.tmp").exists()

    def test_symlinked_config_writes_through_to_canonical_target(self, tmp_path):
        """A symlinked codebeacon.yaml (shared/canonical config linked into the
        repo) must keep the symlink AND update the real target — os.replace
        would otherwise clobber the link with a regular file and leave the
        canonical file stale."""
        import os
        import codebeacon.config as config
        canonical = tmp_path / "configs" / "codebeacon.yaml"
        canonical.parent.mkdir(parents=True)
        canonical.write_text(self.ORIGINAL, encoding="utf-8")
        link = tmp_path / "codebeacon.yaml"
        link.symlink_to(canonical)

        config.append_projects_to_yaml(
            link, [SimpleNamespace(name="added", path="/w/added", framework="go")]
        )

        # the symlink is intact (not replaced by a regular file)
        assert link.is_symlink()
        assert os.path.realpath(link) == str(canonical)
        # and the canonical target itself received the update (not left stale)
        canon_text = canonical.read_text(encoding="utf-8")
        assert "keep-me" in canon_text and "added" in canon_text
        # the temp landed next to the real target, and was consumed
        assert not (canonical.parent / "codebeacon.yaml.tmp").exists()

    def test_existing_mode_preserved_across_rewrite(self, tmp_path):
        """A user who chmod 600'd codebeacon.yaml must not have it silently
        relaxed to umask-default 0644 by the temp+replace rewrite."""
        import os
        import stat
        import codebeacon.config as config
        cfg = tmp_path / "codebeacon.yaml"
        cfg.write_text(self.ORIGINAL, encoding="utf-8")
        os.chmod(cfg, 0o600)

        config.append_projects_to_yaml(
            cfg, [SimpleNamespace(name="added", path="/w/added", framework="go")]
        )

        assert stat.S_IMODE(os.stat(cfg).st_mode) == 0o600
        assert "added" in cfg.read_text(encoding="utf-8")


# ── C5. scalar output:/wave:/semantic: sections are config errors ────────────

class TestConfigScalarSections:
    def _write(self, tmp_path, body: str):
        p = tmp_path / "codebeacon.yaml"
        p.write_text(body, encoding="utf-8")
        return p

    BASE = "version: 1\nprojects:\n  - name: app\n    path: .\n"

    @pytest.mark.parametrize("section_line", [
        "output: express\n",   # str
        "wave: fast\n",        # str
        "semantic: on\n",      # YAML 'on' → bool True, still non-mapping
    ])
    def test_scalar_section_raises_value_error(self, tmp_path, section_line):
        from codebeacon.config import load_config
        with pytest.raises(ValueError):
            load_config(self._write(tmp_path, self.BASE + section_line))

    def test_scalar_context_map_raises_value_error(self, tmp_path):
        from codebeacon.config import load_config
        with pytest.raises(ValueError):
            load_config(self._write(
                tmp_path,
                self.BASE + "output:\n  context_map: nope\n",
            ))

    def test_error_message_names_the_offending_key(self, tmp_path):
        from codebeacon.config import load_config
        with pytest.raises(ValueError) as exc:
            load_config(self._write(tmp_path, self.BASE + "output: express\n"))
        assert "output" in str(exc.value)

    def test_null_sections_still_fall_back_to_defaults(self, tmp_path):
        """The scalar guard must not regress the existing null-tolerance."""
        from codebeacon.config import load_config
        cfg = load_config(self._write(tmp_path, (
            self.BASE + "output:\nwave:\nsemantic:\n"
        )))
        assert cfg.output.dir == ".codebeacon"
        assert cfg.wave.chunk_size == 300
        assert cfg.semantic.enabled is False


# ── C6. upgrade fallback recommends the right command for a uv venv ──────────

class TestUpgradeUvVenvFallback:
    def test_is_uv_venv_true_with_marker(self, monkeypatch, tmp_path):
        (tmp_path / "pyvenv.cfg").write_text(
            "home = /x\nuv = 0.8.0\nversion_info = 3.12.11\n", encoding="utf-8"
        )
        monkeypatch.setattr("sys.prefix", str(tmp_path))
        assert cli._is_uv_venv() is True

    def test_is_uv_venv_false_without_marker(self, monkeypatch, tmp_path):
        (tmp_path / "pyvenv.cfg").write_text(
            "home = /x\nversion_info = 3.12.11\n", encoding="utf-8"
        )
        monkeypatch.setattr("sys.prefix", str(tmp_path))
        assert cli._is_uv_venv() is False

    def test_is_uv_venv_false_when_cfg_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.prefix", str(tmp_path))  # no pyvenv.cfg present
        assert cli._is_uv_venv() is False

    def _run(self, monkeypatch, capsys, *, is_uv):
        import importlib.util
        import subprocess
        monkeypatch.setattr(cli, "_detect_install_kind", lambda: "pip")
        monkeypatch.setattr(cli, "_pypi_latest_version", lambda timeout=5.0: "9.9.9")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        monkeypatch.setattr(cli, "_is_uv_venv", lambda: is_uv)
        executed: list = []
        monkeypatch.setattr(
            subprocess, "call", lambda cmd, *a, **k: executed.append(list(cmd)) or 0
        )
        rc = cli._cmd_upgrade(argparse.Namespace(force=False))
        return rc, capsys.readouterr().err, executed

    def test_uv_venv_recommends_uv_pip_install(self, monkeypatch, capsys):
        rc, err, executed = self._run(monkeypatch, capsys, is_uv=True)
        assert rc == 1
        assert executed == []  # cannot upgrade in-process; nothing was run
        assert "uv pip install --upgrade codebeacon" in err
        # must NOT push the pipx/uv-tool commands that fail for a uv venv
        assert "pipx upgrade codebeacon" not in err
        assert "uv tool upgrade codebeacon" not in err

    def test_non_uv_venv_keeps_pipx_uv_tool_advice(self, monkeypatch, capsys):
        rc, err, executed = self._run(monkeypatch, capsys, is_uv=False)
        assert rc == 1
        assert executed == []
        assert "pipx upgrade codebeacon" in err
        assert "uv tool upgrade codebeacon" in err
        assert "uv pip install --upgrade codebeacon" not in err
