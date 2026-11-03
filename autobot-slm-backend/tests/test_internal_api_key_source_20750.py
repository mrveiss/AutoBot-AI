# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20750: one source for the backend's internal API key, and a mismatch that can't stay silent.

Every SLM call into the backend's System vault answered 401 for a week. Install rendered the
backend's key from the SLM's slm-secrets.env, while every update rendered it back from the
backend's own env file, so once the two differed nothing realigned them and nothing showed it.
"""

import json
import shutil
import subprocess  # nosec B404 -- runs ansible-playbook on a generated local playbook
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE = _ROOT / "ansible"
_SHARED = "resolve_internal_api_key.yml"


def _yaml(rel: str):
    return yaml.safe_load((_ANSIBLE / rel).read_text(encoding="utf-8"))


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


@pytest.mark.parametrize("rel", ["roles/backend/tasks/main.yml", "playbooks/update-all-nodes.yml"])
def test_install_and_update_resolve_the_key_through_the_one_shared_task(rel: str) -> None:
    tasks = list(_walk(_yaml(rel)))
    includes = [t for t in tasks if str(t.get("ansible.builtin.include_tasks", "")).endswith(_SHARED)]
    assert len(includes) == 1, f"{rel} resolves the key once, through {_SHARED}"
    readers = [t for t in tasks if "AUTOBOT_INTERNAL_API_KEY" in str(t.get("ansible.builtin.shell", ""))]
    assert not readers, f"{rel} reads the key itself, a second source: {[t.get('name') for t in readers]}"


def test_the_updater_no_longer_passes_its_own_read_of_the_key() -> None:
    text = (_ANSIBLE / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8")
    assert "existing_internal_api_key" not in text


_PROBE = """
- hosts: localhost
  gather_facts: false
  tasks:
    - ansible.builtin.include_tasks: %s
    - ansible.builtin.debug:
        msg: "RESULT {{ {'same_as_current': autobot_internal_api_key == current_value,
                        'same_as_canonical': autobot_internal_api_key == canonical_value,
                        'mismatch': internal_api_key_mismatch | bool} | to_json }}"
""" % (_ANSIBLE / "_shared" / "tasks" / _SHARED)


def _run(tmp_path: Path, canonical: str, current: str) -> tuple[dict, str]:
    """Resolve with a canonical file and a backend env file holding the given values ('' = absent)."""
    (tmp_path / "slm-secrets.env").write_text(f"AUTOBOT_INTERNAL_API_KEY={canonical}\n" if canonical else "")
    (tmp_path / "backend.env").write_text(f"OTHER=1\nAUTOBOT_INTERNAL_API_KEY={current}\n" if current else "OTHER=1\n")
    (tmp_path / "p.yml").write_text(_PROBE, encoding="utf-8")
    extra = {
        "ansible_become": False,
        "internal_api_key_canonical_file": str(tmp_path / "slm-secrets.env"),
        "internal_api_key_current_env_files": [str(tmp_path / "missing.env"), str(tmp_path / "backend.env")],
        "canonical_value": canonical,
        "current_value": current,
    }
    cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local", str(tmp_path / "p.yml"), "-e", json.dumps(extra)]
    env = {"ANSIBLE_LOG_PATH": str(tmp_path / "a.log"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120, check=False).stdout  # nosec B603
    line = next(x for x in out.splitlines() if "RESULT" in x)
    return json.loads(line.split("RESULT ", 1)[1].rstrip('"').replace('\\"', '"')), out


_needs_ansible = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible not installed")


@_needs_ansible
def test_a_fresh_install_renders_the_canonical_key(tmp_path: Path) -> None:
    result, out = _run(tmp_path, canonical="slm-sample", current="")  # pragma: allowlist secret
    assert result == {"same_as_current": False, "same_as_canonical": True, "mismatch": False}
    assert "FINDING #20750" not in out


@_needs_ansible
def test_matching_keys_render_unchanged(tmp_path: Path) -> None:
    result, out = _run(tmp_path, canonical="same-sample", current="same-sample")  # pragma: allowlist secret
    assert result == {"same_as_current": True, "same_as_canonical": True, "mismatch": False}
    assert "FINDING #20750" not in out


@_needs_ansible
def test_differing_keys_keep_the_backend_value_and_say_so(tmp_path: Path) -> None:
    """Never a silent rewrite of a stored credential (#17038), and never a silent pass either."""
    result, out = _run(tmp_path, canonical="slm-sample", current="backend-sample")  # pragma: allowlist secret
    assert result == {"same_as_current": True, "same_as_canonical": False, "mismatch": True}
    assert "FINDING #20750" in out and "KEPT the backend's key" in out
    assert "slm-sample" not in out and "backend-sample" not in out, "no key value reaches the output"


# --- the SLM side: the refusal becomes an admin-visible finding ---------------------------------


@pytest.fixture
def finding(monkeypatch):
    """The finding writer against a fake session that remembers what it added."""
    from services import backend_key_finding as mod

    added: list = []

    class _Session:
        async def execute(self, _query):
            return MagicMock(scalar=lambda: 1 if added else None)

        def add(self, event):
            added.append(event)

        async def commit(self):
            return None

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "db_service", MagicMock(session=lambda: _Ctx()))
    # The conftest stubs `models` session-wide; the writer's own logic is what is under test here.
    monkeypatch.setattr(mod, "NodeEvent", _RecordedEvent)
    monkeypatch.setattr(mod, "EventSeverity", types.SimpleNamespace(ERROR=types.SimpleNamespace(value="error")))
    monkeypatch.setattr(mod, "select", lambda *_a: MagicMock())
    return mod, added


