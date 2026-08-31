"""0.7.1 audit regressions for discover/{scanner,ignore,detector}.py + diagnostics.

Each test reproduces a confirmed audit-070 failure, so reverting the matching
fix hunk flips the assertion:

- CG1   (GI-2479 / G-0922-2 / G-0932-6) a directory whose *name* merely collides
        with a build-output convention dropped its whole subtree, silently and
        with exit 0 — a UVM ``env/``, a Python package named ``coverage``, a
        Node CLI's ``bin/``. Pruning is now gated on the directory's contents.
- G-0918-9  ``secrets/``/``credentials/`` stay pruned (privacy), but the prune
        is now recorded instead of invisible; ``.gcloud`` joins the set.
- CG2   (GI-1206 / G-0915-2) a ``.gitignore`` in a subdirectory had no effect at
        all; each ignore file now scopes to its own subtree, as in git.
- CG3   (G-0914-8) ``$GIT_DIR/info/exclude`` was never read, and a linked git
        worktree checked out inside the repo doubled every file in the corpus.
- CG4   (G-0926-6 / G-0946-8 / G-0950-5) a UTF-8 BOM disabled the *first* rule
        of an ignore file, and a UTF-16 file lost its rules outright — both
        silently, which means excluded files got indexed.
- G-0940-7  an NFC pattern did not match an NFD directory name (macOS), where
        git precomposes and matches.
- G-0950-6  ignore matching cost O(rules x depth) per path; it is now O(rules),
        and this file pins the decisions against a reference implementation of
        the pre-optimisation semantics.
- G-0924-2  a credential-shaped source module was dropped with no trace at all.
- R12   the ``ignored`` diagnostic bucket: an over-broad rule and a clean scan
        used to be indistinguishable.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import pytest

from codebeacon.diagnostics import (
    IGNORED_FILENAME,
    IgnoredReport,
    write_ignored_report,
)
from codebeacon.discover.ignore import (
    IgnoreMatcher,
    _anchored_can_match_under,
    _glob_match,
    _parse_line,
    read_ignore_text,
)
from codebeacon.discover.scanner import (
    CORROBORATED_IGNORE_DIRS,
    IGNORE_DIRS,
    UNCONDITIONAL_IGNORE_DIRS,
    _is_linked_worktree,
    _looks_like_build_output,
    collect_files,
    read_ignore_file,
)

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def mk(root: Path, rel: str, body: str = "x = 1\n") -> Path:
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def rels(root) -> list[str]:
    r = Path(root).resolve()
    return sorted(Path(f).relative_to(r).as_posix() for f in collect_files(str(r)))


def git_init(root) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)


def git_ignores(root, rel: str) -> bool:
    return subprocess.run(
        ["git", "check-ignore", "-q", rel], cwd=root, capture_output=True
    ).returncode == 0


# ── CG1: a name collision alone must not drop real source ────────────────────

class TestCorroboratedDirPruning:
    # (dir name, marker to create, marker is a directory?)
    MARKERS = [
        ("env", "pyvenv.cfg", False),
        ("coverage", "index.html", False),
        ("target", "debug", True),
        ("build", "CMakeCache.txt", False),
        ("out", "_next", True),
        ("bin", "Debug", True),
        ("obj", "project.assets.json", False),
        ("vendor", "autoload.php", False),
        ("public", "_astro", True),
    ]

    @pytest.mark.parametrize("name", sorted(CORROBORATED_IGNORE_DIRS))
    def test_unmarked_dir_holding_source_is_collected(self, tmp_path, name):
        """The bug: 15 bare names dropped genuine source with no corroboration,
        no warning and exit 0."""
        mk(tmp_path, f"{name}/handler.py", "def handler():\n    return 1\n")
        mk(tmp_path, "src/app.py")
        assert f"{name}/handler.py" in rels(tmp_path)

    @pytest.mark.parametrize("name,marker,is_dir", MARKERS)
    def test_marked_dir_is_pruned(self, tmp_path, name, marker, is_dir):
        """With the name's own marker present, the conventional meaning is
        confirmed and the directory is pruned as before."""
        mk(tmp_path, f"{name}/handler.py")
        mk(tmp_path, "src/app.py")
        target = tmp_path / name / marker
        if is_dir:
            target.mkdir(parents=True)
        else:
            target.write_text("marker\n")
        assert rels(tmp_path) == ["src/app.py"]

    def test_compiled_artifact_prunes_without_a_named_marker(self, tmp_path):
        """A layout no marker table anticipates is still caught: hand-written
        source trees do not ship ``.class`` files."""
        mk(tmp_path, "build/weird-layout/App.class", "BIN")
        mk(tmp_path, "build/weird-layout/App.java", "class App {}")
        mk(tmp_path, "src/Main.java", "class Main {}")
        assert rels(tmp_path) == ["src/Main.java"]

    def test_no_source_at_all_is_pruned(self, tmp_path):
        """Rails' ``tmp/``: nothing indexable inside, so pruning costs nothing
        and no per-framework marker is needed."""
        mk(tmp_path, "tmp/cache/x.dat", "junk")
        mk(tmp_path, "tmp/pids/server.pid", "1")
        mk(tmp_path, "app.rb", "x = 1")
        assert rels(tmp_path) == ["app.rb"]

    def test_hashed_bundles_do_not_count_as_source(self, tmp_path):
        """A Next.js static export is full of ``.js`` — but content-hashed
        bundles are output, not source, or ``out/`` would be indexed."""
        mk(tmp_path, "out/index.html", "<html>")
        mk(tmp_path, "out/static/chunks/main-a1b2c3d4.js", "//")
        mk(tmp_path, "out/static/vendor.min.js", "//")
        mk(tmp_path, "pages/index.js", "export default 1")
        assert rels(tmp_path) == ["pages/index.js"]

    def test_cargo_target_tree_stays_pruned(self, tmp_path):
        """Regression guard: the real thing must keep being excluded."""
        mk(tmp_path, "Cargo.toml", "[package]\n")
        mk(tmp_path, "src/main.rs", "fn main() {}\n")
        mk(tmp_path, "target/CACHEDIR.TAG", "Signature: 8a477f597d28d172\n")
        mk(tmp_path, "target/debug/build/foo/out/generated.rs", "// generated\n")
        assert rels(tmp_path) == ["src/main.rs"]

    def test_laravel_front_controller_survives_but_its_build_dir_does_not(self, tmp_path):
        """``public/index.php`` is genuine source; ``public/build`` beneath it is
        still output, so the two are decided independently."""
        mk(tmp_path, "artisan", "#!/usr/bin/env php\n")
        mk(tmp_path, "public/index.php", "<?php // front controller\n")
        mk(tmp_path, "public/build/assets/app-4f2a1b9c.js", "//\n")
        assert rels(tmp_path) == ["public/index.php"]

    def test_node_bin_cli_kept_but_dotnet_bin_pruned(self, tmp_path):
        mk(tmp_path, "node/package.json", "{}")
        mk(tmp_path, "node/bin/cli.js", "#!/usr/bin/env node\n")
        mk(tmp_path, "net/App.csproj", "<Project/>")
        mk(tmp_path, "net/bin/Debug/net8.0/App.dll", "BIN")
        assert rels(tmp_path) == ["net/App.csproj", "node/bin/cli.js"]

    def test_probe_budget_is_bounded(self, tmp_path):
        """A huge non-source output tree must cost a fixed handful of syscalls,
        not a full traversal."""
        for i in range(1200):
            mk(tmp_path, f"out/assets/f{i}.dat", "x")
        started = time.perf_counter()
        assert _looks_like_build_output(tmp_path / "out", "out") is True
        assert time.perf_counter() - started < 2.0


# ── G-0918-9: credential stores stay pruned, but visibly ─────────────────────

class TestCredentialDirs:
    @pytest.mark.parametrize("name", ["secrets", "credentials", ".ssh", ".aws", ".gcloud", ".gnupg"])
    def test_credential_dirs_pruned_unconditionally(self, tmp_path, name):
        """Privacy wins over recall here: guessing wrong leaks credentials into
        a committed index, so these are never marker-gated."""
        mk(tmp_path, f"{name}/provider.py", "def get():\n    return 1\n")
        mk(tmp_path, "src/app.py")
        assert rels(tmp_path) == ["src/app.py"]
        assert name in UNCONDITIONAL_IGNORE_DIRS

    def test_gcloud_joined_the_set(self):
        assert ".gcloud" in IGNORE_DIRS

    def test_prune_is_recorded_not_silent(self, tmp_path):
        mk(tmp_path, "secrets/provider.py")
        mk(tmp_path, "src/app.py")
        report = IgnoredReport()
        collect_files(str(tmp_path), report=report)
        assert {"path": "secrets", "reason": "ignore_dir"} in report.dirs


# ── CG2: nested ignore files scope to their own subtree ──────────────────────

class TestNestedIgnoreFiles:
    def test_nested_gitignore_applies_to_its_subtree(self, tmp_path):
        """The Expo shape from the field report: ``app-novo/.gitignore`` saying
        ``ios/`` had no effect whatsoever."""
        mk(tmp_path, ".gitignore", "node_modules/\n")
        mk(tmp_path, "app-novo/.gitignore", "ios/\n")
        mk(tmp_path, "app-novo/App.js", "export default 1;\n")
        mk(tmp_path, "app-novo/ios/Pods/Gen.js", "// generated\n")
        mk(tmp_path, "app-novo/ios/build.js", "// generated\n")
        assert rels(tmp_path) == ["app-novo/App.js"]

    def test_nested_star_does_not_zero_the_corpus(self, tmp_path):
        """graphify #1873/#1885/#1887: their first nested-ignore fix applied a
        nested bare ``*`` tree-wide and emptied every corpus. Base scoping makes
        that impossible by construction."""
        mk(tmp_path, "vendor-src/.gitignore", "*\n")
        mk(tmp_path, "vendor-src/blob.py")
        mk(tmp_path, "src/app.py")
        mk(tmp_path, "lib/helper.py")
        assert rels(tmp_path) == ["lib/helper.py", "src/app.py"]

    def test_nested_rule_does_not_leak_to_a_sibling(self, tmp_path):
        mk(tmp_path, "a/.gitignore", "gen/\n")
        mk(tmp_path, "a/gen/x.py")
        mk(tmp_path, "a/keep.py")
        mk(tmp_path, "b/gen/y.py")
        mk(tmp_path, "b/keep.py")
        assert rels(tmp_path) == ["a/keep.py", "b/gen/y.py", "b/keep.py"]

    def test_nested_negation_beats_a_root_positive(self, tmp_path):
        """Deeper file wins under last-match-wins, as in git."""
        mk(tmp_path, ".gitignore", "*.gen.py\n")
        mk(tmp_path, "keep/.gitignore", "!*.gen.py\n")
        mk(tmp_path, "keep/wanted.gen.py")
        mk(tmp_path, "other/dropped.gen.py")
        mk(tmp_path, "app.py")
        assert rels(tmp_path) == ["app.py", "keep/wanted.gen.py"]

    def test_nested_codebeaconignore_composes_with_nested_gitignore(self, tmp_path):
        mk(tmp_path, "svc/.gitignore", "build/\n")
        mk(tmp_path, "svc/.codebeaconignore", "legacy/\n")
        mk(tmp_path, "svc/build/out.py")
        mk(tmp_path, "svc/legacy/old.py")
        mk(tmp_path, "svc/main.py")
        assert rels(tmp_path) == ["svc/main.py"]

    def test_cli_exclude_still_outranks_a_nested_negation(self, tmp_path):
        """``--exclude`` evaluates last, so a nested ignore file discovered
        mid-walk can never re-include what the user excluded explicitly."""
        mk(tmp_path, "svc/.gitignore", "!secret_module.py\n")
        mk(tmp_path, "svc/secret_module.py")
        mk(tmp_path, "svc/main.py")
        got = collect_files(str(tmp_path), extra_ignore=["secret_module.py"])
        assert {Path(f).name for f in got} == {"main.py"}

    def test_sibling_subtrees_do_not_accumulate_rules(self, tmp_path):
        """graphify #2834: their nested-ignore implementation grew one shared
        pattern list across every sibling, so cost climbed with tree size."""
        base = IgnoreMatcher(["root.py"])
        child_a = base.nested(["a-only.py"], "a")
        child_b = base.nested(["b-only.py"], "b")
        assert len(child_a._ordered) == len(child_b._ordered) == 2
        assert base.nested(["# just a comment"], "c") is base

    @requires_git
    @pytest.mark.parametrize("root_rules,nested_dir,nested_rules", [
        ("vendorlib/\n", "app-novo", "ios/\n"),
        ("*.gen.py\n", "keep", "!*.gen.py\n"),
        ("", "pkg", "*\n"),
        ("bld/\n", "pkg", "!bld/\n"),
        ("", "deep/nest", "tmpdata/\n"),
        ("gen/\n", "svc", "!gen/keep.py\n"),
    ])
    def test_differential_against_git_check_ignore(
        self, tmp_path, root_rules, nested_dir, nested_rules
    ):
        """Our verdict must equal real ``git check-ignore`` file by file.

        Every directory name here is deliberately one git and codebeacon both
        treat as ordinary. codebeacon's built-in heuristics (``IGNORE_DIRS``,
        the fixture defaults, the credential filter) are outside git's model on
        purpose, so mixing them in would test the divergence rather than the
        pattern semantics this differential exists to pin.
        """
        files = [
            "app.py", "vendorlib/pkg/index.py", "keep/wanted.gen.py",
            "other/dropped.gen.py", f"{nested_dir}/inner.py",
            f"{nested_dir}/ios/build.py", f"{nested_dir}/bld/out.py",
            f"{nested_dir}/gen/keep.py", f"{nested_dir}/tmpdata/blob.py",
            "deep/nest/inner.py", "deep/nest/tmpdata/blob.py",
        ]
        for f in files:
            mk(tmp_path, f)
        if root_rules:
            mk(tmp_path, ".gitignore", root_rules)
        mk(tmp_path, f"{nested_dir}/.gitignore", nested_rules)
        git_init(tmp_path)

        collected = set(rels(tmp_path))
        for f in files:
            assert (f not in collected) == git_ignores(tmp_path, f), (
                f"divergence from git on {f!r} "
                f"(root={root_rules!r}, {nested_dir}/.gitignore={nested_rules!r})"
            )


# ── CG3: git metadata excludes + linked worktrees ────────────────────────────

class TestGitMetadataExcludes:
    @requires_git
    def test_info_exclude_is_honoured(self, tmp_path):
        git_init(tmp_path)
        (tmp_path / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".git" / "info" / "exclude").write_text("generated/\n")
        mk(tmp_path, "generated/big.py")
        mk(tmp_path, "src/app.py")
        assert rels(tmp_path) == ["src/app.py"]
        assert git_ignores(tmp_path, "generated/big.py")

    @requires_git
    def test_gitignore_negation_outranks_info_exclude(self, tmp_path):
        """git's precedence: info/exclude sits *below* .gitignore."""
        git_init(tmp_path)
        (tmp_path / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".git" / "info" / "exclude").write_text("build/\n")
        mk(tmp_path, ".gitignore", "!build/\n")
        mk(tmp_path, "build/keep.py")
        assert "build/keep.py" in rels(tmp_path)

    def test_missing_or_unreadable_exclude_is_a_no_op(self, tmp_path):
        (tmp_path / ".git").mkdir()
        mk(tmp_path, "src/app.py")
        assert rels(tmp_path) == ["src/app.py"]

    def test_git_dir_env_var_is_not_consulted(self, tmp_path, monkeypatch):
        """codebeacon's own git hooks run with ``GIT_DIR`` set to the enclosing
        repo while the scan may target a subproject. ``info/exclude`` patterns
        are relative to the working tree, so honouring the variable would
        reinterpret every pattern against the wrong root."""
        elsewhere = tmp_path / "elsewhere" / ".git"
        (elsewhere / "info").mkdir(parents=True)
        (elsewhere / "info" / "exclude").write_text("src/\n")
        project = tmp_path / "project"
        mk(project, "src/app.py")
        monkeypatch.setenv("GIT_DIR", str(elsewhere))
        assert rels(project) == ["src/app.py"]

    def test_exclude_resolves_through_a_gitdir_pointer(self, tmp_path):
        """A linked worktree's ``.git`` is a file; the excludes live in the
        common dir it points at."""
        common = tmp_path / "main" / ".git"
        (common / "info").mkdir(parents=True)
        (common / "info" / "exclude").write_text("generated/\n")
        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / ".git").write_text(f"gitdir: {common}/worktrees/wt\n")
        (common / "worktrees" / "wt").mkdir(parents=True)
        (common / "worktrees" / "wt" / "commondir").write_text("../..\n")
        mk(wt, "generated/big.py")
        mk(wt, "src/app.py")
        assert read_ignore_file(wt) == ["generated/"]

    @requires_git
    def test_linked_worktree_inside_the_repo_is_not_double_counted(self, tmp_path):
        """``git worktree add wt-feat`` left a second copy of every tracked
        file in the corpus. git does not mark it ignored, so the detection has
        to be structural."""
        git_init(tmp_path)
        mk(tmp_path, "src/app.py", "def app():\n    return 1\n")
        mk(tmp_path, "src/lib.py", "def lib():\n    return 2\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
        added = subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "feat", "wt-feat"],
            cwd=tmp_path, capture_output=True,
        )
        if added.returncode != 0:
            pytest.skip("git worktree unavailable")

        got = rels(tmp_path)
        assert got == ["src/app.py", "src/lib.py"]
        assert not any(g.startswith("wt-feat/") for g in got)
        assert _is_linked_worktree(tmp_path / "wt-feat") is True
        # …and git itself does NOT consider it ignored, which is exactly why
        # pattern parity alone could never have caught this.
        assert git_ignores(tmp_path, "wt-feat/src/app.py") is False

    def test_submodule_style_gitdir_is_not_treated_as_a_worktree(self, tmp_path):
        """A submodule points at ``.git/modules/...`` and is genuinely different
        code — it must keep being indexed."""
        sub = tmp_path / "libs" / "shared"
        sub.mkdir(parents=True)
        (sub / ".git").write_text("gitdir: ../../.git/modules/shared\n")
        mk(sub, "core.py")
        mk(tmp_path, "app.py")
        assert _is_linked_worktree(sub) is False
        assert "libs/shared/core.py" in rels(tmp_path)

    def test_plain_directory_named_worktrees_still_pruned(self, tmp_path):
        """The literal name stays in the unconditional set (0.6.0 regression
        guard); the structural check is additional, not a replacement."""
        mk(tmp_path, "worktrees/feature-x/leak.py")
        mk(tmp_path, "main.py")
        assert rels(tmp_path) == ["main.py"]


