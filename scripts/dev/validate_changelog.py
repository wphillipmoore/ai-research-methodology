#!/usr/bin/env python3
"""Validate that CHANGELOG.md contains an entry for the current version."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def load_version() -> str:
    """Load the version from pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.is_file():
        message = "Run from the repository root (pyproject.toml missing)."
        raise SystemExit(message)
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project_section = data.get("project")
    if not isinstance(project_section, dict):
        message = "Missing [project] section in pyproject.toml."
        raise SystemExit(message)
    version_value = project_section.get("version")
    if not isinstance(version_value, str):
        message = "Missing or invalid project.version in pyproject.toml."
        raise SystemExit(message)
    return version_value


def main() -> int:
    version = load_version()

    changelog_path = Path("CHANGELOG.md")
    if not changelog_path.is_file():
        print(f"FAIL: CHANGELOG.md not found (expected entry for {version}).")
        return 1

    content = changelog_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^## \[{re.escape(version)}\]", re.MULTILINE)

    if pattern.search(content):
        print(f"OK: CHANGELOG.md contains entry for {version}.")
        return 0

    print(f"FAIL: CHANGELOG.md has no entry for {version}.")
    print("Run git-cliff to update the changelog before releasing.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
