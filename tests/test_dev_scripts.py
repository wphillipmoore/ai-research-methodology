"""Regression tests for ``scripts/dev/*.sh`` host-mode validation.

These tests exist to prevent the "silent local validation" regression
described in issue #160: the previous ``lint.sh`` / ``typecheck.sh`` /
``test.sh`` required Docker + ``st-docker-test`` on PATH, and their
output was invisible. A ruff-rejectable file could land and the local
validator would report success. This suite asserts the opposite: when a
known-bad file appears in the project, the relevant script must exit
non-zero.

The tests build an isolated tmp project that imports the real scripts,
so they do not mutate the repo under test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DEV = REPO_ROOT / "scripts" / "dev"


def _uv_available() -> bool:
    """Return True if uv is installed (the scripts shell out to it)."""
    return shutil.which("uv") is not None


pytestmark = pytest.mark.skipif(
    not _uv_available(),
    reason="scripts/dev/*.sh require `uv` on PATH",
)


def _write_minimal_project(root: Path, *, bad_source: str | None = None) -> None:
    """Scaffold a tiny project that `uv run ruff/mypy/pytest` can operate on.

    Writes a pyproject.toml mirroring the real repo's ruff/mypy config, a
    ``src/toyproj/__init__.py`` (clean by default), and a ``tests/test_x.py``
    placeholder. When ``bad_source`` is set, it is written to a module
    the corresponding script will scan.
    """
    (root / "src" / "toyproj").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "toyproj" / "__init__.py").write_text('"""toyproj package."""\n')
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_x.py").write_text(
        textwrap.dedent(
            """\
            def test_smoke() -> None:
                assert 1 + 1 == 2
            """
        )
    )
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["setuptools>=68", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "toyproj"
            version = "0.0.1"
            requires-python = ">=3.14,<4.0"

            [tool.setuptools]
            package-dir = {"" = "src"}

            [tool.setuptools.packages.find]
            where = ["src"]

            [dependency-groups]
            dev = ["ruff", "mypy", "pytest", "pytest-cov"]

            [tool.ruff]
            line-length = 120
            target-version = "py314"
            src = ["src", "tests"]

            [tool.ruff.lint]
            select = ["E", "F", "PT"]

            [tool.mypy]
            python_version = "3.14"
            strict = true

            [tool.pytest.ini_options]
            testpaths = ["tests"]
            """
        )
    )
    if bad_source is not None:
        (root / "src" / "toyproj" / "bad.py").write_text(bad_source)


def _copy_script(script_name: str, dest: Path) -> Path:
    """Copy a repo dev script into ``dest/scripts/dev/`` preserving mode."""
    target_dir = dest / "scripts" / "dev"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / script_name
    shutil.copy(SCRIPTS_DEV / script_name, target)
    target.chmod(0o755)
    return target


def _run_script(script: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a dev script and capture its output."""
    env = os.environ.copy()
    env.pop("USE_DOCKER", None)
    return subprocess.run(  # noqa: S603  # trusted: script path is from this repo
        [str(script)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class TestLintScriptRegressionGuard:
    """Contract: scripts/dev/lint.sh must fail on ruff-rejectable code."""

    def test_clean_project_exits_zero(self, tmp_path: Path) -> None:
        _write_minimal_project(tmp_path)
        script = _copy_script("lint.sh", tmp_path)
        result = _run_script(script, tmp_path)
        assert result.returncode == 0, f"clean project should pass lint; stderr={result.stderr!r}"
        assert "ruff check" in result.stdout

    def test_unused_import_fails(self, tmp_path: Path) -> None:
        # F401: unused import — classic ruff rejection.
        _write_minimal_project(
            tmp_path,
            bad_source='"""Bad module."""\nimport os  # F401 unused\n',
        )
        script = _copy_script("lint.sh", tmp_path)
        result = _run_script(script, tmp_path)
        assert result.returncode != 0, (
            f"ruff-rejectable file must fail lint.sh; stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_bad_format_fails(self, tmp_path: Path) -> None:
        # Unformatted source — ruff format --check must reject.
        _write_minimal_project(
            tmp_path,
            bad_source='"""Bad module."""\nx=1+2\n',
        )
        script = _copy_script("lint.sh", tmp_path)
        result = _run_script(script, tmp_path)
        assert result.returncode != 0, (
            f"badly-formatted file must fail lint.sh; stdout={result.stdout!r} stderr={result.stderr!r}"
        )


class TestTypecheckScriptRegressionGuard:
    """Contract: scripts/dev/typecheck.sh must fail on mypy errors.

    Critically, it must catch errors in ``tests/`` as well as ``src/``
    — this was gap #4 in issue #160 (CI ran ``mypy src tests``; local
    ran ``mypy src/``, missing test-only annotation errors).
    """

    def test_tests_type_error_fails(self, tmp_path: Path) -> None:
        _write_minimal_project(tmp_path)
        # Plant a mypy-rejectable return-type mismatch IN tests/ to prove
        # the expanded scope (src tests) vs. the old (src/) is working.
        (tmp_path / "tests" / "test_bad.py").write_text(
            textwrap.dedent(
                """\
                def returns_int() -> int:
                    return "not an int"  # type: str -> int mismatch
                """
            )
        )
        script = _copy_script("typecheck.sh", tmp_path)
        result = _run_script(script, tmp_path)
        assert result.returncode != 0, (
            f"mypy error in tests/ must fail typecheck.sh (gap #4); stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "tests" in (result.stdout + result.stderr)


class TestTestScriptRegressionGuard:
    """Contract: scripts/dev/test.sh must enforce 100% coverage."""

    def test_missing_coverage_fails(self, tmp_path: Path) -> None:
        _write_minimal_project(tmp_path)
        # Add an untested branch to force <100% coverage.
        (tmp_path / "src" / "toyproj" / "uncovered.py").write_text(
            textwrap.dedent(
                """\
                def never_called() -> int:
                    return 42
                """
            )
        )
        # Rewrite test.sh invocation to target toyproj (repo default targets
        # diogenes). Easiest: replace the cov package name in a copy.
        target_dir = tmp_path / "scripts" / "dev"
        target_dir.mkdir(parents=True, exist_ok=True)
        src = (SCRIPTS_DEV / "test.sh").read_text()
        patched = src.replace("--cov=diogenes", "--cov=toyproj")
        script = target_dir / "test.sh"
        script.write_text(patched)
        script.chmod(0o755)
        result = _run_script(script, tmp_path)
        assert result.returncode != 0, (
            "uncovered code must fail test.sh's --cov-fail-under=100; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