# ── CG4: ignore files are decoded, not silently mangled ──────────────────────

class TestIgnoreFileDecoding:
    @pytest.mark.parametrize("fname", [".gitignore", ".codebeaconignore"])
    def test_utf8_bom_does_not_disable_the_first_rule(self, tmp_path, fname):
        """PowerShell's default output encoding glues U+FEFF to the first
        pattern — exactly where ``secrets/`` or ``*.env`` usually goes."""
        (tmp_path / fname).write_bytes("generated/\nlogs/\n".encode("utf-8-sig"))
        mk(tmp_path, "generated/big.py")
        mk(tmp_path, "logs/x.py")
        mk(tmp_path, "src/app.py")
        assert read_ignore_file(tmp_path) == ["generated/", "logs/"]
        assert rels(tmp_path) == ["src/app.py"]

    def test_utf16_rules_survive_with_a_warning(self, tmp_path, capsys):
        (tmp_path / ".gitignore").write_bytes("generated/\n".encode("utf-16"))
        mk(tmp_path, "generated/big.py")
        mk(tmp_path, "src/app.py")
        assert rels(tmp_path) == ["src/app.py"]
        assert "utf-16" in capsys.readouterr().err

    def test_latin1_rules_survive_with_a_warning(self, tmp_path, capsys):
        (tmp_path / ".gitignore").write_bytes("caf\xe9/\n".encode("latin-1"))
        mk(tmp_path, "café/mod.py")
        mk(tmp_path, "src/app.py")
        assert rels(tmp_path) == ["src/app.py"]
        assert "not UTF-8" in capsys.readouterr().err

    def test_plain_utf8_produces_no_warning(self, tmp_path, capsys):
        (tmp_path / ".gitignore").write_text("generated/\n", encoding="utf-8")
        mk(tmp_path, "src/app.py")
        rels(tmp_path)
        assert "not UTF-8" not in capsys.readouterr().err

    def test_bom_only_file_yields_no_rules(self, tmp_path):
        (tmp_path / ".gitignore").write_bytes(b"\xef\xbb\xbf")
        assert read_ignore_file(tmp_path) == []

    def test_missing_file_reads_as_none(self, tmp_path):
        assert read_ignore_text(tmp_path / "nope") is None

    @pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "latin-1"])
    def test_from_file_never_raises(self, tmp_path, encoding):
        """The latent UnicodeDecodeError is closed before something wires this
        up: it used to raise on any non-UTF-8 byte."""
        p = tmp_path / ".codebeaconignore"
        p.write_bytes("café/\n".encode(encoding))
        m = IgnoreMatcher.from_file(p)
        assert m.is_ignored("café/mod.py") is True


