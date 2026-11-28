# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20447: each self-check probe passes on a working stack and fails, by name, on a planted fault."""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_PATH = "autobot-infrastructure/shared/scripts/post_install_self_check.py"
_KIND_SCRIPT = "autobot-slm-backend/ansible/_shared/files/check_model_kinds.sh"
_SECRET = "s3cret-value"  # pragma: allowlist secret


def _module():
    spec = importlib.util.spec_from_file_location("_self_check_20447", repo_root() / _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass resolves its annotations through here
    spec.loader.exec_module(module)
    return module


check = _module()
_REAL_EGRESS_POLICY = check.assert_egress_policy


@pytest.fixture(autouse=True)
def _loopback_stack_is_allowed(monkeypatch):
    """The fake stack listens on loopback, which the egress policy rightly refuses; the refusal has its own test."""

    async def allow(_url: str) -> None:
        return None

    monkeypatch.setattr(check, "assert_egress_policy", allow)


def test_an_address_the_egress_policy_refuses_is_a_named_failure_not_a_request(monkeypatch) -> None:
    monkeypatch.setattr(check, "assert_egress_policy", _REAL_EGRESS_POLICY)
    sent: list = []
    monkeypatch.setattr(check.requests, "request", lambda *a, **k: sent.append(a))
    status, body = check._request("http://127.0.0.1:1/api/system/health")
    assert (status, sent) == (0, [])
    assert "disallowed address" in body


def _health(probe: dict | None) -> tuple:
    """The real route's shape: ``components`` maps a name to a status string, ``probes`` carries the detail."""
    probes = [probe] if probe else []
    return 200, {"status": "ok", "components": {"backend": "ok", "embedding_model": "ok"}, "probes": probes}


_MEASURED = {
    "name": "embedding_model",
    "status": "ok",
    "data": {"embedding_measured": True, "embedding_measured_age_s": 0},
}


def _healthy() -> dict:
    return {
        "/api/auth/login": (200, {"access_token": "tok"}),
        "/api/chat/sessions": (check.SESSION_CREATED, {"data": {"id": "sess-1"}}),
        "/api/chat/sessions/sess-1": (200, {"data": {"session_id": "sess-1"}}),
        "/api/chat": (200, {"data": {"content": "Hello.", "role": "assistant", "session_id": "sess-1"}}),
        "/api/system/health": _health(_MEASURED),
    }


@pytest.fixture
def stack():
    replies = _healthy()
    seen: list[str] = []
    calls: list[tuple] = []

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            seen.append(self.headers.get("Authorization", ""))
            calls.append((self.command, self.path))
            status, body = replies.get(self.path, (404, {}))
            raw = json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode("utf-8")
            self.send_response(status)
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self._answer()

        do_GET = do_DELETE = _answer

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    replies["calls"] = calls
    yield f"http://127.0.0.1:{server.server_port}", replies, seen
    server.shutdown()


def _cli(tmp_path: Path, body: str) -> str:
    cli = tmp_path / "fake-ollama"
    cli.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    return str(cli)


_EMBEDDER = (
    "[ \"$1\" = list ] && { printf 'NAME ID\\nembedder:latest x\\n'; exit 0; }\n"
    "printf '  Capabilities\\n    embedding\\n\\n'"
)
_CHATTY = "[ \"$1\" = list ] && { printf 'NAME ID\\nembedder:latest x\\n'; exit 0; }\nprintf '  Capabilities\\n    completion\\n\\n'"


def _env(base: str, tmp_path: Path, cli_body: str = _EMBEDDER) -> dict:
    return {
        "SELF_CHECK_BASE_URL": base,
        "SELF_CHECK_USERNAME": "autobot-selfcheck",
        "SELF_CHECK_PASSWORD": _SECRET,
        "SELF_CHECK_COMMIT": "abc123",
        "SELF_CHECK_REPORT": str(tmp_path / "report.json"),
        "SELF_CHECK_KIND_SCRIPT": str(repo_root() / _KIND_SCRIPT),
        "SELF_CHECK_MODEL_CLI": _cli(tmp_path, cli_body),
        "SELF_CHECK_EMBEDDING_MODEL": "embedder",
    }


def _report(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))


