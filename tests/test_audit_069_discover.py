"""0.6.9 audit regressions for discover/scanner.py (+ discover/ignore.py).

Each test reproduces a confirmed audit-069 failure so reverting the matching
fix hunk flips the assertion:

- C12   gitignore negation semantics: git's "cannot re-include a file if a
        parent directory of that file is excluded" rule was missing, so
        ``dir/`` + ``!dir/keep`` wrongly rescued ``keep``. 0.6.9 matches
        ``git check-ignore`` on all rule sets; the git idiom ``dir/*`` +
        ``!dir/keep`` (exclude *contents*, keep the dir) still rescues.
- G02   uppercase / mixed-case code extensions were silently dropped at the
        collection gate (case-sensitive ``entry.suffix`` vs lowercase set).
- G03   the sensitive-filename heuristic over-matched source modules named
        after a credential concept (``api_key_manager.go``).
- BH-D1  a non-UTF-8 byte anywhere in ``.gitignore`` / ``.codebeaconignore``
        raised UnicodeDecodeError and aborted the whole scan.
- BH-D3  symlinks are (still) skipped, but the drop is no longer silent — one
        grouped warning names the skipped links.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from codebeacon.discover.ignore import IgnoreMatcher
from codebeacon.discover.scanner import (
    collect_files,
    read_ignore_file,
    _is_sensitive_filename,
)


# ── C12: cannot re-include under an excluded parent directory ────────────────

class TestNegationUnderExcludedParent:
    @pytest.mark.parametrize("rules,path,want", [
        # Excluded *directory* is sticky — a self-negation cannot rescue (git:
        # "It is not possible to re-include a file if a parent directory of
        # that file is excluded").
        (["dir/", "!dir/keep.txt"], "dir/keep.txt", True),
        (["logs/", "!logs/important.py"], "logs/important.py", True),
        (["**/temp/", "!**/temp/save.txt"], "a/temp/save.txt", True),
        (["node_modules/", "!node_modules/keep/", "!node_modules/keep/**"],
         "node_modules/keep/deep/b.js", True),
        # `*` ignores the top-level dir itself, so `!important/**` alone
        # cannot rescue anything beneath it.
        (["*", "!important/**"], "important/keep.py", True),
        (["*", "!important/**"], "important/sub/deep.py", True),
        # Git idioms that DO rescue: exclude contents (`dir/*`), or re-include
        # the dir itself first (`!important` before `!important/**`).
        (["dir/*", "!dir/keep.txt"], "dir/keep.txt", False),
        (["dir/*", "!dir/keep.txt"], "dir/other.txt", True),
        (["*", "!important", "!important/**"], "important/keep.py", False),
        (["*", "!important", "!important/**"], "important/sub/deep.py", False),
        # codesight #42 stays intact: parent-level `!.source` re-includes
        # `.source` itself, the deeper positive rule still self-matches.
        ([".source/testfolder", "!.source"], ".source/keep.py", False),
        ([".source/testfolder", "!.source"], ".source/testfolder/skip.py", True),
    ])
    def test_matcher_git_semantics(self, rules, path, want):
        assert IgnoreMatcher(rules).is_ignored(path, is_dir=False) == want

    def test_end_to_end_no_rescue_under_excluded_dir(self, tmp_path):
        (tmp_path / ".gitignore").write_text("dir/\n!dir/keep.py\n")
        (tmp_path / "dir").mkdir()
        (tmp_path / "dir" / "keep.py").write_text("x = 1\n")
        (tmp_path / "dir" / "other.py").write_text("x = 1\n")
        (tmp_path / "main.py").write_text("x = 1\n")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "main.py" in names
        assert "keep.py" not in names, "git: no re-include under an excluded dir"
        assert "other.py" not in names

    @pytest.mark.parametrize("ignore_file", [".gitignore", ".codebeaconignore"])
    def test_end_to_end_contents_idiom_still_rescues(self, tmp_path, ignore_file):
        """The escape hatch works via either ignore file: ``dir/*`` +
        ``!dir/keep.py`` rescues exactly as in git."""
        (tmp_path / ignore_file).write_text("dir/*\n!dir/keep.py\n")
        (tmp_path / "dir").mkdir()
        (tmp_path / "dir" / "keep.py").write_text("x = 1\n")
        (tmp_path / "dir" / "other.py").write_text("x = 1\n")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "keep.py" in names
        assert "other.py" not in names

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    @pytest.mark.parametrize("rules", [
        ["dir/", "!dir/keep.txt"],
        ["dir/*", "!dir/keep.txt"],
        ["*", "!important/**"],
        ["*", "!important", "!important/**"],
        ["logs/", "!logs/important.py"],
        ["node_modules/", "!node_modules/keep/", "!node_modules/keep/**"],
        [".source/", "!.source"],
        [".source/testfolder/", "!.source"],
    ])
    def test_differential_against_git_check_ignore(self, tmp_path, rules):
        """IgnoreMatcher must agree with real ``git check-ignore`` per file."""
        files = [
            "a.txt", "dir/keep.txt", "dir/other.txt",
            "important/keep.py", "important/sub/deep.py",
            "logs/important.py", "logs/debug.py",
            "node_modules/keep/a.js", "node_modules/pkg/index.js",
            ".source/x.txt", ".source/testfolder/y.txt",
        ]
        for f in files:
            p = tmp_path / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        (tmp_path / ".gitignore").write_text("\n".join(rules) + "\n")
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        m = IgnoreMatcher(rules)
        for f in files:
            git_ignored = subprocess.run(
                ["git", "check-ignore", "-q", f], cwd=tmp_path
            ).returncode == 0
            assert m.is_ignored(f, is_dir=False) == git_ignored, (
                f"divergence from git on {f!r} with rules {rules}"
            )


# ── G02: case-insensitive extension matching ─────────────────────────────────

class TestUppercaseExtensions:
    def test_uppercase_and_mixed_case_extensions_collected(self, tmp_path):
        """``App.PY`` / ``Index.JS`` / ``Page.TSX`` / ``Query.SQL`` / ``Bar.Java``
        are valid importable source on case-insensitive filesystems and must be
        collected, not dropped by a case-sensitive suffix test."""
        for fname in ("App.PY", "Index.JS", "Page.TSX", "Query.SQL", "Bar.Java"):
            (tmp_path / fname).write_text("// stub\n")
        # lowercase controls
        (tmp_path / "app_lower.py").write_text("x = 1\n")
        (tmp_path / "index_lower.js").write_text("// js\n")

        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert {
            "App.PY", "Index.JS", "Page.TSX", "Query.SQL", "Bar.Java",
            "app_lower.py", "index_lower.js",
        } <= names

    def test_uppercase_non_code_extension_still_excluded(self, tmp_path):
        """Lowercasing only *adds* matches for code extensions — a non-code
        extension (``.MD``) stays excluded."""
        (tmp_path / "README.MD").write_text("# readme\n")
        (tmp_path / "keep.py").write_text("x = 1\n")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "README.MD" not in names
        assert "keep.py" in names


# ── G03: sensitive-filename heuristic must not eat source modules ────────────

class TestSensitiveFilenamePrecision:
    # Source modules merely *named after* a credential concept — must be KEPT.
    _SOURCE_MODULES = [
        "api_key_manager.go",
        "access_token_service.py",
        "refresh_token_repository.ts",
        "client_secret_validator.ts",
        "private_key_loader.go",
        "secret_key_rotation.py",
        "apikey_store.go",
    ]

    # Files that genuinely *are* a secret — must stay flagged/dropped.
    _REAL_SECRETS = [
        "api_key.txt",
        "api_token.txt",
        "oauth_token.json",
        "access_token.json",
        "client-secret.json",
        "private_key.pem",
        "slack-secret-key.yml",
    ]

    @pytest.mark.parametrize("name", _SOURCE_MODULES)
    def test_source_module_named_after_concept_not_flagged(self, name):
        assert _is_sensitive_filename(name) is False, name

    @pytest.mark.parametrize("name", _REAL_SECRETS)
    def test_real_secret_still_flagged(self, name):
        assert _is_sensitive_filename(name) is True, name

    def test_camelcase_and_bareword_still_kept(self):
        # (documenting the already-immune cases so the boundary stays put)
        assert _is_sensitive_filename("ApiKeyManager.go") is False
        assert _is_sensitive_filename("token_service.ts") is False
        assert _is_sensitive_filename("secret_manager.go") is False

    def test_collect_files_keeps_credential_named_source(self, tmp_path):
        """End-to-end: a real ``api_key_manager.go`` source file lands in the
        index, while a genuine ``private_key.rb`` secret (also a code ext) is
        still dropped."""
        (tmp_path / "api_key_manager.go").write_text("package auth\n")
        (tmp_path / "client_secret_validator.ts").write_text("export const x=1\n")
        (tmp_path / "private_key.rb").write_text("SECRET = 'x'\n")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "api_key_manager.go" in names
        assert "client_secret_validator.ts" in names
        assert "private_key.rb" not in names


# ── BH-D1: non-UTF-8 ignore file must not crash the scan ─────────────────────

# raw latin-1 comment byte (0xe9) followed by a genuine rule
_LATIN1_IGNORE = b"# commentaire \xe9dit\xe9 en latin-1\n*.log\n"


class TestNonUtf8IgnoreFile:
    def test_gitignore_with_non_utf8_byte_does_not_crash(self, tmp_path):
        (tmp_path / ".gitignore").write_bytes(_LATIN1_IGNORE)
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "debug.log").write_text("noise\n")
        # Must not raise UnicodeDecodeError, and the valid `*.log` rule still
        # applies (debug.log is not a code ext, so assert via read_ignore_file).
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "main.py" in names

    def test_codebeaconignore_with_non_utf8_byte_does_not_crash(self, tmp_path):
        (tmp_path / ".codebeaconignore").write_bytes(
            b"# note \xe9\nskip_me.py\n"
        )
        (tmp_path / "skip_me.py").write_text("x = 1\n")
        (tmp_path / "keep.py").write_text("x = 1\n")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "keep.py" in names
        assert "skip_me.py" not in names  # the valid rule after the bad byte held

    def test_read_ignore_file_replaces_bad_bytes_and_keeps_valid_rules(self, tmp_path):
        (tmp_path / ".gitignore").write_bytes(_LATIN1_IGNORE)
        lines = read_ignore_file(tmp_path)
        # The valid rule survives; the bad comment line degraded, not crashed.
        assert "*.log" in lines
        assert any(line.startswith("#") for line in lines)


# ── BH-D3: symlinks skipped but named in one grouped warning ─────────────────

class TestSymlinkWarning:
    def _build(self, root: Path) -> None:
        shared_src = root / "shared-lib" / "src"
        shared_src.mkdir(parents=True)
        (shared_src / "PaymentService.java").write_text("public class PaymentService {}\n")
        app_src = root / "app" / "src"
        app_src.mkdir(parents=True)
        (app_src / "AppController.java").write_text("public class AppController {}\n")
        # directory symlink -> external shared source
        os.symlink(os.path.relpath(shared_src, app_src), app_src / "shared")
        # file symlink -> external real .java
        libs = root / "libs"
        libs.mkdir()
        (libs / "Util.java").write_text("public class Util {}\n")
        os.symlink(os.path.relpath(libs / "Util.java", app_src), app_src / "UtilLink.java")

    def test_symlinks_skipped_but_warned_once(self, tmp_path, capsys):
        self._build(tmp_path)
        app = tmp_path / "app"
        names = {Path(f).name for f in collect_files(str(app))}
        # still not followed
        assert names == {"AppController.java"}

        err = capsys.readouterr().err
        assert "Warning" in err
        assert "symlink" in err.lower()
        assert "not followed" in err
        # both the dir symlink and the file symlink are named, once
        assert "src/shared" in err
        assert "src/UtilLink.java" in err
        assert err.count("Warning: skipped") == 1

    def test_no_symlinks_no_warning(self, tmp_path, capsys):
        (tmp_path / "main.py").write_text("x = 1\n")
        collect_files(str(tmp_path))
        assert "symlink" not in capsys.readouterr().err.lower()

    def test_non_code_file_symlink_not_named(self, tmp_path, capsys):
        """A file symlink to a non-code target is incidental — skip it silently
        (no code lost) rather than adding noise to the grouped warning."""
        (tmp_path / "notes.md").write_text("# notes\n")
        (tmp_path / "main.py").write_text("x = 1\n")
        os.symlink(tmp_path / "notes.md", tmp_path / "LinkedNotes.md")
        collect_files(str(tmp_path))
        assert "symlink" not in capsys.readouterr().err.lower()

    def test_pruned_dir_symlinks_not_named(self, tmp_path, capsys):
        """A directory symlink whose name would be pruned anyway — IGNORE_DIRS
        content (``node_modules``/``dist``) or a hidden dir — must NOT be
        reported as lost 'shared code': the warning fires BEFORE the walk's
        prune, so it would name links a real dir of that name never yields
        (BH-D3). A legit ``src`` link carrying code still warns."""
        real = tmp_path / "external" / "real_shared"  # outside the scanned root
        real.mkdir(parents=True)
        (real / "lib.js").write_text("x = 1\n")
        app = tmp_path / "app"
        app.mkdir()
        (app / "main.py").write_text("x = 1\n")
        os.symlink(real, app / "node_modules")  # IGNORE_DIRS -> pruned
        os.symlink(real, app / "dist")          # IGNORE_DIRS -> pruned
        os.symlink(real, app / ".cache_link")   # hidden dir -> pruned
        os.symlink(real, app / "src")           # not ignored -> warned

        names = {Path(f).name for f in collect_files(str(app))}
        assert names == {"main.py"}  # nothing followed

        err = capsys.readouterr().err
        assert "src" in err
        assert "node_modules" not in err
        assert "dist" not in err
        assert ".cache_link" not in err
        assert err.count("Warning: skipped") == 1

    def test_ignore_matched_symlinks_not_named(self, tmp_path, capsys):
        """A symlink the ignore matcher would drop (dir rule or a file rule) is
        pruned by the real walk, so it must not appear in the warning either —
        only a non-ignored link is named."""
        external = tmp_path / "external"
        external.mkdir()
        (external / "old.js").write_text("x = 1\n")
        (external / "util.js").write_text("x = 1\n")
        app = tmp_path / "app"
        app.mkdir()
        (app / ".codebeaconignore").write_text("legacy/\n*.gen.js\n")
        (app / "main.py").write_text("x = 1\n")
        os.symlink(external, app / "legacy")                     # dir rule -> silent
        os.symlink(external / "util.js", app / "bundle.gen.js")  # file rule -> silent
        os.symlink(external, app / "keep")                       # not ignored -> warned

        collect_files(str(app))
        err = capsys.readouterr().err
        assert "keep" in err
        assert "legacy" not in err
        assert "bundle.gen.js" not in err
