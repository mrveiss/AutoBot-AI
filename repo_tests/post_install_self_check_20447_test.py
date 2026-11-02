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


def _health(probe: dict | None) -> tuple:
    """The real route's shape: ``components`` maps a name to a status string, ``probes`` carries the detail."""
    probes = [probe] if probe else []
    return 200, {"status": "ok", "components": {"backend": "ok", "embedding_model": "ok"}, "probes": probes}


_MEASURED = {"name": "embedding_model", "status": "ok", "data": {"embedding_measured": True}}


def _healthy() -> dict:
    return {
        "/api/auth/login": (200, {"access_token": "tok"}),
        "/api/chat/sessions": (200, {"data": {"id": "sess-1"}}),
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
