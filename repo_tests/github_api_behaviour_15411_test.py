# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GitHubApi in its own module (#15411): requests, headers, errors and the constructor.

The HTTP layer is faked at `urllib.request.urlopen`, so what is asserted is what would
have gone on the wire.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest
from repo_tests._paths import repo_root

sys.path.insert(0, str(Path(repo_root()) / "pipeline-scripts"))
import github_api as ga  # noqa: E402


class _Response:
    def __init__(self, status: int, body: object, headers: dict | None = None) -> None:
        self.status = status
        # urllib's response carries headers; GitHubApi records them as last_headers (#19548).
        self.headers = headers or {}
        self._raw = json.dumps(body).encode("utf-8") if body is not None else b""

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _fake(monkeypatch: pytest.MonkeyPatch, outcome: object) -> list:
    seen: list = []

    def urlopen(request, timeout):  # noqa: ANN001
        seen.append(SimpleNamespace(request=request, timeout=timeout))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(ga.urllib.request, "urlopen", urlopen)
    return seen


def test_request_sends_auth_headers_body_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _fake(monkeypatch, _Response(200, {"ok": True}))
    api = ga.GitHubApi("tok", "o/r", "https://x.test/", 7)
    assert api.request("POST", "/repos/o/r/x", {"a": 1}) == (200, {"ok": True})
    req = seen[0].request
    assert req.full_url == "https://x.test/repos/o/r/x" and req.get_method() == "POST"
    assert req.data == b'{"a": 1}' and seen[0].timeout == 7
    headers = {k.lower(): v for k, v in req.header_items()}
    assert headers["authorization"] == "Bearer tok"
    assert headers["accept"] == "application/vnd.github+json"
    assert headers["x-github-api-version"] == "2022-11-28"
    assert headers["content-type"] == "application/json"


def test_get_has_no_body_or_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _fake(monkeypatch, _Response(200, None))
    assert ga.GitHubApi("tok", "o/r").request("GET", "rate_limit") == (200, None)
    req = seen[0].request
    assert req.data is None and not req.has_header("Content-type")
    assert req.full_url == "https://api.github.com/rate_limit"


def test_http_error_and_transport_failure_become_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    err = urllib.error.HTTPError("u", 403, "no", {}, io.BytesIO(b"not json"))  # type: ignore[arg-type]
    _fake(monkeypatch, err)
    assert ga.GitHubApi("t", "o/r").request("GET", "/x") == (403, {"message": "not json"})
    _fake(monkeypatch, urllib.error.URLError("dns"))
    status, body = ga.GitHubApi("t", "o/r").request("GET", "/x")
    assert status == ga.NO_RESPONSE_STATUS and "transport failure" in body["message"]


def test_listing_raises_instead_of_returning_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, _Response(200, {"workflow_runs": [{"id": 1}]}))
    assert ga.GitHubApi("t", "o/r").runs_for_sha("a" * 40) == [{"id": 1}]
    err = urllib.error.HTTPError("u", 403, "no", {}, io.BytesIO(b"{}"))  # type: ignore[arg-type]
    _fake(monkeypatch, err)
    with pytest.raises(ga.WatchdogApiError):
        ga.GitHubApi("t", "o/r").runs_for_sha("a" * 40)


def test_a_header_unsafe_token_is_refused_at_construction() -> None:
    with pytest.raises(ga.WatchdogConfigError):
        ga.GitHubApi("bad\ntoken", "o/r")


def test_build_api_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", " tok ")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    api = ga.build_api(9)
    assert (api.token, api.repository, api.api_root, api.timeout) == ("tok", "o/r", ga.DEFAULT_API_ROOT, 9)
    assert ga.build_api().timeout == ga.DEFAULT_REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize(("token", "repo"), [("", "o/r"), ("tok", "nope"), ("tok", "")])
def test_build_api_refuses_missing_configuration(monkeypatch: pytest.MonkeyPatch, token: str, repo: str) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", token)
    monkeypatch.setenv("GITHUB_REPOSITORY", repo)
    with pytest.raises(ga.WatchdogConfigError):
        ga.build_api()


def test_the_old_import_location_is_the_same_object() -> None:
    import ci_dispatch_watchdog as wd

    assert wd.GitHubApi is ga.GitHubApi and wd.WatchdogApiError is ga.WatchdogApiError


# ---- rate-limit backoff (#19522) ------------------------------------------------------------


def _limited(status: int, headers: dict, message: str = "") -> urllib.error.HTTPError:
    body = json.dumps({"message": message}).encode("utf-8")
    return urllib.error.HTTPError("u", status, "limited", headers, io.BytesIO(body))  # type: ignore[arg-type]


def _sequence(monkeypatch: pytest.MonkeyPatch, outcomes: list) -> list:
    """urlopen answers ``outcomes`` in order; sleeps are recorded, never taken."""
    slept: list = []

    def urlopen(request, timeout):  # noqa: ANN001
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(ga.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(ga.GitHubApi, "sleep", staticmethod(slept.append))
    return slept


@pytest.mark.parametrize(
    ("status", "headers", "message", "wait"),
    [
        (429, {"Retry-After": "7"}, "", 7.0),
        (403, {"Retry-After": "3"}, "", 3.0),
        (403, {}, "You have exceeded a secondary rate limit", ga.SECONDARY_LIMIT_WAIT_SECONDS),
        (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1030"}, "API rate limit exceeded", 30.0),
        (429, {}, "", ga.SECONDARY_LIMIT_WAIT_SECONDS),
    ],
)
def test_a_rate_limited_answer_waits_what_github_asks(status, headers, message, wait) -> None:
    assert ga.rate_limit_wait(status, {"message": message}, headers, 1000.0) == wait


@pytest.mark.parametrize(("status", "message"), [(403, "Resource not accessible by integration"), (404, ""), (200, "")])
def test_a_permission_or_other_answer_is_not_retried(status, message) -> None:
    assert ga.rate_limit_wait(status, {"message": message}, {}, 1000.0) is None


def test_request_retries_after_retry_after_then_returns_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    slept = _sequence(monkeypatch, [_limited(429, {"Retry-After": "5"}), _Response(200, {"ok": 1})])
    assert ga.GitHubApi("t", "o/r").request("GET", "/x") == (200, {"ok": 1})
    assert slept == [5.0]


def test_request_gives_up_after_the_retry_budget_and_caps_each_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [
        _limited(403, {"Retry-After": "9999"}, "secondary rate limit") for _ in range(ga.RATE_LIMIT_RETRIES + 1)
    ]
    slept = _sequence(monkeypatch, outcomes)
    status, _ = ga.GitHubApi("t", "o/r").request("GET", "/x")
    assert status == 403 and slept == [ga.RATE_LIMIT_MAX_WAIT_SECONDS] * ga.RATE_LIMIT_RETRIES
