# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One deploy path for agent code, one home for SLM_REPO_PATH (#19352, #15708).

#19352: the schedule executor pushed agent code with code_distributor's rsync into ``/opt/slm-agent``,
the directory #1163 retired, without autobot_shared. It now runs the fleet-sync job that run-now and
update-all use (``update-all-nodes.yml``), which deploys autobot_shared before the slm_agent role.

#15708: ``SLM_REPO_PATH`` was read twice with two fallbacks (a checkout and the install root that
contains it). It is read once, in ``services/git_tracker.py``; every other module imports it.

Each guard is a function over source text, and each has a control that feeds it a deliberate copy.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from testkit.fake_async_session import FakeAsyncSession

_SLM = Path(__file__).resolve().parents[2]
_EXECUTOR = _SLM / "services" / "schedule_executor.py"
_PLAYBOOK = _SLM / "ansible" / "playbooks" / "update-all-nodes.yml"
_REPO_PATH_HOME = "services/git_tracker.py"
_RETIRED_AGENT_ROOT = "/opt/slm-agent"
#: Files that name the retired root as history or as the thing forbidden, not as a target.
_RETIRED_ROOT_HISTORY = frozenset(
    {"tests/test_cleanup_never_destroys_data_14856.py", Path(__file__).resolve().relative_to(_SLM).as_posix()}
)


def _slm_sources(include_tests: bool) -> dict[str, str]:
    """rel path -> source for every tracked-looking SLM Python file (venvs and caches skipped)."""
    out = {}
    for path in _SLM.rglob("*.py"):
        rel = path.relative_to(_SLM).as_posix()
        if any(part in {"venv", ".venv", "node_modules", "__pycache__"} for part in path.parts):
            continue
        if not include_tests and (rel.startswith("tests/") or rel.endswith("_test.py") or "/test_" in rel):
            continue
        out[rel] = path.read_text(encoding="utf-8")
    return out


def _is_env_read(node: ast.AST, name: str) -> bool:
    """``env(name)`` (the registry), ``os.environ.get(name, ...)``, ``os.getenv(name, ...)``, ``os.environ[name]``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "env":
        return bool(node.args) and isinstance(node.args[0], ast.Constant) and node.args[0].value == name
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "getenv"}:
        return bool(node.args) and isinstance(node.args[0], ast.Constant) and node.args[0].value == name
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return node.slice.value == name and "environ" in ast.unparse(node.value)
    return False


def repo_path_homes(sources: dict[str, str]) -> list[str]:
    """Files that read SLM_REPO_PATH or bind a module-level DEFAULT_REPO_PATH to anything but an import."""
    homes = set()
    for rel, text in sources.items():
        tree = ast.parse(text)
        if any(_is_env_read(node, "SLM_REPO_PATH") for node in ast.walk(tree)):
            homes.add(rel)
        for stmt in tree.body:
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [getattr(stmt, "target", None)]
            if any(isinstance(t, ast.Name) and t.id == "DEFAULT_REPO_PATH" for t in targets):
                homes.add(rel)
    return sorted(homes)


def retired_root_sites(sources: dict[str, str]) -> list[str]:
    """Files whose string literals name the agent root #1163 retired."""
    return sorted(
        rel
        for rel, text in sources.items()
        if rel not in _RETIRED_ROOT_HISTORY
        and any(
            isinstance(n, ast.Constant) and isinstance(n.value, str) and _RETIRED_AGENT_ROOT in n.value
            for n in ast.walk(ast.parse(text))
        )
    )


# ---- #15708: one home for SLM_REPO_PATH -------------------------------------------------------------


def test_slm_repo_path_has_exactly_one_home():
    assert repo_path_homes(_slm_sources(include_tests=False)) == [_REPO_PATH_HOME]


def test_slm_repo_path_guard_fails_on_a_deliberate_copy():
    sources = _slm_sources(include_tests=False)
    sources["services/code_distributor.py"] += '\nDEFAULT_REPO_PATH = os.environ.get("SLM_REPO_PATH", "/x")\n'
    sources["services/other.py"] = 'import os\nROOT = os.getenv("SLM_REPO_PATH")\n'
    sources["services/third.py"] = 'from autobot_shared.env_registry import env\nROOT = env("SLM_REPO_PATH")\n'
    expected = ["services/code_distributor.py", _REPO_PATH_HOME, "services/other.py", "services/third.py"]
    assert repo_path_homes(sources) == expected


