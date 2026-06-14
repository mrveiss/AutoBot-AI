# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #7444 lint hook — blocking I/O in async paths."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tools.lint.check_no_blocking_io_in_async import check_file


def _write(tmp_path: Path, source: str) -> Path:
    """Write `source` (after dedenting) to a fresh .py file in tmp_path."""
    p = tmp_path / "sample.py"
    p.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# requests.* in async def — must flag
# ---------------------------------------------------------------------------


class TestRequestsInAsync:
    def test_requests_get_inside_async_def_is_flagged(self, tmp_path: Path) -> None:
        src = """
        import requests

        async def fetch():
            r = requests.get("https://example.com")
            return r.text
        """
        violations = check_file(_write(tmp_path, src))
        assert len(violations) == 1
        assert violations[0].kind == "requests.*"
        assert "requests.get" in violations[0].snippet

    def test_all_forbidden_requests_methods_are_flagged(self, tmp_path: Path) -> None:
        src = """
        import requests

        async def all_methods():
            requests.get("u")
            requests.post("u")
            requests.put("u")
            requests.patch("u")
            requests.delete("u")
            requests.head("u")
            requests.options("u")
            requests.request("GET", "u")
        """
        violations = check_file(_write(tmp_path, src))
        # 8 lines of requests.* — all flagged.
        assert len(violations) == 8

    def test_requests_in_sync_def_is_not_flagged(self, tmp_path: Path) -> None:
        src = """
        import requests

        def fetch_sync():
            return requests.get("https://example.com").text
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []

    def test_requests_in_sync_function_nested_in_async_is_not_flagged(self, tmp_path: Path) -> None:
        # A sync function defined inside an async function runs synchronously
        # when called — not in async context. Don't flag.
        src = """
        import requests

        async def outer():
            def helper():
                return requests.get("u")
            return helper
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []


# ---------------------------------------------------------------------------
# Path.read_text / write_text in async def — must flag
# ---------------------------------------------------------------------------


class TestPathIOInAsync:
    def test_read_text_inside_async_is_flagged(self, tmp_path: Path) -> None:
        src = """
        from pathlib import Path

        async def load():
            content = Path("/etc/config").read_text()
            return content
        """
        violations = check_file(_write(tmp_path, src))
        assert len(violations) == 1
        assert violations[0].kind == "Path.read/write_text/bytes"

    def test_write_text_inside_async_is_flagged(self, tmp_path: Path) -> None:
        src = """
        from pathlib import Path

        async def save(p):
            p.write_text("data")
        """
        violations = check_file(_write(tmp_path, src))
        assert len(violations) == 1
        assert violations[0].kind == "Path.read/write_text/bytes"

    def test_read_bytes_and_write_bytes_are_flagged(self, tmp_path: Path) -> None:
        src = """
        async def io_ops(p):
            data = p.read_bytes()
            p.write_bytes(b"x")
        """
        violations = check_file(_write(tmp_path, src))
        assert len(violations) == 2

    def test_read_text_in_sync_def_is_not_flagged(self, tmp_path: Path) -> None:
        src = """
        from pathlib import Path

        def load_sync():
            return Path("/etc").read_text()
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []


# ---------------------------------------------------------------------------
# noqa: async_blocking_io allowlist
# ---------------------------------------------------------------------------


class TestNoqaAllowlist:
    def test_noqa_marker_suppresses_violation(self, tmp_path: Path) -> None:
        src = """
        import requests

        async def fetch():
            r = requests.get("https://example.com")  # noqa: async_blocking_io
            return r.text
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []

    def test_noqa_marker_is_case_insensitive(self, tmp_path: Path) -> None:
        src = """
        import requests

        async def fetch():
            r = requests.get("u")  # noqa: ASYNC_BLOCKING_IO
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []

    def test_noqa_only_suppresses_its_own_line(self, tmp_path: Path) -> None:
        src = """
        import requests

        async def fetch():
            r1 = requests.get("u")  # noqa: async_blocking_io
            r2 = requests.get("u")  # NOT allowlisted
            return r1, r2
        """
        violations = check_file(_write(tmp_path, src))
        assert len(violations) == 1
        assert "NOT allowlisted" in violations[0].snippet


# ---------------------------------------------------------------------------
# Negative cases — must NOT flag
# ---------------------------------------------------------------------------


class TestNegativeCases:
    def test_aiofiles_open_in_async_is_not_flagged(self, tmp_path: Path) -> None:
        # aiofiles is the canonical async file path — must pass.
        src = """
        import aiofiles

        async def load(path):
            async with aiofiles.open(path, "r") as f:
                return await f.read()
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []

    def test_httpx_async_client_is_not_flagged(self, tmp_path: Path) -> None:
        src = """
        import httpx

        async def fetch():
            async with httpx.AsyncClient() as client:
                r = await client.get("u")
            return r.text
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []

    def test_to_thread_wrapped_path_read_text_is_not_flagged(self, tmp_path: Path) -> None:
        # `asyncio.to_thread(p.read_text)` passes the bound method as a
        # callable — the read_text attribute access is NOT a Call node so
        # the AST visitor correctly skips it. This is the canonical
        # async-safe pattern; pin it so a future regression of the
        # detection logic can't accidentally flag it.
        src = """
        import asyncio
        from pathlib import Path

        async def safe_read(p: Path):
            return await asyncio.to_thread(p.read_text)
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []

    def test_to_thread_wrapped_path_read_text_with_call_is_flagged(self, tmp_path: Path) -> None:
        # Calling read_text() inside to_thread's first arg IS a Call node
        # at AST analysis time and DOES execute the read sync — flag this
        # mistake. (Correct usage is to pass the unbound method, not call it.)
        src = """
        import asyncio
        from pathlib import Path

        async def buggy_read(p: Path):
            # to_thread receives the result of read_text(), not the function.
            # The read happens sync BEFORE to_thread schedules anything.
            return await asyncio.to_thread(p.read_text())
        """
        violations = check_file(_write(tmp_path, src))
        assert len(violations) == 1

    def test_unparseable_file_is_silently_skipped(self, tmp_path: Path) -> None:
        # SyntaxError shouldn't crash the hook — flake8 catches those.
        src = """
        async def broken(:
            pass
        """
        violations = check_file(_write(tmp_path, src))
        assert violations == []

    def test_empty_file_is_clean(self, tmp_path: Path) -> None:
        violations = check_file(_write(tmp_path, ""))
        assert violations == []