def _failed(tmp_path: Path) -> dict:
    return {p["probe"]: p for p in _report(tmp_path)["probes"] if not p["passed"]}


def test_a_working_stack_passes_every_probe_and_reports_them(stack, tmp_path: Path) -> None:
    base, _, seen = stack
    assert check.main(_env(base, tmp_path)) == 0
    report = _report(tmp_path)
    assert report["passed"] is True and report["commit"] == "abc123" and report["timestamp"]
    assert [p["probe"] for p in report["probes"]] == ["chat", "model kinds", "embeddings"]
    assert "Bearer tok" in seen


def test_the_password_reaches_neither_output_nor_report(stack, tmp_path: Path, capsys) -> None:
    base, replies, _ = stack
    replies["/api/chat"] = (500, "boom")
    check.main(_env(base, tmp_path))
    assert _SECRET not in capsys.readouterr().out
    assert _SECRET not in (tmp_path / "report.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("reply", "said"),
    [((500, "boom"), "HTTP 500"), ((200, {"data": {"content": "  "}}), "real answer"), ((200, "not json"), "JSON")],
    ids=["server-error", "empty-answer", "not-json"],
)
def test_a_planted_chat_fault_fails_the_chat_probe(stack, tmp_path: Path, reply, said: str) -> None:
    base, replies, _ = stack
    replies["/api/chat"] = reply
    assert check.main(_env(base, tmp_path)) == 1
    failed = _failed(tmp_path)
    assert list(failed) == ["chat"] and said in failed["chat"]["expected"] + failed["chat"]["got"]


@pytest.mark.parametrize(
    "probe",
    [None, {"name": "embedding_model", "status": "degraded", "detail": "could not embed", "data": {}}],
    ids=["no-probe", "could-not-embed"],
)
def test_a_planted_embedding_fault_fails_the_embeddings_probe(stack, tmp_path: Path, probe) -> None:
    base, replies, _ = stack
    replies["/api/system/health"] = _health(probe)
    assert check.main(_env(base, tmp_path)) == 1
    assert list(_failed(tmp_path)) == ["embeddings"]


def test_an_embedding_never_measured_fails_rather_than_passing_unexamined(stack, tmp_path: Path, monkeypatch) -> None:
    base, replies, _ = stack
    replies["/api/system/health"] = _health(
        {"name": "embedding_model", "status": "ok", "data": {"embedding_measured": False}}
    )
    monkeypatch.setattr(check, "EMBEDDING_WAIT_S", 0)
    assert check.main(_env(base, tmp_path)) == 1
    assert "measured" in _failed(tmp_path)["embeddings"]["expected"]


def test_a_measurement_cached_from_before_this_check_is_not_a_pass(stack, tmp_path: Path, monkeypatch) -> None:
    """The cache can say "ok" for minutes after embedding started failing."""
    base, replies, _ = stack
    replies["/api/system/health"] = _health(
        {
            "name": "embedding_model",
            "status": "ok",
            "data": {"embedding_measured": True, "embedding_measured_age_s": 200},
        }
    )
    monkeypatch.setattr(check, "EMBEDDING_WAIT_S", 0)
    assert check.main(_env(base, tmp_path)) == 1
    assert "during this check" in _failed(tmp_path)["embeddings"]["expected"]