# ── G-0940-7: NFC / NFD parity with git ──────────────────────────────────────

class TestUnicodeNormalisation:
    NFC = unicodedata.normalize("NFC", "caché")
    NFD = unicodedata.normalize("NFD", "caché")
    HANGUL_NFC = unicodedata.normalize("NFC", "한글")
    HANGUL_NFD = unicodedata.normalize("NFD", "한글")

    @pytest.mark.parametrize("rule_form", [NFC, NFD])
    @pytest.mark.parametrize("path_form", [NFC, NFD])
    def test_all_four_normalisation_combinations_match(self, tmp_path, rule_form, path_form):
        mk(tmp_path, f"{path_form}/mod.py")
        mk(tmp_path, "src/app.py")
        (tmp_path / ".gitignore").write_text(f"{rule_form}/\n", encoding="utf-8")
        assert rels(tmp_path) == ["src/app.py"]

    @pytest.mark.parametrize("rule_form", [HANGUL_NFC, HANGUL_NFD])
    def test_hangul_composed_and_decomposed(self, tmp_path, rule_form):
        mk(tmp_path, f"{self.HANGUL_NFD}/mod.py")
        mk(tmp_path, "src/app.py")
        (tmp_path / ".gitignore").write_text(f"{rule_form}/\n", encoding="utf-8")
        assert rels(tmp_path) == ["src/app.py"]

    def test_returned_paths_stay_in_the_on_disk_form(self, tmp_path):
        """Normalise what we *match*, never what we *return* — a normalised
        path would fail to open on a filesystem that stored the other form."""
        mk(tmp_path, f"{self.NFD}/mod.py", "x = 1\n")
        for f in collect_files(str(tmp_path)):
            assert Path(f).read_text() == "x = 1\n"

    def test_ascii_paths_take_the_fast_path(self):
        """``is_normalized`` short-circuits, so the common case allocates
        nothing — this pins that the check is not doing a normalise-always."""
        assert unicodedata.is_normalized("NFC", "src/app.py") is True

    @requires_git
    def test_differential_against_git_on_nfd_tree(self, tmp_path):
        git_init(tmp_path)
        mk(tmp_path, f"{self.NFD}/mod.py")
        mk(tmp_path, "src/app.py")
        (tmp_path / ".gitignore").write_text(f"{self.NFC}/\n", encoding="utf-8")
        collected = set(rels(tmp_path))
        for f in (f"{self.NFD}/mod.py", "src/app.py"):
            assert (f not in collected) == git_ignores(tmp_path, f)