def registrations(sources: dict[str, str], name: str) -> list[str]:
    """Registry modules that register *name*: its default and meaning are written where it is registered."""
    return sorted(
        rel
        for rel, text in sources.items()
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) in {"_register", "EnvVarSpec"}
        and name in [_literal(a) for a in [*node.args[:1], *(k.value for k in node.keywords if k.arg == "name")]]
    )


def _literal(node: ast.AST):
    return node.value if isinstance(node, ast.Constant) else None


def _registry_sources() -> dict[str, str]:
    shared = _SLM.parent / "autobot_shared"
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(shared.glob("env_registry*.py"))}


def _default_arg(sources: dict[str, str], rel: str, name: str) -> str:
    """Source of the default given to *name*'s one registration in *rel*."""
    for node in ast.walk(ast.parse(sources[rel])):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "_register" and _literal(node.args[0]) == name:
            return ast.unparse(node.args[2])
    raise AssertionError(f"{name} is not registered in {rel}")


def _git_tracker_fallback() -> str:
    tree = ast.parse((_SLM / _REPO_PATH_HOME).read_text(encoding="utf-8"))
    assigns = [n for n in tree.body if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "DEFAULT_REPO_PATH"]
    return ast.unparse(assigns[0].value.args[1])


def test_slm_repo_path_is_documented_once_and_both_defaults_are_the_fleet_constant():
    sources = _registry_sources()
    assert registrations(sources, "SLM_REPO_PATH") == ["env_registry_npu.py"]
    assert _default_arg(sources, "env_registry_npu.py", "SLM_REPO_PATH") == "FLEET_CODE_SOURCE_DIR"
    assert _git_tracker_fallback() == "FLEET_CODE_SOURCE_DIR"


def test_registration_guard_fails_on_a_second_registration():
    sources = _registry_sources()
    sources["env_registry_slm.py"] += '\n_register("SLM_REPO_PATH", str, "/x", "copy", "slm")\n'
    assert registrations(sources, "SLM_REPO_PATH") == ["env_registry_npu.py", "env_registry_slm.py"]


