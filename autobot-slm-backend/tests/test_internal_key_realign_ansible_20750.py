# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20750: the updater proposes, claims, applies and verifies re-aligning the backend's internal key.

Real ansible-playbook runs of the shared task files against a fake backend that answers the
credential-action routes, accepts only the keys a case allows, and records every call.
"""

import json
import shutil
import subprocess  # nosec B404 -- runs ansible-playbook on a generated local playbook
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_TASKS = Path(__file__).resolve().parents[1] / "ansible" / "_shared" / "tasks"
_SLM, _BACKEND = "slm-sample", "backend-sample"  # pragma: allowlist secret
_ID = "00000000-0000-0000-0000-000000000001"

pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible not installed")


class _Backend:
    """A fake backend: `status` is the proposal's state, `accepts` the keys it authenticates."""

    def __init__(self, status: str, accepts: set) -> None:
        self.status, self.accepts, self.calls = status, accepts, []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 -- http.server's name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                key = self.headers.get("X-Internal-API-Key")
                backend.calls.append((self.path.rsplit("/", 1)[-1], key, body))
                if key not in backend.accepts:
                    return self._answer(401, {"detail": "unauthorized"})
                if self.path.endswith("/credential-proposals"):
                    return self._answer(201, {"approval_id": _ID, "status": backend.status, "created": False})
                if self.path.endswith("/claim"):
                    return self._answer(200, {"approval_id": _ID, "node_id": body["node_id"]})
                return self._answer(204, None)

            def _answer(self, code, payload):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if payload is not None:
                    self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *_args):
                return None

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def steps(self) -> list:
        return [(step, key) for step, key, _body in self.calls]