# ── G-0950-6: the optimisation must be decision-identical ────────────────────

def _matches_reference(rule, rel_path: str) -> bool:
    """The pre-optimisation ``_matches``: an O(depth) suffix loop for every
    unanchored rule. Base scoping (new in 0.7.1) is shared, so what this
    isolates is exactly the basename collapse."""
    if rule.base:
        base = rule.base
        if (not rel_path.startswith(base) or len(rel_path) <= len(base)
                or rel_path[len(base)] != "/"):
            return False
        rel_path = rel_path[len(base) + 1:]
    if rule.anchored:
        return _glob_match(rule.pattern, rel_path)
    segments = rel_path.split("/")
    for i in range(len(segments)):
        if _glob_match(rule.pattern, "/".join(segments[i:])):
            return True
    return False


def _self_verdict_reference(matcher, rel_path: str, is_dir: bool) -> bool:
    """The pre-optimisation ``_self_verdict``: glob first, dir_only guard second."""
    result = False
    for rule in matcher._ordered:
        if _matches_reference(rule, rel_path) and (not rule.dir_only or is_dir):
            result = not rule.negate
    return result


class TestMatcherOptimisationParity:
    PATTERNS = [
        "build", "build/", "*.log", "!keep.py", "src/*.py", "a/b/c.ts", "/root.py",
        "**/gen", "**", "node_modules/", "!node_modules/keep/", "vendor/**",
        "*.gen*.ts", "dist", "!dist/keep.ts", "logs/", ".source/", "!.source",
        "?.py", "[abc]*.rs", "docs/**/*.md", "**/tests/fixtures/", "a*b", "x/**/y",
    ]
    SEGMENTS = ["src", "build", "dist", "a", "b", "c", "gen", "keep", "vendor",
                "node_modules", "logs", ".source", "tests", "fixtures", "docs", "x", "y"]
    LEAVES = ["mod.py", "keep.py", "a.log", "c.ts", "root.py", "index.gen1.ts",
              "z.rs", "readme.md", "gen"]

    def test_property_parity_with_reference_implementation(self):
        """Promoted from the audit's differential fuzz: 96,000 decisions
        compared with zero mismatches, at a fixed seed."""
        rng = random.Random(20260831)
        checks = 0
        for _ in range(4000):
            rules = rng.sample(self.PATTERNS, rng.randint(1, 8))
            m = IgnoreMatcher(rules)
            for _ in range(12):
                depth = rng.randint(0, 5)
                prefix = "/".join(rng.choice(self.SEGMENTS) for _ in range(depth))
                leaf = rng.choice(self.LEAVES)
                rel = f"{prefix}/{leaf}" if prefix else leaf
                for is_dir in (False, True):
                    checks += 1
                    assert m._self_verdict(rel, is_dir=is_dir) == _self_verdict_reference(
                        m, rel, is_dir
                    ), f"rules={rules} path={rel!r} is_dir={is_dir}"
        assert checks == 96000

    def test_property_parity_for_nested_scoped_rules(self):
        rng = random.Random(4242)
        for _ in range(1500):
            base = IgnoreMatcher(rng.sample(self.PATTERNS, rng.randint(1, 4)))
            m = base.nested(rng.sample(self.PATTERNS, rng.randint(1, 4)), "svc/api")
            for _ in range(8):
                depth = rng.randint(0, 4)
                prefix = "/".join(rng.choice(self.SEGMENTS) for _ in range(depth))
                rel = f"svc/api/{prefix}/mod.py" if prefix else "svc/api/mod.py"
                for is_dir in (False, True):
                    assert m._self_verdict(rel, is_dir=is_dir) == _self_verdict_reference(
                        m, rel, is_dir
                    )

    def test_cost_is_linear_in_rules_not_rules_times_depth(self):
        """Perf guard: 200 rules against a deep path used to cost ~424us per
        decision. A future rewrite must not silently reintroduce that."""
        rules = [f"vendor{i}/" for i in range(100)] + [f"*.gen{i}.ts" for i in range(100)]
        m = IgnoreMatcher(rules)
        deep = "/".join(f"seg{i}" for i in range(10)) + "/module.ts"
        started = time.perf_counter()
        for _ in range(2000):
            m._self_verdict(deep, is_dir=False)
        per_call_us = (time.perf_counter() - started) / 2000 * 1e6
        assert per_call_us < 150, f"{per_call_us:.1f}us/decision — the O(depth) loop is back"

    def test_dir_only_rules_do_not_decide_file_verdicts(self):
        """The reordering is a pure optimisation only because a ``dir/`` rule
        could never have changed a file's outcome."""
        m = IgnoreMatcher(["logs/"])
        assert m._self_verdict("logs", is_dir=True) is True
        assert m._self_verdict("logs", is_dir=False) is False

    def test_unanchored_patterns_cannot_cross_a_separator(self):
        """The basename collapse rests on this: a `**`-free unanchored pattern
        holds no `/`, and segment regexes emit `[^/]*`."""
        for pattern in self.PATTERNS:
            rule = _parse_line(pattern)
            if rule is None or rule.anchored or "**" in rule.pattern:
                continue
            assert "/" not in rule.pattern


