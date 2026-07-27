"""Dependency metadata checks for runtime/dev separation."""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_ONLY_PACKAGES = {"pytest", "pytest-asyncio", "ruff", "pyright"}


def _dependency_name(requirement: str) -> str:
    name = requirement
    for separator in ("[", ">", "<", "=", "~", "!", ";"):
        name = name.split(separator, 1)[0]
    return name.strip().lower()


def _load_pyproject() -> dict:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_runtime_dependencies_exclude_dev_tools() -> None:
    pyproject = _load_pyproject()
    runtime_dependencies = {
        _dependency_name(dependency)
        for dependency in pyproject["project"].get("dependencies", [])
    }

    assert DEV_ONLY_PACKAGES.isdisjoint(runtime_dependencies)


def test_dev_dependency_metadata_keeps_dev_tools_available() -> None:
    pyproject = _load_pyproject()
    dependency_groups = pyproject.get("dependency-groups", {})
    optional_dependencies = pyproject["project"].get("optional-dependencies", {})
    dev_dependencies = {
        _dependency_name(dependency)
        for dependency in [
            *dependency_groups.get("dev", []),
            *optional_dependencies.get("dev", []),
        ]
    }

    assert dev_dependencies >= DEV_ONLY_PACKAGES
