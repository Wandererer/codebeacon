"""Shared pytest fixtures for codebeacon tests."""
from __future__ import annotations

from pathlib import Path
import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def spring_fixture(fixtures_dir) -> Path:
    return fixtures_dir / "spring_boot" / "UserController.java"


@pytest.fixture
def fastapi_fixture(fixtures_dir) -> Path:
    return fixtures_dir / "fastapi" / "main.py"


@pytest.fixture
def django_fixture(fixtures_dir) -> Path:
    return fixtures_dir / "django" / "views.py"


@pytest.fixture
def flask_fixture(fixtures_dir) -> Path:
    return fixtures_dir / "flask" / "app.py"


@pytest.fixture
def express_fixture(fixtures_dir) -> Path:
    return fixtures_dir / "express" / "userRouter.js"


@pytest.fixture
def nestjs_fixture(fixtures_dir) -> Path:
    return fixtures_dir / "nestjs" / "user.controller.ts"