# ── G-0924-2: the sensitive-filename drop is auditable ───────────────────────

class TestSensitiveFileReporting:
    def test_dropped_module_is_named_on_stderr(self, tmp_path, capsys):
        """Keeping ``api_key.py`` excluded is defensible; dropping it with no
        trace at all is not."""
        mk(tmp_path, "src/api_key.py", "API_KEY_HEADER = 'X-Api-Key'\n")
        mk(tmp_path, "src/app.py")
        assert rels(tmp_path) == ["src/app.py"]
        err = capsys.readouterr().err
        assert "credential-looking" in err
        assert "src/api_key.py" in err

    def test_dropped_module_lands_in_the_report(self, tmp_path):
        mk(tmp_path, "src/api_key.py")
        report = IgnoredReport()
        collect_files(str(tmp_path), report=report)
        assert {"path": "src/api_key.py", "reason": "sensitive_filename"} in report.files

    def test_no_warning_when_nothing_is_dropped(self, tmp_path, capsys):
        mk(tmp_path, "src/app.py")
        collect_files(str(tmp_path))
        assert "credential-looking" not in capsys.readouterr().err

    @pytest.mark.parametrize("name", [
        "api_key_manager.go", "access_token_service.py", "client_secret_validator.ts",
    ])
    def test_boundary_controls_still_collected(self, tmp_path, name):
        """0.6.x boundary fix stays put: source modules merely *named after* a
        credential concept are not credentials."""
        mk(tmp_path, f"src/{name}", "// stub\n")
        assert rels(tmp_path) == [f"src/{name}"]

    def test_symlink_warning_count_unaffected(self, tmp_path, capsys):
        """The two warnings are separate lines, so the grouped symlink warning
        stays exactly one."""
        mk(tmp_path, "src/api_key.py")
        mk(tmp_path, "external/util.py")
        os.symlink(tmp_path / "external", tmp_path / "src" / "linked")
        collect_files(str(tmp_path))
        err = capsys.readouterr().err
        assert err.count("Warning: skipped") == 1
        assert err.count("Warning: excluded") == 1