def test_code_distributor_packages_from_the_git_tracker_checkout():
    tree = ast.parse((_SLM / "services" / "code_distributor.py").read_text(encoding="utf-8"))
    imports = {(n.module, a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert ("services.git_tracker", "DEFAULT_REPO_PATH") in imports


# ---- #19352: nothing targets the retired agent root ---------------------------------------------------


def test_no_slm_code_targets_the_retired_agent_root():
    assert retired_root_sites(_slm_sources(include_tests=True)) == []


def test_retired_root_guard_fails_on_a_deliberate_copy():
    sources = {"services/code_distributor.py": 'REMOTE_AGENT_PATH = "/opt/slm-agent"\n'}
    assert retired_root_sites(sources) == ["services/code_distributor.py"]


# ---- #19352: the playbook every sync runs deploys autobot_shared before the agent -----------------------


def _flat_tasks(tasks: list) -> list[dict]:
    out = []
    for task in tasks or []:
        out.append(task)
        out.extend(_flat_tasks(task.get("block")))
    return out


def _is_shared_deploy(task: dict) -> bool:
    return str((task.get("unarchive") or {}).get("src", "")).endswith("/shared.tar.gz")


def _is_agent_role(task: dict) -> bool:
    return (task.get("ansible.builtin.import_role") or {}).get("name") == "slm_agent"


def shared_first_violations(plays: list[dict]) -> list[str]:
    """Plays where the slm_agent role is reached on a host that has not been given autobot_shared yet."""
    bad = []
    for play in plays:
        tasks = _flat_tasks(play.get("tasks"))
        agent_at = [i for i, t in enumerate(tasks) if _is_agent_role(t)]
        if not agent_at:
            continue
        guards = {str(t.get("when", "")) for t in tasks[: agent_at[0]] if _is_shared_deploy(t)}
        covered = "" in guards or {"'backend' in group_names", "'backend' not in group_names"} <= guards
        if not covered:
            bad.append(play["name"])
    return bad


def test_update_all_nodes_deploys_autobot_shared_before_the_agent_role():
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    agent_plays = [p["name"] for p in plays if any(_is_agent_role(t) for t in _flat_tasks(p.get("tasks")))]
    assert len(agent_plays) == 2, agent_plays  # Play 1 (SLM server) and Play 2 (infrastructure)
    assert shared_first_violations(plays) == []


def test_shared_first_guard_fails_when_the_agent_comes_first():
    agent = {"ansible.builtin.import_role": {"name": "slm_agent"}}
    shared = {"unarchive": {"src": "{{ deploy_tmp }}/shared.tar.gz"}}
    half = {**shared, "when": "'backend' in group_names"}
    assert shared_first_violations([{"name": "late", "tasks": [{"block": [agent]}, shared]}]) == ["late"]
    assert shared_first_violations([{"name": "half", "tasks": [half, agent]}]) == ["half"]
    assert shared_first_violations([{"name": "ok", "tasks": [shared, {"block": [agent]}]}]) == []


# ---- #19352: a due schedule runs the fleet-sync job -------------------------------------------------


@pytest.fixture
def executor():
    try:
        spec = importlib.util.spec_from_file_location("_schedule_executor_19352", _EXECUTOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except ImportError as exc:  # the executor needs the live SLM service graph
        pytest.skip(f"schedule_executor not importable in this harness: {exc}")
    return module


def _fake_code_sync(monkeypatch, node_statuses, queue_error=None):
    calls = []
    job = SimpleNamespace(nodes={nid: SimpleNamespace(status="pending") for nid in node_statuses})

    async def queue_schedule_job(db, schedule, nodes):
        calls.append(("queue", schedule.name, [n.node_id for n in nodes]))
        if queue_error:
            raise queue_error
        return job

    async def _run_fleet_sync_job(run_job):
        calls.append(("run", run_job is job))
        for nid, status in node_statuses.items():
            run_job.nodes[nid].status = status

    fake = ModuleType("api.code_sync")
    fake.queue_schedule_job, fake._run_fleet_sync_job = queue_schedule_job, _run_fleet_sync_job
    monkeypatch.setitem(sys.modules, "api.code_sync", fake)
    return calls


def _wire(executor, monkeypatch, node_ids):
    nodes = [SimpleNamespace(node_id=n) for n in node_ids]
    monkeypatch.setattr(executor, "db_service", SimpleNamespace(session=lambda: FakeAsyncSession()))

    async def _targets(db, schedule):
        return nodes

    monkeypatch.setattr(executor, "get_schedule_target_nodes", _targets)
    return SimpleNamespace(id=7, name="nightly")


@pytest.mark.asyncio
async def test_due_schedule_runs_the_fleet_sync_job_and_reports_its_outcome(executor, monkeypatch):
    calls = _fake_code_sync(monkeypatch, {"n1": "success", "n2": "failed"})
    schedule = _wire(executor, monkeypatch, ["n1", "n2"])
    assert await executor.execute_schedule(schedule) == (True, "Synced 1/2 nodes (1 failed)")
    assert calls == [("queue", "nightly", ["n1", "n2"]), ("run", True)]


@pytest.mark.asyncio
async def test_due_schedule_skips_while_a_fleet_sync_runs(executor, monkeypatch):
    from fastapi import HTTPException

    calls = _fake_code_sync(monkeypatch, {"n1": "success"}, queue_error=HTTPException(status_code=409))
    schedule = _wire(executor, monkeypatch, ["n1"])
    assert await executor.execute_schedule(schedule) == (False, "Fleet sync already in progress")
    assert [c[0] for c in calls] == ["queue"]


def test_executor_has_no_second_deploy_path():
    text = _EXECUTOR.read_text(encoding="utf-8")
    assert "code_distributor" not in text and "trigger_node_sync" not in text
