# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #7444 lint hook — blocking I/O in async paths."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tools.lint.check_no_blocking_io_in_async import (
    _Violation,
    check_file,
    imported_callables,
    imported_modules,
    in_scope,
)


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


# ---------------------------------------------------------------------------
# stdlib blocking calls in async def — the #7444 widening
# ---------------------------------------------------------------------------


class TestStdlibBlockingCalls:
    """Each of these was invisible to the guard until the (module, attr) table.

    The codebase-analytics index reported them as high-severity
    `performance_blocking_io_in_async`; this guard passed clean over all of
    them because it knew `requests.*` and `Path.*` and nothing else.
    """

    @pytest.mark.parametrize(
        ("call", "kind"),
        [
            ("subprocess.run(['ls'], timeout=5)", "subprocess.*"),
            ("subprocess.call(['ls'])", "subprocess.*"),
            ("subprocess.check_call(['ls'])", "subprocess.*"),
            ("subprocess.check_output(['ls'])", "subprocess.*"),
            ("subprocess.Popen(['ls'])", "subprocess.*"),
            ("sqlite3.connect('db.sqlite')", "sqlite3.connect"),
            ("time.sleep(1)", "time.sleep"),
            ("os.system('ls')", "os.system"),
        ],
    )
    def test_each_stdlib_blocking_call_is_flagged_in_async(self, tmp_path: Path, call: str, kind: str) -> None:
        src = f"""
        import os
        import sqlite3
        import subprocess
        import time

        async def handler():
            return {call}
        """
        violations = check_file(_write(tmp_path, src))
        assert [v.kind for v in violations] == [kind]

    def test_the_same_calls_in_a_sync_def_are_not_flagged(self, tmp_path: Path) -> None:
        # Sync functions run synchronously by design — nothing to starve.
        src = """
        import subprocess
        import time

        def handler():
            subprocess.run(["ls"], timeout=5)
            time.sleep(1)
        """
        assert check_file(_write(tmp_path, src)) == []

    def test_a_sync_helper_nested_in_async_is_not_flagged(self, tmp_path: Path) -> None:
        # This is the canonical fix shape — the blocking body moves into a sync
        # helper handed to to_thread. It must pass, or the fix can't be written.
        src = """
        import asyncio
        import subprocess

        async def handler():
            def probe():
                return subprocess.run(["ls"], timeout=5)

            return await asyncio.to_thread(probe)
        """
        assert check_file(_write(tmp_path, src)) == []

    def test_a_bare_method_named_run_or_connect_is_not_flagged(self, tmp_path: Path) -> None:
        # The module qualifier is what keeps this a gate rather than a nuisance:
        # `run` and `connect` are any object's methods.
        src = """
        async def handler(engine, task):
            engine.connect()
            task.run()
            return engine.sleep(1)
        """
        assert check_file(_write(tmp_path, src)) == []

    def test_noqa_exempts_a_stdlib_call(self, tmp_path: Path) -> None:
        src = """
        import subprocess

        async def handler():
            return subprocess.run(["ls"])  # noqa: ASYNC_BLOCKING_IO -- runs in a thread
        """
        assert check_file(_write(tmp_path, src)) == []


# ---------------------------------------------------------------------------
# Where the stdlib group is enforced (in_scope)
# ---------------------------------------------------------------------------


def _v(kind: str) -> _Violation:
    return _Violation(path=Path("x.py"), line=1, col=0, kind=kind, snippet="")


class TestInScope:
    @pytest.mark.parametrize(
        "rel",
        [
            "autobot-backend/memory/general_storage_tenancy_test.py",
            "autobot-backend/tests/migrations/test_sqlite_secrets_importer.py",
            "autobot-backend/llc/tests/scheduler_helpers.py",
        ],
    )
    def test_stdlib_kinds_are_out_of_scope_in_every_test_path_spelling(self, rel: str) -> None:
        # All three spellings, because a predicate matching only `*_test.py`
        # would enforce in `tests/test_x.py` and not in `x_test.py` — the same
        # class of half-covering detector this widening exists to close.
        kept, skipped = in_scope([_v("sqlite3.connect")], rel)
        assert (kept, skipped) == ([], 1)

    def test_stdlib_kinds_are_enforced_in_a_production_module(self) -> None:
        kept, skipped = in_scope([_v("subprocess.*")], "autobot-backend/api/vnc_manager.py")
        assert ([v.kind for v in kept], skipped) == (["subprocess.*"], 0)

    @pytest.mark.parametrize("kind", ["requests.*", "Path.read/write_text/bytes"])
    def test_the_pre_existing_kinds_stay_enforced_in_test_files(self, kind: str) -> None:
        # The widening must not quietly relax what already held. A test file
        # doing sync HTTP or sync file I/O in async is still a violation.
        kept, skipped = in_scope([_v(kind)], "autobot-backend/api/some_test.py")
        assert ([v.kind for v in kept], skipped) == ([kind], 0)

    def test_a_mixed_test_file_keeps_the_enforced_kind_and_counts_the_other(self) -> None:
        kept, skipped = in_scope(
            [_v("Path.read/write_text/bytes"), _v("time.sleep")],
            "autobot-backend/api/some_test.py",
        )
        assert ([v.kind for v in kept], skipped) == (["Path.read/write_text/bytes"], 1)