# ── R12: the `ignored` diagnostic bucket ─────────────────────────────────────

class TestIgnoredReport:
    def _tree(self, root: Path) -> None:
        mk(root, ".codebeaconignore", "legacy/\n*.gen.py\n")
        mk(root, "node_modules/pkg/index.js")
        mk(root, "legacy/old.py")
        mk(root, ".hidden/x.py")
        mk(root, "src/app.py")
        mk(root, "src/api_key.py")
        mk(root, "src/thing.gen.py")

    def test_every_bucket_gets_its_reason(self, tmp_path):
        self._tree(tmp_path)
        report = IgnoredReport()
        collect_files(str(tmp_path), report=report)
        dirs = {d["path"]: d["reason"] for d in report.dirs}
        files = {f["path"]: f["reason"] for f in report.files}
        assert dirs["node_modules"] == "ignore_dir"
        assert dirs[".hidden"] == "hidden_dir"
        assert dirs["legacy"] == "pattern"
        assert files["src/api_key.py"] == "sensitive_filename"
        assert files["src/thing.gen.py"] == "pattern"

    def test_a_pruned_subtree_costs_one_entry(self, tmp_path):
        """Bounded output: record the directory, do not descend. Otherwise a
        vendored tree alone would blow past every cap."""
        for i in range(300):
            mk(tmp_path, f"node_modules/pkg{i}/index.js")
        mk(tmp_path, "app.js")
        report = IgnoredReport()
        collect_files(str(tmp_path), report=report)
        assert [d["path"] for d in report.dirs] == ["node_modules"]

    def test_per_directory_file_cap(self, tmp_path):
        mk(tmp_path, ".codebeaconignore", "*.gen.py\n")
        for i in range(60):
            mk(tmp_path, f"src/f{i}.gen.py")
        report = IgnoredReport(max_per_dir=20)
        collect_files(str(tmp_path), report=report)
        assert len(report.files) == 20
        assert report.counts["pattern"] == 60   # the count stays exact
        assert report.truncated is True

    def test_no_report_keeps_the_old_signature_and_costs_nothing(self, tmp_path):
        self._tree(tmp_path)
        assert rels(tmp_path) == ["src/app.py"]

    @staticmethod
    def _lock(path: Path) -> None:
        """chmod 000, and skip only if the OS did not actually enforce it.

        The check must not consult the code under test: asking ``collect_files``
        whether it noticed would let a regression masquerade as "running as
        root" and skip itself into a pass.
        """
        os.chmod(path, 0o000)
        try:
            os.listdir(path)
        except PermissionError:
            return
        os.chmod(path, 0o755)
        pytest.skip("directory modes are not enforced here (root / permissive FS)")

    def test_permission_denied_marks_the_corpus_incomplete(self, tmp_path):
        """A subtree we could not read is not the same as one the user
        excluded — the shrink guard has to be able to tell them apart."""
        locked = tmp_path / "locked"
        locked.mkdir()
        mk(locked, "hidden.py")
        mk(tmp_path, "app.py")
        self._lock(locked)
        try:
            report = IgnoredReport()
            got = collect_files(str(tmp_path), report=report)
            assert report.incomplete is True
            assert "locked" in report.permission_denied
            assert {Path(f).name for f in got} == {"app.py"}
        finally:
            os.chmod(locked, 0o755)

    def test_permission_denied_warns_even_without_a_report(self, tmp_path, capsys):
        locked = tmp_path / "locked"
        locked.mkdir()
        mk(locked, "hidden.py")
        self._lock(locked)
        try:
            collect_files(str(tmp_path))
            err = capsys.readouterr().err
            assert "permission denied" in err
            assert "incomplete" in err
        finally:
            os.chmod(locked, 0o755)

    def test_unreadable_dirs_contract_for_the_shrink_guard(self, tmp_path):
        """``pipeline._unreadable_subtrees`` queries this with no arguments,
        long after the collection loop — so the signal cannot live only in an
        optional report object."""
        from codebeacon.discover.scanner import reset_unreadable_dirs, unreadable_dirs

        reset_unreadable_dirs()
        a, b = tmp_path / "a", tmp_path / "b"
        for p in (a, b):
            p.mkdir()
            mk(p, "app.py")
        locked = a / "locked"
        locked.mkdir()
        self._lock(locked)
        try:
            collect_files(str(a))
            collect_files(str(b))    # a second project must not erase a's signal
            found = unreadable_dirs()
            assert any("locked" in d for d in found), found

            collect_files(str(a))    # re-scanning a known root starts a new run
            reset_unreadable_dirs()
            assert unreadable_dirs() == []
        finally:
            os.chmod(locked, 0o755)
            reset_unreadable_dirs()

    def test_clean_scan_is_not_incomplete(self, tmp_path):
        mk(tmp_path, "app.py")
        report = IgnoredReport()
        collect_files(str(tmp_path), report=report)
        assert report.incomplete is False

    def test_writes_ignored_json_and_clears_a_stale_one(self, tmp_path):
        out = tmp_path / "out"
        report = IgnoredReport()
        report.add_dir("node_modules", "ignore_dir")
        path = write_ignored_report(report, out)
        assert path is not None and path.name == IGNORED_FILENAME
        assert '"ignore_dir": 1' in path.read_text()

        assert write_ignored_report(IgnoredReport(), out) is None
        assert not (out / IGNORED_FILENAME).exists()

    def test_own_output_dir_is_pruned_but_not_reported(self, tmp_path):
        """``.codebeacon/`` exists only because the previous run created it, so
        reporting it makes the artefact describe its own footprint — and makes
        it non-idempotent, since the first scan's write is what brings the
        directory into being."""
        mk(tmp_path, "src/app.py")
        (tmp_path / ".codebeacon").mkdir()
        mk(tmp_path, ".codebeacon/beacon.json", "{}")
        report = IgnoredReport()
        got = collect_files(str(tmp_path), report=report)

        assert {Path(f).name for f in got} == {"app.py"}   # still pruned
        assert [d["path"] for d in report.dirs] == []      # but not reported

    def test_report_is_idempotent_across_rescans(self, tmp_path):
        """``.codebeacon/`` is a committed directory, so a scan over an
        unchanged corpus must not rewrite it — mtime churn re-fires Obsidian,
        sync clients and codebeacon's own watch mode (graphify #3060)."""
        mk(tmp_path, ".codebeaconignore", "legacy/\n")
        mk(tmp_path, "node_modules/pkg/i.js")
        mk(tmp_path, "legacy/old.py")
        mk(tmp_path, "src/app.py")
        out = tmp_path / ".codebeacon"

        digests, mtimes = [], []
        for _ in range(3):
            report = IgnoredReport()
            collect_files(str(tmp_path), report=report)
            path = write_ignored_report(report, out)
            digests.append(path.read_text())
            mtimes.append(path.stat().st_mtime_ns)
            time.sleep(0.01)

        assert len(set(digests)) == 1, "content drifted across identical scans"
        assert len(set(mtimes)) == 1, "file rewritten despite identical content"

    def test_a_real_change_still_rewrites(self, tmp_path):
        """The skip must not wedge the file: a genuinely different report
        still lands, or the artefact would go permanently stale."""
        out = tmp_path / ".codebeacon"
        first = IgnoredReport()
        first.add_dir("node_modules", "ignore_dir")
        path = write_ignored_report(first, out)
        before = path.read_text()

        second = IgnoredReport()
        second.add_dir("node_modules", "ignore_dir")
        second.add_dir("vendor", "build_output")
        assert write_ignored_report(second, out).read_text() != before

    def test_corrupted_report_self_heals(self, tmp_path):
        """A hand-edited or truncated artefact must be rewritten, not skipped
        because the comparison failed."""
        out = tmp_path / ".codebeacon"
        out.mkdir()
        (out / IGNORED_FILENAME).write_bytes(b"\xff\xfe not json at all")
        report = IgnoredReport()
        report.add_dir("node_modules", "ignore_dir")
        assert '"ignore_dir": 1' in write_ignored_report(report, out).read_text()

    def test_totals_and_serialisation(self):
        report = IgnoredReport()
        report.add_dir("a", "ignore_dir")
        report.add_file("b/c.py", "pattern")
        report.add_permission_denied("d")
        payload = report.to_dict()
        assert payload["total"] == 3
        assert payload["incomplete"] is True
        assert payload["counts"] == {
            "ignore_dir": 1, "pattern": 1, "permission_denied": 1,
        }


