# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for pre-commit-hardcoded-values hook.

Issue #6725: Phase 3 of #6715 — locks down current hook behavior with a
runnable test suite so future tightening of allow/deny rules can be done
safely.

Each test creates a tmpdir, initializes a git repo, stages a file with a
known pattern, invokes the hook against the staged context, and asserts
on exit code + output.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK_PATH = (
    Path(__file__).resolve().parent / "pre-commit-hardcoded-values"
)


def _run_hook_with_staged(
    tmp_path: Path, files: dict[str, str]
) -> subprocess.CompletedProcess:
    """
    Stage ``files`` in a fresh git repo at ``tmp_path`` and run the hook.

    files: relative path -> file content
    """
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=tmp_path, check=True
    )
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)

    return subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(
    not HOOK_PATH.exists(), reason="hook script missing at expected path"
)
class TestHardcodedIPDetection:
    """Hook MUST block hardcoded VM IPs in runtime code."""

    def test_blocks_hardcoded_redis_ip(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/worker.py": 'REDIS_HOST = "172.16.168.23"\n'},
        )
        assert result.returncode != 0
        assert "172.16.168.23" in result.stdout

    def test_blocks_hardcoded_backend_ip_in_typescript(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/api.ts": 'export const URL = "172.16.168.20:8001";\n'},
        )
        assert result.returncode != 0

    def test_blocks_hardcoded_ip_in_vue_component(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/Comp.vue": (
                    "<script>\nconst h = '172.16.168.21';\n</script>\n"
                ),
            },
        )
        assert result.returncode != 0


@pytest.mark.skipif(
    not HOOK_PATH.exists(), reason="hook script missing at expected path"
)
class TestAllowlistedContexts:
    """Files in allowlisted paths or using SSOT must NOT be flagged."""

    def test_allows_ssot_config_file(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "ssot_config.py": (
                    "# This file IS the SSOT — IPs allowed\n"
                    'DEFAULT_REDIS = "172.16.168.23"\n'
                ),
            },
        )
        assert result.returncode == 0, (
            f"hook should allow ssot_config.py:\n{result.stdout}"
        )

    def test_allows_network_constants(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "network_constants.py": (
                    'PRIVATE_PREFIX = "172.16.168."\n'
                ),
            },
        )
        assert result.returncode == 0

    def test_allows_test_files(self, tmp_path: Path) -> None:
        # Test fixtures legitimately use literal IPs to validate behavior
        result = _run_hook_with_staged(
            tmp_path,
            {"test_redis.py": 'EXAMPLE_HOST = "172.16.168.23"\n'},
        )
        assert result.returncode == 0

    def test_allows_underscore_test_suffix(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "module_test.py": 'FIXTURE = "172.16.168.20"\n',
            },
        )
        assert result.returncode == 0

    def test_allows_code_using_ssot_config(self, tmp_path: Path) -> None:
        # Lines that reference config.* / getenv / AUTOBOT_* are skipped
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/db.py": (
                    "import os\n"
                    'host = os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")\n'
                ),
            },
        )
        # NOTE: This test documents the CURRENT behavior of the hook —
        # the line containing `getenv` is skipped wholesale by the regex
        # filter, so the literal fallback string is not flagged. This is
        # exactly the false-negative the AST-aware rewrite (#6725 follow-up)
        # would close. Keeping this assertion green so the eventual rewrite
        # has a clear regression to flip.
        assert result.returncode == 0

    def test_allows_yaml_files(self, tmp_path: Path) -> None:
        # Hook only filters .py/.ts/.vue — YAML/JSON pass through untouched
        result = _run_hook_with_staged(
            tmp_path,
            {"deploy.yaml": 'host: "172.16.168.23"\n'},
        )
        assert result.returncode == 0

    def test_allows_markdown_files(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "README.md": "Backend at 172.16.168.20:8001 (example).\n",
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(
    not HOOK_PATH.exists(), reason="hook script missing at expected path"
)
class TestNonBlockingPatterns:
    """Lines that look like hardcoded IPs but aren't deployment IPs are allowed."""

    def test_allows_rfc1918_192_168_literals(self, tmp_path: Path) -> None:
        # 192.168.x is universal example IP space; tests/SSRF guards use it
        result = _run_hook_with_staged(
            tmp_path,
            {"src/check.py": 'BLOCK = "192.168.1.1"\n'},
        )
        assert result.returncode == 0

    def test_allows_loopback_literal(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path, {"src/local.py": 'HOST = "127.0.0.1"\n'}
        )
        assert result.returncode == 0

    def test_allows_comments(self, tmp_path: Path) -> None:
        # Comments referencing the IP for documentation purposes are skipped
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/doc.py": (
                    "# Production Redis lives at 172.16.168.23\n"
                    "import os\n"
                    'host = os.environ["AUTOBOT_REDIS_HOST"]\n'
                ),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(
    not HOOK_PATH.exists(), reason="hook script missing at expected path"
)
class TestHookExecutability:
    """Sanity: the script is executable and reports its rules on a clean stage."""

    def test_clean_stage_passes(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(tmp_path, {})
        assert result.returncode == 0

    def test_hook_file_is_readable(self) -> None:
        assert HOOK_PATH.is_file(), f"hook missing at {HOOK_PATH}"
        assert os.access(HOOK_PATH, os.R_OK)
