"""``_is_sensitive_filename`` + sensitive-dir handling in collect_files.

Mirrors graphify 0.8.12's _is_sensitive hardening: credential files and
secret directories must be skipped even when they share an extension with
code (and even when they don't start with ``.``).
"""

from __future__ import annotations

from pathlib import Path

from codebeacon.discover.scanner import (
    IGNORE_DIRS,
    _is_sensitive_filename,
    collect_files,
)


def test_sensitive_basename_credentials_json():
    assert _is_sensitive_filename("credentials.json") is True
    assert _is_sensitive_filename("service-account.json") is True


def test_sensitive_underscore_prefix():
    assert _is_sensitive_filename("api_token.txt") is True
    assert _is_sensitive_filename("oauth_token.json") is True
    assert _is_sensitive_filename("access_token.json") is True


def test_sensitive_hyphen_prefix():
    assert _is_sensitive_filename("slack-secret-key.yml") is True
    assert _is_sensitive_filename("client-secret.json") is True


def test_sensitive_case_insensitive():
    assert _is_sensitive_filename("API_TOKEN.TXT") is True
    assert _is_sensitive_filename("OAuth_Token.json") is True


def test_innocent_names_not_flagged():
    assert _is_sensitive_filename("token_bucket.ts") is False
    assert _is_sensitive_filename("UserService.ts") is False
    assert _is_sensitive_filename("config.json") is False
    assert _is_sensitive_filename("package.json") is False


def test_secrets_and_credentials_dirs_in_ignore_set():
    assert "secrets" in IGNORE_DIRS
    assert "credentials" in IGNORE_DIRS
    assert ".ssh" in IGNORE_DIRS
    assert ".aws" in IGNORE_DIRS


def test_collect_files_skips_sensitive_filenames(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "main.ts").write_text("console.log('hi')", encoding="utf-8")
    (root / "src" / "api_token.json").write_text("{}", encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "leaked.ts").write_text("hello", encoding="utf-8")

    files = collect_files(root)
    rel = {Path(f).relative_to(root).as_posix() for f in files}
    assert "src/main.ts" in rel
    # api_token.json is .json — not in CODE_EXTENSIONS anyway — but the
    # sensitive check must also fire on its own merit; here we assert that
    # nothing under secrets/ leaks even though leaked.ts has a code ext.
    assert not any(p.startswith("secrets/") for p in rel)


def test_collect_files_skips_secrets_dir(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "credentials").mkdir()
    (root / "credentials" / "stash.ts").write_text("evil", encoding="utf-8")
    files = collect_files(root)
    rel = {Path(f).relative_to(root).as_posix() for f in files}
    assert not any(p.startswith("credentials/") for p in rel)