class _RecordedEvent(types.SimpleNamespace):
    """A NodeEvent stand-in that keeps its constructor arguments; the class attributes feed the query."""

    id = node_id = event_type = resolved = MagicMock()


@pytest.mark.asyncio
async def test_the_finding_is_recorded_once_until_resolved(finding) -> None:
    mod, added = finding
    await mod.report_backend_refused_internal_key("/api/v2/secrets/system")
    await mod.report_backend_refused_internal_key("/api/v2/secrets/system")
    assert len(added) == 1, "repeated refusals stand for one finding, not one per call"
    event = added[0]
    assert event.event_type == mod.FINDING_EVENT_TYPE and event.severity == "error" and event.resolved is not True
    assert "#20750" in event.message


@pytest.mark.asyncio
async def test_a_failing_finding_never_replaces_the_callers_error(monkeypatch) -> None:
    from services import backend_key_finding as mod

    monkeypatch.setattr(mod, "db_service", MagicMock(session=MagicMock(side_effect=RuntimeError("db down"))))
    await mod.report_backend_refused_internal_key("/x")  # does not raise


def _load_vault_client():
    """vault_client from its file: the conftest stubs `user_management` session-wide."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_vault_client_20750", _ROOT / "user_management/services/vault_client.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _vault(monkeypatch, status: int, internal_key: str, service_key: str):
    vc = _load_vault_client()

    resp = AsyncMock(status=status, ok=status < 400)
    resp.text = AsyncMock(return_value="refused")
    cm = AsyncMock(__aenter__=AsyncMock(return_value=resp), __aexit__=AsyncMock(return_value=False))
    monkeypatch.setattr(vc, "get_http_client", lambda: MagicMock(tracked_request=MagicMock(return_value=cm)))
    monkeypatch.setattr(vc, "_INTERNAL_API_KEY", internal_key)
    monkeypatch.setattr(vc, "_SERVICE_KEY", service_key)
    report = AsyncMock()
    monkeypatch.setitem(
        sys.modules,
        "services.backend_key_finding",
        types.SimpleNamespace(report_backend_refused_internal_key=report),
    )
    return vc, report


@pytest.mark.asyncio
async def test_a_refused_internal_key_reports_the_finding(monkeypatch) -> None:
    vc, report = _vault(monkeypatch, 401, internal_key="k-sample", service_key="")  # pragma: allowlist secret
    with pytest.raises(vc.VaultClientError, match="401"):
        await vc._request("GET", "/api/v2/secrets/system")
    report.assert_awaited_once_with("/api/v2/secrets/system")


@pytest.mark.asyncio
@pytest.mark.parametrize("status, internal_key", [(401, ""), (403, "k-sample"), (500, "k-sample")])
async def test_only_a_refused_internal_key_is_that_finding(monkeypatch, status: int, internal_key: str) -> None:
    """Control: an HMAC 401, a 403 or a 500 is a different fault, and no key-mismatch finding."""
    vc, report = _vault(monkeypatch, status, internal_key=internal_key, service_key="aa" * 32)
    with pytest.raises(vc.VaultClientError):
        await vc._request("GET", "/api/v2/secrets/system")
    report.assert_not_awaited()