# ---------------------------------------------------------------------------
# Receiver binding: the name is resolved through the file's imports
# ---------------------------------------------------------------------------


class TestReceiverBinding:
    """Matching the *name* `subprocess` is not the same as matching the module.

    Raised on #17647 review: the first cut of the (module, attr) table compared
    `node.func.value.id` to a literal, which let an alias through in the
    false-negative direction and caught a same-named local in the false-positive
    direction. Both directions are pinned here.
    """

    def test_an_aliased_module_is_still_flagged(self, tmp_path: Path) -> None:
        src = """
        import subprocess as sp

        async def handler():
            return sp.run(["ls"], timeout=5)
        """
        assert [v.kind for v in check_file(_write(tmp_path, src))] == ["subprocess.*"]

    @pytest.mark.parametrize(
        ("imp", "call", "kind"),
        [
            ("import sqlite3 as db", "db.connect('x.db')", "sqlite3.connect"),
            ("import time as clock", "clock.sleep(1)", "time.sleep"),
            ("import os as operating_system", "operating_system.system('ls')", "os.system"),
        ],
    )
    def test_every_aliased_kind_is_flagged(self, tmp_path: Path, imp: str, call: str, kind: str) -> None:
        src = f"""
        {imp}

        async def handler():
            return {call}
        """
        assert [v.kind for v in check_file(_write(tmp_path, src))] == [kind]

    def test_a_local_named_like_a_module_is_not_flagged(self, tmp_path: Path) -> None:
        # `time` here is an argument with a `sleep` method, not the stdlib module.
        # Before binding resolution this was reported as `time.sleep`.
        src = """
        async def handler(time, subprocess, sqlite3):
            time.sleep(1)
            subprocess.run(["ls"])
            return sqlite3.connect("x")
        """
        assert check_file(_write(tmp_path, src)) == []

    def test_a_function_local_import_is_resolved(self, tmp_path: Path) -> None:
        # A blocking call is often written right under a local import.
        src = """
        async def handler():
            import subprocess

            return subprocess.run(["ls"])
        """
        assert [v.kind for v in check_file(_write(tmp_path, src))] == ["subprocess.*"]

    def test_a_dotted_import_binds_its_root_package(self, tmp_path: Path) -> None:
        src = """
        import os.path

        async def handler():
            return os.system("ls")
        """
        assert [v.kind for v in check_file(_write(tmp_path, src))] == ["os.system"]

    def test_imported_modules_maps_names_to_modules(self) -> None:
        import ast as _ast

        tree = _ast.parse("import subprocess as sp\nimport os.path\nimport time\n")
        assert imported_modules(tree) == {"sp": "subprocess", "os": "os", "time": "time"}


# ---------------------------------------------------------------------------
# from-import bindings: the half the module-qualified fix did not reach
# ---------------------------------------------------------------------------


class TestFromImportBindings:
    """`from time import sleep` then `sleep(1)` is an `ast.Name` call.

    The module-qualified matcher returns early on any call whose `func` is not an
    `ast.Attribute`, so it could not see these at all -- the alias fix covered
    `import x as y` and left `from x import y`, which is this hook's own subject
    matter one level up: a fix that covers one spelling of the class it names.
    Raised on #17647 review.
    """

    @pytest.mark.parametrize(
        ("src", "kind"),
        [
            ("from time import sleep", "time.sleep"),
            ("from subprocess import run", "subprocess.*"),
            ("from subprocess import Popen", "subprocess.*"),
            ("from sqlite3 import connect", "sqlite3.connect"),
            ("from os import system", "os.system"),
            ("from requests import get", "requests.*"),
        ],
    )
    def test_a_directly_imported_blocking_callable_is_flagged(self, tmp_path: Path, src: str, kind: str) -> None:
        name = src.rsplit(" ", 1)[-1]
        body = f"""
        {src}

        async def handler():
            return {name}(1)
        """
        assert [v.kind for v in check_file(_write(tmp_path, body))] == [kind]

    def test_an_aliased_direct_import_is_flagged(self, tmp_path: Path) -> None:
        src = """
        from subprocess import run as child_run

        async def handler():
            return child_run(["ls"])
        """
        assert [v.kind for v in check_file(_write(tmp_path, src))] == ["subprocess.*"]

    def test_a_bare_name_this_file_never_imported_is_not_flagged(self, tmp_path: Path) -> None:
        # The map is what keeps this narrow: an argument or local named `sleep`
        # is not the stdlib one, and a same-named function from another module is
        # not either.
        src = """
        from mymod import run

        async def handler(sleep):
            sleep(1)
            return run()
        """
        assert check_file(_write(tmp_path, src)) == []

    def test_a_direct_import_called_from_sync_is_not_flagged(self, tmp_path: Path) -> None:
        src = """
        from time import sleep

        def handler():
            sleep(1)
        """
        assert check_file(_write(tmp_path, src)) == []

    def test_imported_callables_maps_names_to_module_attr_pairs(self) -> None:
        import ast as _ast

        tree = _ast.parse("from time import sleep\nfrom subprocess import run as child_run\n")
        assert imported_callables(tree) == {
            "sleep": ("time", "sleep"),
            "child_run": ("subprocess", "run"),
        }
