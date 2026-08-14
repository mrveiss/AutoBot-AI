# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A route that exceeds its deadline says so, and every covered route has one (#14015).

#13602: `/api/analytics/codebase/report` held the socket open past 180s and
logged nothing — no exception, no timeout, no trace. Not a slow endpoint; a
handler that never ran, because it queued behind eight busy executor workers on
the one analysis in its fan-out that had no `asyncio.wait_for`.

The defect is the PATTERN. When bounding is opt-in and per-call-site, an
unbounded path is invisible — it looks exactly like every other handler until it
hangs. `report.py` carried three different timeout constants and one analysis
with none, and nothing about the file made that visible.

So there are two halves here and both are load-bearing: a decorator that turns
the hang into a 504 naming the endpoint, and a checker that makes an unbounded
route a declaration rather than a default.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess  # nosec B404  # runs the repo's own checker
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from autobot_shared.error_boundaries import DEFAULT_ROUTE_DEADLINE_SECONDS, bounded

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKER = _REPO_ROOT / "tools" / "lint" / "check_route_deadlines.py"


class TestTheDeadlineFires:
    @pytest.mark.asyncio
    async def test_a_handler_that_never_returns_becomes_a_504(self):
        """The reproduction, not the predicate. #13602's handler never returned
        and the socket stayed open; a test asserting only that the decorator is
        present would pass against a decorator that never fires."""

        @bounded(0.05, operation="never_returns")
        async def handler():
            await asyncio.Event().wait()

        # Outer bound on purpose: without the decorator's wait_for this handler
        # never returns, and a mutation test would hang the suite instead of
        # failing it — which in CI is a cancelled job, not a report.
        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(handler(), timeout=10)

        assert exc.value.status_code == 504
        assert exc.value.detail["error"] == "deadline_exceeded"

    @pytest.mark.asyncio
    async def test_the_error_names_the_endpoint_and_the_limit(self):
        """A hang with no output is indistinguishable from a slow network, a
        stuck proxy or a dead process. The payload has to be actionable."""

        @bounded(0.05, operation="named_thing")
        async def handler():
            await asyncio.sleep(5)

        # Outer bound on purpose: without the decorator's wait_for this handler
        # never returns, and a mutation test would hang the suite instead of
        # failing it — which in CI is a cancelled job, not a report.
        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(handler(), timeout=10)

        assert exc.value.detail["operation"] == "named_thing"
        assert exc.value.detail["timeout_seconds"] == 0.05
        assert "named_thing" in exc.value.detail["message"]

    @pytest.mark.asyncio
    async def test_the_operation_defaults_to_the_handler_name(self):
        """What an operator greps for."""

        @bounded(0.05)
        async def get_codebase_stats():
            await asyncio.sleep(5)

        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(get_codebase_stats(), timeout=10)

        assert exc.value.detail["operation"] == "get_codebase_stats"

    @pytest.mark.asyncio
    async def test_the_timeout_is_logged(self, caplog):
        """Silence was half of #13602 — a bounded-but-silent handler is still
        undiagnosable from the outside, because a 504 tells the caller nothing
        about which of many analyses ran long."""

        @bounded(0.05, operation="logged_thing")
        async def handler():
            await asyncio.sleep(5)

        with caplog.at_level(logging.WARNING):
            with pytest.raises(HTTPException):
                await asyncio.wait_for(handler(), timeout=10)

        assert any(
            "logged_thing" in record.getMessage() and "deadline" in record.getMessage().lower()
            for record in caplog.records
        ), "a deadline that fires must name the handler in the log"

    @pytest.mark.asyncio
    async def test_a_fast_handler_is_untouched(self):
        """The direction that must stay true. A decorator that always fires
        would pass every test above while breaking every endpoint."""

        @bounded(5.0)
        async def handler():
            return {"ok": True}

        assert await handler() == {"ok": True}

    @pytest.mark.asyncio
    async def test_a_handler_raising_its_own_error_is_not_masked(self):
        """The deadline must not convert a real failure into a timeout."""

        @bounded(5.0)
        async def handler():
            raise HTTPException(status_code=400, detail="bad request")

        # Outer bound on purpose: without the decorator's wait_for this handler
        # never returns, and a mutation test would hang the suite instead of
        # failing it — which in CI is a cancelled job, not a report.
        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(handler(), timeout=10)

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_arguments_and_return_value_pass_through(self):
        @bounded(5.0)
        async def handler(a, *, b):
            return a + b

        assert await handler(1, b=2) == 3


