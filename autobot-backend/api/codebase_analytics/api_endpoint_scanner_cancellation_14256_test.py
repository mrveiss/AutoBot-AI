# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cooperative cancellation for API-endpoint scanning (#14256, #14244).

``APIEndpointChecker.run_full_analysis()`` was one synchronous call submitted
to the analytics executor (``report.py``) or the default executor
(``api_endpoints.py``) that walked the ENTIRE backend and frontend tree with
nothing checking whether the caller was still waiting -- the same shape
#12779 found and fixed for duplicate detection, just for endpoint scanning:
`asyncio.wait_for` cancels the AWAIT, not the thread already walking the
tree.

These tests assert the scan loops actually stop, not merely that a check was
added somewhere.
"""

from __future__ import annotations

import threading

from api.codebase_analytics import api_endpoint_scanner as scanner_mod


def _make_backend_files(tmp_path, count: int) -> None:
    api_dir = tmp_path / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (api_dir / f"m{i}.py").write_text(
            f'@router.get("/x{i}")\nasync def h{i}():\n    return {{}}\n',
            encoding="utf-8",
        )


def _make_frontend_files(tmp_path, count: int) -> None:
    src_dir = tmp_path / "autobot-frontend" / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (src_dir / f"c{i}.ts").write_text(f'api.get("/x{i}");\n', encoding="utf-8")


class TestBackendScannerCooperativeCancellation:
    def test_pre_set_token_stops_the_scan_before_any_file(self, tmp_path):
        """A timed-out scan must stop, not run to completion for a discarded
        result -- the #12779 shape, applied here."""
        _make_backend_files(tmp_path, 5)
        token = threading.Event()
        token.set()
        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path, cancel_token=token)

        assert scanner.scan_all_endpoints() == []

    def test_scan_completes_normally_without_a_token(self, tmp_path):
        """Cancellation must be opt-in -- the default path is unchanged."""
        _make_backend_files(tmp_path, 3)
        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path)

        assert scanner._cancel_token is None
        assert scanner._cancelled() is False
        endpoints = scanner.scan_all_endpoints()
        assert len(endpoints) == 3

    def test_the_check_is_periodic_not_only_at_the_top(self, tmp_path, monkeypatch):
        """#14256: 'checked at loop boundaries... not only at the top'.

        With more files than CANCEL_CHECK_INTERVAL, setting the token after a
        few files must stop the scan well before the last file -- proving the
        loop re-checks periodically, not once at entry.
        """
        total = scanner_mod.CANCEL_CHECK_INTERVAL * 3
        _make_backend_files(tmp_path, total)
        token = threading.Event()
        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path, cancel_token=token)

        call_count = {"n": 0}
        real_scan_file = scanner._scan_file

        def _counting_scan_file(py_file):
            call_count["n"] += 1
            if call_count["n"] == 5:
                token.set()
            return real_scan_file(py_file)

        monkeypatch.setattr(scanner, "_scan_file", _counting_scan_file)
        scanner.scan_all_endpoints()

        assert 5 <= call_count["n"] < total, (
            f"expected the scan to stop well short of all {total} files after being "
            f"cancelled at file 5, but it processed {call_count['n']}"
        )

    def test_unset_token_does_not_cancel(self, tmp_path):
        _make_backend_files(tmp_path, 2)
        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path, cancel_token=threading.Event())

        assert scanner._cancelled() is False
        assert len(scanner.scan_all_endpoints()) == 2


class TestFrontendScannerCooperativeCancellation:
    def test_pre_set_token_stops_the_scan_before_any_file(self, tmp_path):
        _make_frontend_files(tmp_path, 5)
        token = threading.Event()
        token.set()
        scanner = scanner_mod.FrontendAPICallScanner(project_root=tmp_path, cancel_token=token)

        assert scanner.scan_all_calls() == []

    def test_scan_completes_normally_without_a_token(self, tmp_path):
        _make_frontend_files(tmp_path, 3)
        scanner = scanner_mod.FrontendAPICallScanner(project_root=tmp_path)

        assert scanner._cancelled() is False
        assert len(scanner.scan_all_calls()) == 3

    def test_the_check_is_periodic_not_only_at_the_top(self, tmp_path, monkeypatch):
        total = scanner_mod.CANCEL_CHECK_INTERVAL * 3
        _make_frontend_files(tmp_path, total)
        token = threading.Event()
        scanner = scanner_mod.FrontendAPICallScanner(project_root=tmp_path, cancel_token=token)

        call_count = {"n": 0}
        real_scan_file = scanner._scan_file

        def _counting_scan_file(file_path):
            call_count["n"] += 1
            if call_count["n"] == 5:
                token.set()
            return real_scan_file(file_path)

        monkeypatch.setattr(scanner, "_scan_file", _counting_scan_file)
        scanner.scan_all_calls()

        assert 5 <= call_count["n"] < total, (
            f"expected the scan to stop well short of all {total} files after being "
            f"cancelled at file 5, but it processed {call_count['n']}"
        )


class TestAPIEndpointCheckerThreadsTheTokenThrough:
    """run_full_analysis() dispatches both scanners as ONE call submitted to
    a pool (report.py/api_endpoints.py) -- the token has to reach whichever
    of the two scanners is running when the deadline fires."""

    def test_the_same_token_reaches_both_scanners(self, tmp_path):
        _make_backend_files(tmp_path, 1)
        _make_frontend_files(tmp_path, 1)
        token = threading.Event()

        checker = scanner_mod.APIEndpointChecker(project_root=tmp_path, cancel_token=token)

        assert checker.backend_scanner._cancel_token is token
        assert checker.frontend_scanner._cancel_token is token

    def test_a_pre_set_token_makes_run_full_analysis_return_an_empty_analysis(self, tmp_path):
        """Abandoned before it starts: an honest, immediate result rather than
        the full backend+frontend walk running anyway."""
        _make_backend_files(tmp_path, 5)
        _make_frontend_files(tmp_path, 5)
        token = threading.Event()
        token.set()

        checker = scanner_mod.APIEndpointChecker(project_root=tmp_path, cancel_token=token)
        analysis = checker.run_full_analysis()

        assert analysis.backend_endpoints == 0
        assert analysis.frontend_calls == 0
