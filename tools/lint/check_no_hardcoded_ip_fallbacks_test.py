# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/check_no_hardcoded_ip_fallbacks.py (#6783)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_no_hardcoded_ip_fallbacks as hook  # noqa: E402


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


class TestDenyCases:
    """Patterns the AST visitor MUST flag."""

    def test_blocks_os_getenv_with_ip_default(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "config.py",
            "import os\nh = os.getenv('AUTOBOT_REDIS_HOST', '172.16.168.23')\n",
        )
        hits = hook._scan(path, tmp_path)
        assert len(hits) == 1
        assert "172.16.168.23" in hits[0][1]

    def test_blocks_os_environ_get_with_ip_default(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "config.py",
            "import os\nh = os.environ.get('AUTOBOT_BACKEND_HOST', '172.16.168.20')\n",
        )
        hits = hook._scan(path, tmp_path)
        assert len(hits) == 1
        assert "172.16.168.20" in hits[0][1]

    def test_blocks_keyword_default(self, tmp_path: Path) -> None:
        # keyword form: os.getenv("X", default="172.16.168.X")
        # Currently NOT supported (kwarg form is rare). Test documents
        # current behavior; if/when added, flip this assertion.
        path = _write(
            tmp_path,
            "config.py",
            "import os\nh = os.getenv('X', default='172.16.168.20')\n",
        )
        hits = hook._scan(path, tmp_path)
        assert hits == []  # documented limitation

    def test_blocks_multiple_distinct_ips_in_one_file(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "multi.py",
            ("import os\n" "r = os.getenv('R', '172.16.168.23')\n" "b = os.getenv('B', '172.16.168.20')\n"),
        )
        hits = hook._scan(path, tmp_path)
        assert len(hits) == 2


class TestAllowCases:
    """Legitimate uses that must NOT trip the visitor."""

    def test_allows_loopback_default(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "ok.py",
            "import os\nh = os.getenv('X', '127.0.0.1')\n",
        )
        assert hook._scan(path, tmp_path) == []

    def test_allows_rfc1918_192_default(self, tmp_path: Path) -> None:
        # 192.168.x.x is example/test space; legitimately used as defaults.
        path = _write(
            tmp_path,
            "ok.py",
            "import os\nh = os.getenv('X', '192.168.1.1')\n",
        )
        assert hook._scan(path, tmp_path) == []

    def test_allows_no_default(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "ok.py",
            "import os\nh = os.getenv('X')\n",
        )
        assert hook._scan(path, tmp_path) == []

    def test_allows_non_string_default(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "ok.py",
            "import os\nh = os.getenv('X', None)\n",
        )
        assert hook._scan(path, tmp_path) == []

    def test_allows_unrelated_get_call(self, tmp_path: Path) -> None:
        # dict.get / redis.get / requests.get etc. must NOT be matched
        path = _write(
            tmp_path,
            "ok.py",
            (
                "d = {}\n"
                "x = d.get('redis_host', '172.16.168.23')\n"
                "import redis\n"
                "y = redis.Redis().get('172.16.168.23')\n"
            ),
        )
        assert hook._scan(path, tmp_path) == []

    def test_allows_ssot_lookup(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "ok.py",
            ("from autobot_shared.ssot_config import config\n" "h = config.vm.redis\n"),
        )
        assert hook._scan(path, tmp_path) == []


class TestAllowlistedFiles:
    """Self-allowlist: hook + test must not trigger when scanned."""

    def test_hook_itself_allowlisted(self, tmp_path: Path) -> None:
        # Simulate a file at the allowlisted path inside tmp_path
        target = tmp_path / "tools" / "lint"
        target.mkdir(parents=True)
        path = target / "check_no_hardcoded_ip_fallbacks.py"
        path.write_text("import os\nh = os.getenv('X', '172.16.168.23')\n", encoding="utf-8")
        assert hook._scan(path, tmp_path) == []


class TestEntryPoint:
    """Smoke test the main() argv harness end-to-end."""

    def test_returns_1_when_violations(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = _write(
            tmp_path,
            "bad.py",
            "import os\nh = os.getenv('X', '172.16.168.23')\n",
        )
        rc = hook.main(["check_no_hardcoded_ip_fallbacks.py", str(path)])
        assert rc == 1
        captured = capsys.readouterr()
        assert "172.16.168.23" in captured.err
        assert "1 hardcoded-IP fallback(s)" in captured.err

    def test_returns_0_on_clean(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = _write(
            tmp_path,
            "clean.py",
            "import os\nh = os.getenv('X', '127.0.0.1')\n",
        )
        rc = hook.main(["check_no_hardcoded_ip_fallbacks.py", str(path)])
        assert rc == 0