def test_the_wait_follows_the_backends_own_refresh_time(monkeypatch) -> None:
    """A raised cache lifetime must not make the check impossible to pass."""
    clock = {"now": 0.0}
    monkeypatch.setattr(check.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(check, "EMBEDDING_WAIT_S", 10)

    def health(*_args, **_kwargs):
        age = 900 if clock["now"] < 1000 else 0
        probe = {"name": "embedding_model", "status": "ok"}
        probe["data"] = {"embedding_measured_age_s": age, "embedding_refresh_within_s": 2000}
        return 200, json.dumps({"probes": [probe]})

    monkeypatch.setattr(check, "_request", health)
    check.probe_embeddings("http://x", "", {}, sleep=lambda s: clock.update(now=clock["now"] + 500))
    assert clock["now"] == 1000


def test_a_cached_failure_from_before_the_check_is_measured_again(monkeypatch) -> None:
    """The model may have been fixed since; only a failure measured now counts."""
    clock = {"now": 0.0}
    monkeypatch.setattr(check.time, "monotonic", lambda: clock["now"])

    def health(*_args, **_kwargs):
        stale = clock["now"] == 0
        probe = {"name": "embedding_model", "status": "degraded" if stale else "ok", "detail": "old"}
        probe["data"] = {"embedding_measured_age_s": 50 if stale else 1}
        return 200, json.dumps({"probes": [probe]})

    monkeypatch.setattr(check, "_request", health)
    check.probe_embeddings("http://x", "", {}, sleep=lambda s: clock.update(now=clock["now"] + 5))
    assert clock["now"] == 5


def test_a_failure_measured_during_the_check_fails_it(monkeypatch) -> None:
    monkeypatch.setattr(check.time, "monotonic", lambda: 0.0)
    probe = {"name": "embedding_model", "status": "degraded", "detail": "could not embed"}
    probe["data"] = {"embedding_measured_age_s": 0}
    monkeypatch.setattr(check, "_request", lambda *a, **k: (200, json.dumps({"probes": [probe]})))
    with pytest.raises(check.ProbeFailed, match="could not embed"):
        check.probe_embeddings("http://x", "", {}, sleep=lambda s: None)


def test_the_ca_file_comes_from_the_environment_it_was_given(stack, tmp_path: Path, monkeypatch) -> None:
    base, _, _ = stack
    used = []
    real = check._request

    def spy(*args, **kwargs):
        used.append(kwargs.get("cafile"))
        return real(*args, **{**kwargs, "cafile": None})

    monkeypatch.setattr(check, "_request", spy)
    monkeypatch.delenv("SELF_CHECK_CA_FILE", raising=False)
    assert check.main({**_env(base, tmp_path), "SELF_CHECK_CA_FILE": "/given/ca.pem"}) == 0
    assert used and set(used) == {"/given/ca.pem"}


def test_an_unwritable_report_still_prints_the_outcomes_and_fails(stack, tmp_path: Path, capsys) -> None:
    base, _, _ = stack
    env = {**_env(base, tmp_path), "SELF_CHECK_REPORT": str(tmp_path / "missing" / "report.json")}
    assert check.main(env) == 1
    out = capsys.readouterr().out
    assert "PASS chat" in out and "FAIL report" in out


def test_an_unreadable_ca_file_is_a_named_failure_not_a_traceback(stack, tmp_path: Path) -> None:
    base, _, _ = stack
    env = {**_env(base.replace("http:", "https:"), tmp_path), "SELF_CHECK_CA_FILE": str(tmp_path / "missing.pem")}
    assert check.main(env) == 1
    assert _failed(tmp_path)["login"]["got"].startswith("HTTP 0")


def test_a_crash_in_the_chat_step_still_deletes_the_session(stack, tmp_path: Path, monkeypatch) -> None:
    base, replies, _ = stack
    real_json = check._json

    def crash_on_chat(status, body, what, *expected):
        if what == "chat":
            raise KeyError("data")
        return real_json(status, body, what, *expected)

    monkeypatch.setattr(check, "_json", crash_on_chat)
    assert check.main(_env(base, tmp_path)) == 1
    assert ("DELETE", "/api/chat/sessions/sess-1") in replies["calls"]


def test_the_chat_fallback_reply_is_not_an_answer(stack, tmp_path: Path) -> None:
    base, replies, _ = stack
    text = f"{check.CHAT_ERROR_REPLY}. Please try again."
    replies["/api/chat"] = (200, {"data": {"content": text, "role": "assistant", "session_id": "sess-1"}})
    assert check.main(_env(base, tmp_path)) == 1
    assert list(_failed(tmp_path)) == ["chat"]


@pytest.mark.parametrize("chat_ok", [True, False], ids=["after-an-answer", "after-a-failure"])
def test_the_session_is_deleted_either_way(stack, tmp_path: Path, chat_ok: bool) -> None:
    base, replies, _ = stack
    if not chat_ok:
        replies["/api/chat"] = (500, "boom")
    check.main(_env(base, tmp_path))
    assert ("DELETE", "/api/chat/sessions/sess-1") in replies["calls"]


def test_a_session_left_behind_fails_the_probe(stack, tmp_path: Path) -> None:
    base, replies, _ = stack
    replies["/api/chat/sessions/sess-1"] = (500, "boom")
    assert check.main(_env(base, tmp_path)) == 1
    assert "deleted" in _failed(tmp_path)["chat"]["expected"]


def test_a_failed_delete_does_not_hide_the_chat_failure(stack, tmp_path: Path) -> None:
    base, replies, _ = stack
    replies["/api/chat"] = (500, "boom")
    replies["/api/chat/sessions/sess-1"] = (500, "stuck")
    assert check.main(_env(base, tmp_path)) == 1
    failed = _failed(tmp_path)["chat"]
    assert "HTTP 200 from chat" in failed["expected"] and "boom" in failed["got"] and "stuck" in failed["got"]


def test_a_probe_s_own_crash_still_reports(stack, tmp_path: Path) -> None:
    base, _, _ = stack

    def _crash(*_args) -> None:
        raise AttributeError("a defect")

    assert check.main(_env(base, tmp_path), probes={"chat": _crash}) == 1
    assert "AttributeError" in _failed(tmp_path)["chat"]["got"]


def test_the_shapes_this_reads_are_the_backend_s_own() -> None:
    chat = (repo_root() / "autobot-backend/api/chat.py").read_text(encoding="utf-8")
    assert f'"{check.CHAT_ERROR_REPLY}. Please try again."' in chat
    system = (repo_root() / "autobot-backend/api/system.py").read_text(encoding="utf-8")
    assert 'health_status["probes"] = [component.model_dump(' in system
    assert '@router.api_route("/health", methods=["GET"]' in system
    health = (repo_root() / "autobot-backend/api/embedding_model_health.py").read_text(encoding="utf-8")
    assert '"embedding_measured"' in health
    sessions = (repo_root() / "autobot-backend/api/chat_sessions.py").read_text(encoding="utf-8")
    assert '@router.post("/chat/sessions"' in sessions and '@router.delete("/chat/sessions/{session_id}"' in sessions
    create = sessions[sessions.index("async def create_session(") :]
    create = create[: create.index("\n@router.")]
    assert f"status_code={check.SESSION_CREATED}," in create, "the probe expects the status the create route returns"


def test_a_chat_model_in_the_embedding_role_fails_the_kinds_probe(stack, tmp_path: Path) -> None:
    base, _, _ = stack
    assert check.main(_env(base, tmp_path, _CHATTY)) == 1
    assert "WRONG-KIND" in _failed(tmp_path)["model kinds"]["got"]


def test_no_models_to_judge_fails_rather_than_passing_unexamined(stack, tmp_path: Path) -> None:
    base, _, _ = stack
    env = _env(base, tmp_path)
    env["SELF_CHECK_EMBEDDING_MODEL"] = ""
    assert check.main(env) == 1
    assert "nothing to examine" in _failed(tmp_path)["model kinds"]["got"]


@pytest.mark.parametrize(
    "change",
    [{"SELF_CHECK_PASSWORD": ""}, {"SELF_CHECK_BASE_URL": ""}, {"SELF_CHECK_BASE_URL": "http://127.0.0.1:9"}],
    ids=["no-credentials", "no-url", "nothing-listening"],
)
def test_no_login_is_a_named_failure(stack, tmp_path: Path, change: dict) -> None:
    base, _, _ = stack
    assert check.main({**_env(base, tmp_path), **change}) == 1
    assert list(_failed(tmp_path)) == ["login"]


def test_a_run_with_no_probes_is_a_failure(stack, tmp_path: Path) -> None:
    base, _, _ = stack
    assert check.main(_env(base, tmp_path), probes={}) == 1
    assert _report(tmp_path)["passed"] is False


def test_a_session_create_answered_200_is_not_taken_as_created(stack, tmp_path: Path) -> None:
    """Control: the probe checks the create status, so the 201 above is a claim it actually tests."""
    base, replies, _ = stack
    replies["/api/chat/sessions"] = (200, {"data": {"id": "sess-1"}})
    assert check.main(_env(base, tmp_path)) == 1
    assert "HTTP 201 from session create" in _failed(tmp_path)["chat"]["expected"]
