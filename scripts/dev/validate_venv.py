#!/usr/bin/env python3
"""Validate that the local virtual environment is usable after moves or rebuilds."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REQUIRED_TOOLS: tuple[str, ...] = ("pip-audit", "ruff", "mypy", "ty", "pytest")
UV_VERSION = "0.10.4"


def ensure_project_root() -> None:
    """Fail fast if invoked outside the repository root."""
    if not Path("pyproject.toml").is_file():
        message = "Run from the repository root (pyproject.toml missing)."
        raise SystemExit(message)


def validate_uv_version() -> None:
    """Ensure uv is installed and matches the pinned version."""
    uv_path = shutil.which("uv")
    if not uv_path:
        message = (
            f"Missing uv executable. Install uv {UV_VERSION} (for example: python3 -m pip install uv=={UV_VERSION})."
        )
        raise SystemExit(message)
    result = subprocess.run((uv_path, "--version"), check=True, text=True, capture_output=True)  # noqa: S603
    version_output = result.stdout.strip()
    if not version_output.startswith("uv "):
        message = f"Unexpected uv version output: {version_output}"
        raise SystemExit(message)
    version_value = version_output.split()[1]
    if version_value != UV_VERSION:
        message = f"uv version mismatch. Expected {UV_VERSION}, found {version_value}."
        raise SystemExit(message)


def read_shebang(script_path: Path) -> str | None:
    """Return the shebang line without '#!' or None if absent."""
    with script_path.open("rb") as handle:
        first_line = handle.readline().decode("utf-8", errors="replace").strip()
    if first_line.startswith("#!"):
        return first_line[2:].strip()
    return None


def is_binary(script_path: Path) -> bool:
    """Detect binary entrypoints by scanning for null bytes."""
    sample = script_path.read_bytes()[:1024]
    return b"\x00" in sample


def validate_shebang(script_path: Path, expected_python: Path) -> None:
    """Ensure entrypoint uses the current venv interpreter."""
    shebang = read_shebang(script_path)
    if shebang is None:
        if is_binary(script_path):
            return
        message = f"Missing shebang in {script_path}. Rebuild the venv."
        raise SystemExit(message)

    interpreter = shebang.split()[0]
    if interpreter == "/usr/bin/env":
        return

    interpreter_path = Path(interpreter)
    if not interpreter_path.is_absolute():
        message = f"Unexpected shebang in {script_path}: {shebang}. Rebuild the venv."
        raise SystemExit(message)

    if not interpreter_path.exists():
        message = f"Broken shebang in {script_path}: {interpreter_path} not found. Rebuild the venv."
        raise SystemExit(message)

    if interpreter_path.resolve() != expected_python.resolve():
        message = (
            "Venv entrypoint mismatch detected.\n"
            f"Expected: {expected_python}\n"
            f"Found:    {interpreter_path}\n"
            "Rebuild the venv."
        )
        raise SystemExit(message)


def validate_venv() -> None:
    validate_uv_version()
    venv_path = Path(".venv").resolve()
    if not venv_path.is_dir():
        message = "Missing .venv. Rebuild with: uv sync --group dev"
        raise SystemExit(message)

    python_path = venv_path / "bin" / "python3"
    if not python_path.exists():
        message = f"Missing venv interpreter: {python_path}"
        raise SystemExit(message)

    bin_dir = venv_path / "bin"
    for tool in REQUIRED_TOOLS:
        tool_path = bin_dir / tool
        if not tool_path.exists():
            message = f"Missing venv tool: {tool_path}. Run: uv sync --group dev"
            raise SystemExit(message)
        validate_shebang(tool_path, python_path)


def main() -> int:
    ensure_project_root()
    validate_venv()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
