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


#: The per-destination lookup every backend env render uses; the structural test below pins it.
_LOOKUP = (
    "(internal_api_key_by_file | default({})).get({dest}, "
    "internal_api_key_resolved | default(autobot_internal_api_key))"
)


def _run(tmp_path: Path, canonical: str, env_key: str, etc_key: str) -> tuple[dict, str]:
    """Resolve with a canonical file and the two backend env files holding the given keys ('' = none)."""
    (tmp_path / "slm-secrets.env").write_text(f"AUTOBOT_INTERNAL_API_KEY={canonical}\n" if canonical else "")
    files = {"env": tmp_path / "code.env", "etc": tmp_path / "etc.env"}
    for name, key in (("env", env_key), ("etc", etc_key)):
        files[name].write_text(f"OTHER=1\nAUTOBOT_INTERNAL_API_KEY={key}\n" if key else "OTHER=1\n")
    lines = [
        "- hosts: localhost",
        "  gather_facts: false",
        "  tasks:",
        f"    - ansible.builtin.include_tasks: {_ANSIBLE / '_shared' / 'tasks' / _SHARED}",
        "    - ansible.builtin.debug:",
        '        msg: "RENDER {{ item }} {{ ' + _LOOKUP.replace("{dest}", "item") + ' }}"',
        '      loop: "{{ internal_api_key_current_env_files }}"',
        "    - ansible.builtin.debug:",
        "        msg: \"RESULT {{ {'mismatch': internal_api_key_mismatch | bool,"
        " 'differing': internal_api_key_differing_files | map('basename') | list} | to_json }}\"",
    ]
    (tmp_path / "p.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    extra = {
        "ansible_become": False,
        "internal_api_key_canonical_file": str(tmp_path / "slm-secrets.env"),
        "internal_api_key_current_env_files": [str(files["env"]), str(files["etc"])],
    }
    cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local", str(tmp_path / "p.yml"), "-e", json.dumps(extra)]
    env = {"ANSIBLE_LOG_PATH": str(tmp_path / "a.log"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120, check=False).stdout  # nosec B603
    renders = {}
    for line in out.splitlines():
        if '"msg": "RENDER ' in line:
            path, _, key = line.split('"msg": "RENDER ', 1)[1].rstrip('"').partition(" ")
            renders[Path(path).name] = key
    result_line = next(x for x in out.splitlines() if '"msg": "RESULT ' in x)
    result = json.loads(result_line.split('"msg": "RESULT ', 1)[1].rstrip('"').replace('\\"', '"'))
    return {"renders": renders, **result}, out


_needs_ansible = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible not installed")

_A, _B, _C = "slm-sample", "backend-sample", "other-sample"  # pragma: allowlist secret


@_needs_ansible
@pytest.mark.parametrize(
    "canonical, env_key, etc_key, renders, differing",
    [
        (_A, "", "", {"code.env": _A, "etc.env": _A}, []),  # fresh install: the canonical key
        (_A, _A, _A, {"code.env": _A, "etc.env": _A}, []),  # all agree: unchanged
        (_A, _B, _B, {"code.env": _B, "etc.env": _B}, ["code.env", "etc.env"]),  # both differ from the SLM
        (_A, _B, _C, {"code.env": _B, "etc.env": _C}, ["code.env", "etc.env"]),  # the files disagree
        (_A, _A, _C, {"code.env": _A, "etc.env": _C}, ["etc.env"]),  # one file drifted
    ],
    ids=["fresh-install", "all-agree", "both-differ", "files-disagree", "one-drifted"],
)
def test_each_file_keeps_its_own_key_and_a_difference_is_named(
    tmp_path: Path, canonical: str, env_key: str, etc_key: str, renders: dict, differing: list
) -> None:
    """Never a silent rewrite of a stored credential (#17038), in either file, and never a silent pass."""
    result, out = _run(tmp_path, canonical, env_key, etc_key)
    assert result["renders"] == renders
    assert result["mismatch"] is bool(differing) and sorted(result["differing"]) == differing
    assert ("FINDING #20750: the backend's" in out) is bool(differing)


@_needs_ansible
def test_an_unreadable_canonical_key_is_a_finding_and_nothing_is_rewritten(tmp_path: Path) -> None:
    result, out = _run(tmp_path, canonical="", env_key=_B, etc_key=_B)
    assert result["renders"] == {"code.env": _B, "etc.env": _B}
    assert "could not be read" in out


@_needs_ansible
def test_the_findings_never_print_a_key(tmp_path: Path) -> None:
    _result, out = _run(tmp_path, _A, _B, _C)
    findings = [line for line in out.splitlines() if "FINDING #20750" in line]
    assert findings and not any(v in line for line in findings for v in (_A, _B, _C))


@pytest.mark.parametrize(
    "rel, dest",
    [
        ("roles/backend/tasks/main.yml", "autobot_backend_env_file"),
        ("roles/backend/tasks/main.yml", "(backend_code_dir | default(backend_install_dir)) ~ '/.env'"),
        ("roles/backend/tasks/env_only.yml", "backend_env_dest"),
    ],
)
def test_every_backend_env_render_writes_its_own_files_key(rel: str, dest: str) -> None:
    renders = [t for t in _walk(_yaml(rel)) if (t.get("ansible.builtin.template") or {}).get("src") == "backend.env.j2"]
    lookups = [str((t.get("vars") or {}).get("internal_api_key_render", "")) for t in renders]
    assert "{{ " + _LOOKUP.replace("{dest}", dest) + " }}" in lookups, f"{rel}: a render for {dest} without the lookup"


def test_the_template_renders_the_per_file_key() -> None:
    text = (_ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2").read_text(encoding="utf-8")
    assert "AUTOBOT_INTERNAL_API_KEY={{ internal_api_key_render | default(autobot_internal_api_key) }}" in text


# --- the SLM side: the refusal becomes an admin-visible finding ---------------------------------


@pytest.fixture
def finding(monkeypatch):
    """The finding writer against the shared fake session (#18883): no finding pending, then one."""
    from services import backend_key_finding as mod
    from testkit.fake_async_session import FakeAsyncSession, FakeResult

    # One canned answer per statement: the advisory lock, then the pending-finding check (none, then one).
    session = FakeAsyncSession(results=[FakeResult([]), FakeResult([]), FakeResult([]), FakeResult([1])])
    monkeypatch.setattr(mod, "_last_check", [float("-inf")])

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "db_service", MagicMock(session=lambda: _Ctx()))
    # The conftest stubs `models` session-wide; the writer's own logic is what is under test here.
    monkeypatch.setattr(mod, "NodeEvent", _RecordedEvent)
    monkeypatch.setattr(mod, "EventSeverity", types.SimpleNamespace(ERROR=types.SimpleNamespace(value="error")))
    monkeypatch.setattr(mod, "select", lambda *_a: MagicMock())
    # The SLM conftest stubs sqlalchemy too; a recording text() keeps the lock statement inspectable.
    monkeypatch.setattr(mod, "text", lambda sql: types.SimpleNamespace(bindparams=lambda **kw: f"{sql} {kw}"))
    return mod, session


class _RecordedEvent(types.SimpleNamespace):
    """A NodeEvent stand-in that keeps its constructor arguments; the class attributes feed the query."""

    id = node_id = event_type = resolved = MagicMock()


@pytest.mark.asyncio
async def test_the_finding_is_recorded_once_until_resolved(finding) -> None:
    mod, session = finding
    await mod.report_backend_refused_internal_key("/api/v2/secrets/system")
    mod._last_check[0] = float("-inf")  # past the rate limit, so the second call reaches the database check
    await mod.report_backend_refused_internal_key("/api/v2/secrets/system")
    assert len(session.added) == 1 and session.commits == 1, "repeated refusals are one finding, not one per call"
    locks = [str(st) for st in session.statements if "pg_advisory_xact_lock" in str(st)]
    assert len(locks) == 2, "each check holds the advisory lock, so concurrent workers can't both insert"
    event = session.added[0]
    assert event.event_type == mod.FINDING_EVENT_TYPE and event.severity == "error" and event.resolved is not True
    assert "#20750" in event.message


@pytest.mark.asyncio
async def test_a_burst_of_refusals_checks_the_database_once_per_interval(finding) -> None:
    mod, session = finding
    for _ in range(5):
        await mod.report_backend_refused_internal_key("/api/v2/secrets/system")
    assert len(session.statements) == 2, "one lock and one check for the whole burst, not a query per 401"


@pytest.mark.asyncio
async def test_a_failing_finding_never_replaces_the_callers_error(monkeypatch) -> None:
    from services import backend_key_finding as mod

    monkeypatch.setattr(mod, "db_service", MagicMock(session=MagicMock(side_effect=RuntimeError("db down"))))
    monkeypatch.setattr(mod, "_last_check", [float("-inf")])
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