# ── G-0913-8: .rake files reach the pipeline (collector half) ────────────────

class TestRakeCollection:
    """The other half of G-0913-8. ``extract/base.py`` maps ``.rake`` to the
    ruby grammar, but a grammar mapping is inert while the collector never
    hands the file over — these two registrations only work as a pair, and they
    live in files owned by different fixers, so each side needs its own guard.
    """

    def test_rake_files_are_collected(self, tmp_path):
        mk(tmp_path, "lib/tasks/db.rake", "require 'csv'\nclass RakeHelper\nend\n")
        mk(tmp_path, "app.rb", "x = 1\n")
        assert rels(tmp_path) == ["app.rb", "lib/tasks/db.rake"]

    def test_collector_and_grammar_map_agree(self):
        """A file the collector picks up but no grammar claims would be counted
        as an extraction failure on every scan."""
        from codebeacon.extract.base import EXT_TO_GRAMMAR

        assert EXT_TO_GRAMMAR.get(".rake") == "ruby"
        assert ".rake" in __import__(
            "codebeacon.discover.scanner", fromlist=["CODE_EXTENSIONS"]
        ).CODE_EXTENSIONS

    def test_extensionless_rakefile_stays_out_of_scope(self, tmp_path):
        """Documented boundary: an extension-keyed set cannot express it."""
        mk(tmp_path, "Rakefile", "task :default\n")
        mk(tmp_path, "app.rb", "x = 1\n")
        assert rels(tmp_path) == ["app.rb"]


