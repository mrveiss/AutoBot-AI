#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A live self-check after an install or update: does each basic function work? (#19740, #20447)

Install and update report success on presence: services up, a model name listed. Each probe here
exercises a function for real and fails naming the probe, what it expected and what came back. A run
that examined nothing is a failure (#15826). Standard library only, so it runs before any venv is sound.

Environment:
    SELF_CHECK_BASE_URL     where the backend answers, the way a browser reaches it
    SELF_CHECK_USERNAME     the dedicated self-check account
    SELF_CHECK_PASSWORD     its password; never printed or written to the report
    SELF_CHECK_COMMIT       the commit under test, for the report
    SELF_CHECK_REPORT       where the JSON report goes
    SELF_CHECK_MODEL_CLI, SELF_CHECK_EMBEDDING_MODEL, SELF_CHECK_COMPLETION_MODELS (newline-separated),
    SELF_CHECK_KIND_SCRIPT  the model kinds probe: the one check_model_kinds.sh, and what to give it
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404  # runs the one model kind script, with a fixed argv
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

CHAT_PROMPT = "Reply with one short sentence."
EMBEDDING_PROBE = "embedding_model"
REQUEST_TIMEOUT_S = 180
EMBEDDING_WAIT_S = 120
EMBEDDING_POLL_S = 5
FAILING_KINDS = ("WRONG-KIND", "MISSING-EMBEDDING", "SHOW-FAILED", "UNKNOWN", "UNREACHABLE")


class ProbeFailed(Exception):
    """A probe's expected result did not come back."""

    def __init__(self, expected: str, got: str) -> None:
        super().__init__(f"expected {expected}; got {got}")
        self.expected, self.got = expected, got


@dataclass
class Result:
    probe: str
    passed: bool
    expected: str = ""
    got: str = ""


def _request(url: str, payload: Optional[dict] = None, token: str = "") -> Tuple[int, str]:
    """(status, body); a refused connection or a timeout is status 0, never an exception."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)  # nosec B310  # a configured backend URL
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as reply:  # nosec B310
            return reply.status, reply.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def _json(status: int, body: str, what: str) -> dict:
    if status != 200:
        raise ProbeFailed(f"HTTP 200 from {what}", f"HTTP {status}: {body[:300]}")
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise ProbeFailed(f"JSON from {what}", f"{body[:300]}") from exc
    if not isinstance(parsed, dict):
        raise ProbeFailed(f"a JSON object from {what}", body[:300])
    return parsed


def login(base: str, username: str, password: str) -> str:
    """The self-check account's token, through the login a browser uses."""
    if not username or not password:
        raise ProbeFailed("the self-check account's credentials", "none in the environment")
    status, body = _request(f"{base}/api/auth/login", {"username": username, "password": password})
    token = _json(status, body, "login").get("access_token") or json.loads(body).get("token")
    if not token:
        raise ProbeFailed("a token from login", "a reply with none")
    return token


def probe_chat(base: str, token: str, _env: Mapping[str, str]) -> None:
    """The default chat model answers a fixed prompt, through the chat API."""
    status, body = _request(f"{base}/api/chat", {"content": CHAT_PROMPT}, token)
    data = _json(status, body, "chat").get("data") or {}
    if not str(data.get("content", "")).strip():
        raise ProbeFailed("a non-empty answer from chat", body[:300])


def _component(components: List[dict], name: str) -> Optional[dict]:
    return next((c for c in components if c.get("name") == name), None)


def probe_embeddings(base: str, token: str, _env: Mapping[str, str], sleep: Callable[[float], None] = time.sleep) -> None:
    """The backend's own probe has embedded for real; its first result lands in the background."""
    deadline = time.monotonic() + EMBEDDING_WAIT_S
    while True:
        status, body = _request(f"{base}/api/system/health/detailed", None, token)
        component = _component(_json(status, body, "detailed health").get("components") or [], EMBEDDING_PROBE)
        if component is None:
            raise ProbeFailed(f"a {EMBEDDING_PROBE} health component", "none in the reply")
        if component.get("status") != "ok":
            raise ProbeFailed("the embedding model to embed", str(component.get("detail")))
        if (component.get("data") or {}).get("embedding_measured"):
            return
        if time.monotonic() >= deadline:
            raise ProbeFailed("a measured embedding", f"none within {EMBEDDING_WAIT_S}s")
        sleep(EMBEDDING_POLL_S)


def probe_model_kinds(_base: str, _token: str, env: Mapping[str, str]) -> None:
    """Every role's model has the capability that role needs, by the one kind script (#19736)."""
    script, embedding = env.get("SELF_CHECK_KIND_SCRIPT", ""), env.get("SELF_CHECK_EMBEDDING_MODEL", "")
    completion = env.get("SELF_CHECK_COMPLETION_MODELS", "")
    if not script or not (embedding or completion):
        raise ProbeFailed("a kind script and models to judge", "nothing to examine")
    child_env = {
        **os.environ,
        "MODEL_CLI": env.get("SELF_CHECK_MODEL_CLI", "ollama"),
        "EMBEDDING_MODEL": embedding,
        "COMPLETION_MODELS": completion,
    }
    done = subprocess.run(["sh", script], capture_output=True, text=True, check=False, env=child_env)  # nosec B603 B607
    lines = done.stdout.splitlines()
    bad = [line for line in lines if line.startswith(FAILING_KINDS)]
    if bad or done.returncode != 0:
        raise ProbeFailed("every model able to do its role's job", "; ".join(bad) or f"exit {done.returncode}")
    if not [line for line in lines if line.startswith("OK ")]:
        raise ProbeFailed("at least one model judged OK", "; ".join(lines) or "no verdicts")


PROBES: Dict[str, Callable[[str, str, Mapping[str, str]], None]] = {
    "chat": probe_chat,
    "model kinds": probe_model_kinds,
    "embeddings": probe_embeddings,
}


def run_probes(base: str, token: str, env: Mapping[str, str], probes: Optional[dict] = None) -> List[Result]:
    results = []
    for name, probe in (PROBES if probes is None else probes).items():
        try:
            probe(base, token, env)
            results.append(Result(name, True))
        except ProbeFailed as exc:
            results.append(Result(name, False, exc.expected, exc.got))
    return results


def write_report(path: str, commit: str, results: List[Result]) -> None:
    report = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "commit": commit,
        "passed": bool(results) and all(r.passed for r in results),
        "probes": [asdict(r) for r in results],
    }
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")


def main(env: Mapping[str, str] = os.environ, probes: Optional[dict] = None) -> int:
    base = env.get("SELF_CHECK_BASE_URL", "").rstrip("/")
    try:
        if not base:
            raise ProbeFailed("SELF_CHECK_BASE_URL", "unset")
        token = login(base, env.get("SELF_CHECK_USERNAME", ""), env.get("SELF_CHECK_PASSWORD", ""))
        results = run_probes(base, token, env, probes)
    except ProbeFailed as exc:
        results = [Result("login", False, exc.expected, exc.got)]
    if env.get("SELF_CHECK_REPORT"):
        write_report(env["SELF_CHECK_REPORT"], env.get("SELF_CHECK_COMMIT", ""), results)
    for r in results:
        sys.stdout.write(f"{'PASS' if r.passed else 'FAIL'} {r.probe}" + ("" if r.passed else f": expected {r.expected}; got {r.got}") + "\n")
    if not results:
        sys.stdout.write("FAIL no probe ran, so nothing was examined\n")
    return 0 if results and all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