def _run(tmp_path: Path, backend: _Backend, canonical: str = _SLM, restart: bool = True, verify: bool = True, flags=()):
    """Resolve, then claim; then verify if a realign is being applied. Returns (renders, ok, output)."""
    (tmp_path / "slm-secrets.env").write_text(f"AUTOBOT_INTERNAL_API_KEY={canonical}\n" if canonical else "")
    env_file = tmp_path / "code.env"
    env_file.write_text(f"AUTOBOT_INTERNAL_API_KEY={_BACKEND}\n")
    play = [
        "- hosts: localhost",
        "  gather_facts: false",
        "  tasks:",
        f"    - ansible.builtin.include_tasks: {_TASKS / 'resolve_internal_api_key.yml'}",
        f"    - ansible.builtin.include_tasks: {_TASKS / 'realign_internal_api_key_claim.yml'}",
        "    - ansible.builtin.debug:",
        '        msg: "RENDER {{ internal_api_key_by_file[internal_api_key_loaded_file] }}"',
    ]
    if verify:
        play += [
            f"    - ansible.builtin.include_tasks: {_TASKS / 'realign_internal_api_key_verify.yml'}",
            "      when: internal_api_key_realign_applying | default(false) | bool",
        ]
    (tmp_path / "p.yml").write_text("\n".join(play) + "\n", encoding="utf-8")
    extra = {
        "ansible_become": False,
        "internal_api_key_canonical_file": str(tmp_path / "slm-secrets.env"),
        "internal_api_key_current_env_files": [str(env_file)],
        "internal_api_key_loaded_file": str(env_file),
        "internal_api_key_backend_url": backend.url,
        "slm_node_id": "node-b",
        "autobot_restart_services": restart,
    }
    cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local", str(tmp_path / "p.yml"), "-e", json.dumps(extra)]
    cmd += list(flags)
    env = {"ANSIBLE_LOG_PATH": str(tmp_path / "a.log"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180, check=False)  # nosec B603
    render = next(
        (x.split('"msg": "RENDER ', 1)[1].rstrip('"') for x in proc.stdout.splitlines() if "RENDER " in x), ""
    )
    backend.server.shutdown()
    return render, proc.returncode == 0, proc.stdout


def test_a_pending_realign_is_proposed_with_the_backends_key_and_nothing_changes(tmp_path: Path) -> None:
    backend = _Backend("pending", accepts={_BACKEND})
    render, ok, out = _run(tmp_path, backend)
    assert ok and render == _BACKEND
    assert backend.steps() == [("credential-proposals", _BACKEND)], "only a proposal, sent with the CURRENT key"
    assert backend.calls[0][2] == {"action": "slm_backend_internal_key_realign", "node_id": "node-b"}
    assert "awaiting a decision" in out


def test_an_approved_realign_is_claimed_applied_and_reported_with_the_new_key(tmp_path: Path) -> None:
    backend = _Backend("approved", accepts={_BACKEND, _SLM})
    render, ok, _out = _run(tmp_path, backend)
    assert ok and render == _SLM
    assert backend.steps() == [("credential-proposals", _BACKEND), ("claim", _BACKEND), ("outcome", _SLM)]
    assert backend.calls[-1][2]["result"] == "applied"


def test_a_realign_the_backend_does_not_take_is_reported_failed_and_stops_loudly(tmp_path: Path) -> None:
    """The restarted backend still runs the old key: report it with that key, fail the run, roll nothing back."""
    backend = _Backend("approved", accepts={_BACKEND})
    _render, ok, out = _run(tmp_path, backend)
    assert not ok
    assert backend.steps()[-2:] == [("outcome", _SLM), ("outcome", _BACKEND)]
    assert backend.calls[-1][2]["result"] == "apply_failed"
    assert "still accepts the OLD key" in out and "Nothing was rolled back" in out


@pytest.mark.parametrize("canonical, restart", [("", True), (_SLM, False)], ids=["no-slm-key", "no-restart-sync"])
def test_an_approval_is_not_spent_when_this_run_cannot_apply_it(tmp_path: Path, canonical: str, restart: bool) -> None:
    """Never an empty credential, and a no-restart sync leaves the approval for the next full update."""
    backend = _Backend("approved", accepts={_BACKEND, _SLM})
    render, ok, _out = _run(tmp_path, backend, canonical=canonical, restart=restart, verify=False)
    assert ok and render == _BACKEND
    assert "claim" not in [step for step, _key in backend.steps()]


def test_no_key_reaches_the_output(tmp_path: Path) -> None:
    backend = _Backend("approved", accepts={_BACKEND, _SLM})
    _render, _ok, out = _run(tmp_path, backend)
    assert not [line for line in out.splitlines() if (_SLM in line or _BACKEND in line) and "RENDER" not in line]


def test_the_updater_claims_before_it_renders_and_verifies_after_the_backend_is_up() -> None:
    import yaml

    playbook = yaml.safe_load((_TASKS.parents[1] / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8"))
    names = [t.get("name", "") for play in playbook for t in play.get("tasks", []) if isinstance(t, dict)]

    def at(fragment: str) -> int:
        return next(i for i, name in enumerate(names) if fragment in name)

    resolve, claim = at("Resolve AUTOBOT_INTERNAL_API_KEY"), at("Propose or claim re-aligning")
    render, ready = at("Regenerate .env"), at("Backend | Wait for API to be ready")
    verify = at("Check the re-aligned internal key works")
    assert resolve < claim < render < ready < verify


@pytest.mark.parametrize(
    "flags", [("--skip-tags", "restart"), ("--skip-tags", "celery")], ids=["no-restart", "no-celery"]
)
def test_a_run_that_wont_restart_or_verify_does_not_spend_the_approval(tmp_path: Path, flags) -> None:
    """Claim -> render -> restart -> verify -> outcome is one unit: no claim when the run skips part of it."""
    backend = _Backend("approved", accepts={_BACKEND, _SLM})
    render, ok, _out = _run(tmp_path, backend, verify=False, flags=flags)
    assert ok and render == _BACKEND
    assert "claim" not in [step for step, _key in backend.steps()]