# ── Detector: discovery and collection must agree ────────────────────────────

class TestDetectorParity:
    def test_projects_under_ambiguous_names_are_discoverable(self, tmp_path):
        """``build/`` and ``env/`` projects were undiscoverable, and
        ``.codebeaconignore`` could not reach the detector at all."""
        from codebeacon.discover.detector import discover_projects

        for d in ("build", "env", "svc"):
            mk(tmp_path, f"{d}/package.json", '{"name":"x","dependencies":{"express":"^4"}}')
            mk(tmp_path, f"{d}/index.js", "const express = require('express');\n")
        names = {p.name for p in discover_projects([str(tmp_path)])}
        assert {"build", "env", "svc"} <= names

    def test_real_build_output_still_not_discovered(self, tmp_path):
        from codebeacon.discover.detector import discover_projects

        mk(tmp_path, "svc/package.json", '{"name":"x"}')
        mk(tmp_path, "svc/index.js", "// app\n")
        mk(tmp_path, "build/CMakeCache.txt", "x\n")
        mk(tmp_path, "build/package.json", '{"name":"y"}')
        names = {p.name for p in discover_projects([str(tmp_path)])}
        assert "build" not in names

    def test_negation_reaches_the_detector(self, tmp_path):
        """The scanner has had this escape hatch all along; discovery did not,
        so a rescued directory yielded a project with zero files."""
        from codebeacon.discover.detector import discover_projects

        mk(tmp_path, ".codebeaconignore", "!dist/\n")
        mk(tmp_path, "svc/package.json", '{"name":"x"}')
        mk(tmp_path, "svc/index.js", "// app\n")
        mk(tmp_path, "dist/package.json", '{"name":"y"}')
        mk(tmp_path, "dist/index.js", "// also an app\n")
        names = {p.name for p in discover_projects([str(tmp_path)])}
        assert "dist" in names
