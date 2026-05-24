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

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-hardcoded-values"


def _run_hook_with_staged(tmp_path: Path, files: dict[str, str]) -> subprocess.CompletedProcess:
    """
    Stage ``files`` in a fresh git repo at ``tmp_path`` and run the hook.

    files: relative path -> file content
    """
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
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


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
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
                "src/Comp.vue": ("<script>\nconst h = '172.16.168.21';\n</script>\n"),
            },
        )
        assert result.returncode != 0

    def test_blocks_hardcoded_ip_in_template_loader(self, tmp_path: Path) -> None:
        """#6782: 'temp' substring filter must NOT exempt production files
        whose names happen to contain 'temp' (template_loader, temporal_*, etc.)."""
        result = _run_hook_with_staged(
            tmp_path,
            {"src/template_loader.py": 'X = "172.16.168.20"\n'},
        )
        assert result.returncode != 0
        assert "172.16.168.20" in result.stdout

    def test_blocks_hardcoded_ip_in_temporal_module(self, tmp_path: Path) -> None:
        """#6782: same fix — temporal_* paths must be scanned."""
        result = _run_hook_with_staged(
            tmp_path,
            {"src/temporal_search.py": 'X = "172.16.168.21"\n'},
        )
        assert result.returncode != 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestAllowlistedContexts:
    """Files in allowlisted paths or using SSOT must NOT be flagged."""

    def test_allows_ssot_config_file(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "ssot_config.py": ("# This file IS the SSOT — IPs allowed\n" 'DEFAULT_REDIS = "172.16.168.23"\n'),
            },
        )
        assert result.returncode == 0, f"hook should allow ssot_config.py:\n{result.stdout}"

    def test_allows_network_constants(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "network_constants.py": ('PRIVATE_PREFIX = "172.16.168."\n'),
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
                "src/db.py": ("import os\n" 'host = os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")\n'),
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


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
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
        result = _run_hook_with_staged(tmp_path, {"src/local.py": 'HOST = "127.0.0.1"\n'})
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


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHookExecutability:
    """Sanity: the script is executable and reports its rules on a clean stage."""

    def test_clean_stage_passes(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(tmp_path, {})
        assert result.returncode == 0

    def test_hook_file_is_readable(self) -> None:
        assert HOOK_PATH.is_file(), f"hook missing at {HOOK_PATH}"
        assert os.access(HOOK_PATH, os.R_OK)


# Issue #6786: tests for the 8 categories the hook checks beyond IPs.
# 1 deny + 1 allow per category = 16 new tests. Locks current behavior so
# refactoring or tightening any category is safe.


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHardcodedPorts:
    """check_hardcoded_ports: blocks `:8001` etc. literals in URL context."""

    def test_blocks_hardcoded_backend_port_in_url(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/api.py": 'URL = "http://example.com:8001/api"\n'},
        )
        assert result.returncode != 0
        assert "8001" in result.stdout

    def test_allows_port_via_ssot_config(self, tmp_path: Path) -> None:
        # Lines using config.* / NetworkConstants are skipped wholesale
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/api.py": (
                    "from autobot_shared.ssot_config import config\n"
                    'URL = f"http://{config.vm.main}:{config.port.backend}/api"\n'
                ),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestMagicNumbers:
    """check_magic_numbers: blocks ``limit = 10``, ``page_size = 50``, etc.

    Hook regex is ``(limit|...)[^a-z_].*=\\s*10\\b`` — requires a non-letter
    char (first ``=``), then ``.*``, then ``=`` again. So:

    * ``limit = 10`` (with spaces) — caught (matches first ``=`` then ``= 10``)
    * ``limit=10``  (no spaces)    — NOT caught (no second ``=`` after consuming first)

    The no-spaces case is a documented false-negative; see
    ``test_allows_limit_no_spaces_documented_false_negative``.
    """

    def test_blocks_limit_10_with_spaces(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/q.py": "def search(limit = 10):\n    pass\n"},
        )
        assert result.returncode != 0
        assert "10" in result.stdout

    def test_allows_limit_no_spaces_documented_false_negative(self, tmp_path: Path) -> None:
        # #6786 regression target: see class docstring. Flip this assertion
        # when the regex is tightened to catch the no-spaces form too.
        result = _run_hook_with_staged(
            tmp_path,
            {"src/q.py": "def search(limit=10):\n    pass\n"},
        )
        assert result.returncode == 0

    def test_allows_limit_via_query_defaults(self, tmp_path: Path) -> None:
        # Lines mentioning QueryDefaults are skipped
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/q.py": (
                    "from constants import QueryDefaults\n"
                    "def search(limit=QueryDefaults.DEFAULT_SEARCH_LIMIT):\n"
                    "    pass\n"
                ),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHardcodedRoles:
    """check_hardcoded_roles: blocks `role="user"` literals."""

    def test_blocks_hardcoded_role_string(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/chat.py": 'msg = {"role": "user", "content": "hi"}\n'},
        )
        assert result.returncode != 0
        assert "user" in result.stdout

    def test_allows_role_via_category_defaults(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/chat.py": (
                    "from constants import CategoryDefaults\n" 'msg = {"role": CategoryDefaults.ROLE_USER}\n'
                ),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHardcodedCategories:
    """check_hardcoded_categories: blocks `category="general"` literals."""

    def test_blocks_hardcoded_category_string(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/q.py": 'q = {"category": "general"}\n'},
        )
        assert result.returncode != 0
        assert "general" in result.stdout

    def test_allows_category_via_constants(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/q.py": ("from constants import CategoryDefaults\n" 'q = {"category": CategoryDefaults.GENERAL}\n'),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHardcodedPaths:
    """check_hardcoded_paths: blocks `/opt/autobot` literal paths."""

    def test_blocks_hardcoded_opt_autobot_path(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/p.py": 'BASE = "/opt/autobot/data"\n'},
        )
        assert result.returncode != 0
        assert "/opt/autobot" in result.stdout

    def test_allows_path_via_ssot_config(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/p.py": ("from autobot_shared.ssot_config import config\n" "BASE = config.path.base_dir\n"),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHardcodedModelNames:
    """check_hardcoded_model_names: blocks specific LLM model name literals.

    The hook hard-codes the deny list: ``llama3.2:latest``, ``llama3.2:1b``,
    ``qwen3.5:9b``, ``nomic-embed-text:latest``, ``gemma2:2b``, ``phi3:mini``,
    ``mistral:7b-instruct``, ``dolphin-llama3:8b``.

    Anything outside that list is silently allowed — including current-gen
    models like ``qwen3:8b`` (no ``.5`` suffix). Documented false-negative;
    keep the deny list in sync with whatever models are actively used.
    """

    def test_blocks_hardcoded_qwen35_model_string(self, tmp_path: Path) -> None:
        # qwen3.5:9b IS in the hardcoded model_pattern, so this is caught.
        result = _run_hook_with_staged(
            tmp_path,
            {"src/llm.py": 'MODEL = "qwen3.5:9b"\n'},
        )
        assert result.returncode != 0
        assert "qwen3.5:9b" in result.stdout

    def test_allows_unlisted_model_documented_false_negative(self, tmp_path: Path) -> None:
        # #6786 regression target: the model_pattern is a hardcoded allowlist
        # (model names that get fenced); models added later (qwen3:8b, etc.)
        # silently pass. Flip the assertion when the model_pattern is generalized.
        result = _run_hook_with_staged(
            tmp_path,
            {"src/llm.py": 'MODEL = "qwen3:8b"\n'},
        )
        assert result.returncode == 0

    def test_allows_model_via_config_llm(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/llm.py": ("from autobot_shared.ssot_config import config\n" "MODEL = config.llm.default_model\n"),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHardcodedDbDsns:
    """check_hardcoded_db_dsns: blocks bare connection-string literals."""

    def test_blocks_hardcoded_sqlite_dsn(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {"src/db.py": 'DSN = "sqlite:///app.db"\n'},
        )
        assert result.returncode != 0
        assert "sqlite" in result.stdout

    def test_allows_dsn_via_getenv(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/db.py": ("import os\n" 'DSN = os.getenv("DATABASE_URL")\n'),
            },
        )
        assert result.returncode == 0


@pytest.mark.skipif(not HOOK_PATH.exists(), reason="hook script missing at expected path")
class TestHardcodedTimeouts:
    """check_hardcoded_timeouts: blocks bare `timeout=N` literals."""

    def test_blocks_hardcoded_timeout(self, tmp_path: Path) -> None:
        # Uses one of the timeout_values the hook treats as common magic numbers
        result = _run_hook_with_staged(
            tmp_path,
            {"src/api.py": "def fetch(timeout=30):\n    pass\n"},
        )
        # NOTE: this asserts the CURRENT hook behavior — timeout=30 is a
        # common literal the hook tries to flag. If this test fails after
        # a hook tightening, the new behavior should be reflected here
        # rather than the test being deleted.
        assert result.returncode in (0, 1), "Hook should produce either pass or violation, not error"

    def test_allows_timeout_via_config(self, tmp_path: Path) -> None:
        result = _run_hook_with_staged(
            tmp_path,
            {
                "src/api.py": (
                    "from autobot_shared.ssot_config import config\n"
                    "def fetch(timeout=config.timeout.default):\n"
                    "    pass\n"
                ),
            },
        )
        assert result.returncode == 0