class TestAMisconfiguredDeadlineFailsAtImport:
    @pytest.mark.parametrize("bad", [0, -1, -0.5])
    def test_a_non_positive_deadline_is_rejected_at_decoration(self, bad):
        """`wait_for(timeout=0)` expires immediately, so every request 504s —
        an always-on failure reads as a broken endpoint rather than a
        misconfiguration. Better to fail at import than on the first request."""
        with pytest.raises(ValueError):
            bounded(bad)

    def test_the_default_is_a_usable_number(self):
        assert 0 < DEFAULT_ROUTE_DEADLINE_SECONDS <= 300


class TestTheCheckerCoversEveryRoute:
    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(  # nosec B603  # fixed interpreter, repo-local target
            [sys.executable, str(_CHECKER)],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=120,
        )

    def test_the_repo_passes_its_own_checker(self):
        result = self._run()
        assert result.returncode == 0, result.stdout + result.stderr

    def test_the_checker_sees_a_real_number_of_routes(self):
        """Guard the guard: a matcher that matches nothing reports a clean tree.
        An empty result reads as a clean result."""
        result = self._run()
        assert "of 85 routes bounded" in result.stdout or " routes bounded" in result.stdout
        count = int(result.stdout.split(" of ")[1].split(" ")[0])
        assert count >= 50, f"checker found only {count} routes — the matcher is probably broken"


class TestTheCheckerActuallyFires:
    """The checker's whole premise is that an unbounded route becomes a
    declaration rather than a default. Review of #14243 showed nothing proved
    it: mutating `_is_bounded` to `return True` — so it would accept ANY route —
    left the suite green, because every test only asserted the checker is
    currently happy with a repo that happens to be fully bounded.

    Asserting "it passes today" is not asserting "it catches an omission". These
    plant one.
    """

    def _run_against(self, tmp_path, body: str) -> int:
        import importlib.util

        pkg = tmp_path / "endpoints"
        pkg.mkdir()
        (pkg / "routes.py").write_text(body, encoding="utf-8")

        spec = importlib.util.spec_from_file_location("_deadline_checker", _CHECKER)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        checker._REPO_ROOT = tmp_path
        checker.COVERED_PACKAGES = ("endpoints",)
        checker.UNBOUNDED_BY_DESIGN = {}
        return checker.main()

    def test_an_unbounded_route_fails(self, tmp_path):
        code = self._run_against(
            tmp_path,
            '@router.get("/thing")\nasync def get_thing():\n    return {}\n',
        )
        assert code == 1, "an unbounded route was accepted — the checker does not detect the thing it exists for"

    def test_a_bounded_route_passes(self, tmp_path):
        """The direction that must stay true: a checker that always fails is as
        useless as one that never does, and would be deleted within a week."""
        code = self._run_against(
            tmp_path,
            '@router.get("/thing")\n@bounded(60.0)\nasync def get_thing():\n    return {}\n',
        )
        assert code == 0

    def test_a_declared_route_passes_only_with_its_declaration(self, tmp_path):
        import importlib.util

        pkg = tmp_path / "endpoints"
        pkg.mkdir()
        (pkg / "routes.py").write_text(
            '@router.get("/thing")\nasync def get_thing():\n    return {}\n', encoding="utf-8"
        )
        spec = importlib.util.spec_from_file_location("_deadline_checker2", _CHECKER)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        checker._REPO_ROOT = tmp_path
        checker.COVERED_PACKAGES = ("endpoints",)

        checker.UNBOUNDED_BY_DESIGN = {}
        assert checker.main() == 1, "undeclared and unbounded must fail"

        checker.UNBOUNDED_BY_DESIGN = {"get_thing": "streams an unbounded log tail"}
        assert checker.main() == 0, "a declared route with a reason must pass"

    def test_a_non_route_function_is_not_required_to_be_bounded(self, tmp_path):
        """Only routes. A helper without a deadline is not a finding."""
        code = self._run_against(
            tmp_path,
            '@router.get("/thing")\n@bounded(60.0)\nasync def get_thing():\n    return {}\n\n\n'
            "async def _helper():\n    return {}\n",
        )
        assert code == 0
