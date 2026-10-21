# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fork-return guard for the helper cores shared in #18557 (slice 1).

Three near-identical copies were collapsed into one home each. This fails when a
second copy of any of them reappears:

* the "role must exist in this company" query -> ``llc/services/_role_guard.py``
* the worker's local-IP-toward-the-backend lookup -> ``app/utils/local_ip.py``
* the "unknown or bare-PENDING Celery task is a 404" check -> ``utils/celery_task_status.py``

The detectors read the syntax tree, so a comment or docstring naming the pattern is not a copy.
They are pure functions of source text so the guard can be shown to fail on a re-introduced copy.
The populations are named directories and files, not a tree sweep: a copy in a brand-new module
is outside this guard, which is why the helper docstrings name their callers.
"""

from __future__ import annotations

import ast
import os

from repo_tests._paths import repo_root

_ROLE_DIR = "autobot-backend/llc/services"
_ROLE_GUARD = f"{_ROLE_DIR}/_role_guard.py"
_COMPANY_OS_LOADERS = f"{_ROLE_DIR}/company_os/loaders.py"
_ROLE_CALLERS = ("role_assignment.py", "role_credential.py", "role_tool.py", "role_workflow.py")
_WORKER_UTILS = "autobot-npu-worker/resources/windows-npu-worker/app/utils"
_LOCAL_IP_HOME = f"{_WORKER_UTILS}/local_ip.py"
_LOCAL_IP_USERS = (f"{_WORKER_UTILS}/config_bootstrap.py", f"{_WORKER_UTILS}/backend_telemetry.py")
_CELERY_HOME = "autobot-backend/utils/celery_task_status.py"
_CELERY_404_SITES = (
    "autobot-backend/api/analytics.py",
    "autobot-backend/api/analytics_bug_prediction.py",
    "autobot-backend/api/codebase_analytics/endpoints/import_tree.py",
    "autobot-backend/api/codebase_analytics/endpoints/dependencies.py",
    "autobot-backend/api/codebase_analytics/endpoints/duplicates.py",
)


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def _functions(source: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(source)
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _attr(node: ast.AST, owner: str, name: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == name
        and isinstance(node.value, ast.Name)
        and node.value.id == owner
    )


def has_inline_role_query(source: str) -> bool:
    """A function that runs ``select(Role.id)`` scoped by ``Role.org_id`` -- the role-exists check."""
    for fn in _functions(source):
        nodes = list(ast.walk(fn))
        selects_id = any(
            isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "select"
            and any(_attr(a, "Role", "id") for a in n.args)
            for n in nodes
        )
        if selects_id and any(_attr(n, "Role", "org_id") for n in nodes):
            return True
    return False


def _is_route_probe(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """The body shape: a ``SOCK_DGRAM`` socket, a ``connect`` and a ``getsockname`` -- whatever it is called."""
    nodes = list(ast.walk(fn))
    dgram = any(isinstance(n, ast.Attribute) and n.attr == "SOCK_DGRAM" for n in nodes)
    calls = {n.func.attr for n in nodes if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    return dgram and {"connect", "getsockname"} <= calls


def defines_local_ip_lookup(source: str) -> bool:
    return any(fn.name in ("get_local_ip", "_get_local_ip") or _is_route_probe(fn) for fn in _functions(source))


def has_inline_celery_404(source: str) -> bool:
    """A function that maps a Celery result and tests the bare ``"pending"`` status itself."""
    for fn in _functions(source):
        nodes = list(ast.walk(fn))
        maps = any(isinstance(n, ast.Call) and getattr(n.func, "id", None) == "celery_result_to_status" for n in nodes)
        pending = any(isinstance(n, ast.Constant) and n.value == "pending" for n in nodes)
        if maps and pending:
            return True
    return False


def _role_modules() -> list[str]:
    names = sorted(n for n in os.listdir(repo_root() / _ROLE_DIR) if n.startswith("role_") and n.endswith(".py"))
    return [f"{_ROLE_DIR}/{n}" for n in names]


def test_role_exists_query_lives_once_in_the_role_guard() -> None:
    modules = _role_modules()
    assert len(modules) >= 6, f"role_*.py population shrank to {len(modules)}: the guard is reading nothing"
    assert has_inline_role_query(_read(_ROLE_GUARD)), "the shared core no longer holds the query"
    modules.append(_COMPANY_OS_LOADERS)
    copies = [rel for rel in modules if has_inline_role_query(_read(rel))]
    assert not copies, f"#18557: {copies} re-implement the role-exists query; call ensure_role_in_company"


def test_company_os_loader_delegates_the_query_and_keeps_its_own_error() -> None:
    source = _read(_COMPANY_OS_LOADERS)
    assert "role_exists_in_company(session, company_id, role_id)" in source and "CompanyOsNotFound(" in source


def test_every_role_caller_delegates_to_the_guard() -> None:
    for name in _ROLE_CALLERS:
        assert "ensure_role_in_company(session, company_id, role_id)" in _read(f"{_ROLE_DIR}/{name}"), name


def test_local_ip_lookup_has_one_home() -> None:
    assert defines_local_ip_lookup(_read(_LOCAL_IP_HOME))
    copies = [rel for rel in _LOCAL_IP_USERS if defines_local_ip_lookup(_read(rel))]
    assert not copies, f"#18557: {copies} define their own local-IP lookup; import utils.local_ip"


def test_celery_404_check_has_one_home() -> None:
    assert has_inline_celery_404(_read(_CELERY_HOME))
    copies = [rel for rel in _CELERY_404_SITES if has_inline_celery_404(_read(rel))]
    assert not copies, f"#18557: {copies} inline the pending->404 check; call known_task_status_or_404"


_OLD_ROLE_COPY = """
class S:
    async def _require_role(self, session, company_id, role_id):
        result = await session.execute(select(Role.id).where(Role.id == role_id, Role.org_id == company_id))
        if result.scalar_one_or_none() is None:
            raise ValueError("x")
"""
_DELEGATING_ROLE = """
class S:
    async def _require_role(self, session, company_id, role_id):
        await ensure_role_in_company(session, company_id, role_id)
"""
_OLD_IP_COPY = """
def whatever_name(host):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((host, 80))
    return sock.getsockname()[0]
"""
_DELEGATING_IP = """
def start(host):
    return get_local_ip(host)
"""
_OLD_CELERY_COPY = """
async def get_x_status(task_id):
    status = celery_result_to_status(AsyncResult(task_id))
    if status is None or status["status"] == "pending":
        raise HTTPException(status_code=404, detail="nf")
    return status
"""
_DELEGATING_CELERY = """
async def get_x_status(task_id):
    return known_task_status_or_404(task_id)
"""


def test_role_detector_separates_an_old_copy_from_a_delegating_caller() -> None:
    assert has_inline_role_query(_OLD_ROLE_COPY)
    assert not has_inline_role_query(_DELEGATING_ROLE)


def test_local_ip_detector_catches_a_renamed_copy_by_body_shape() -> None:
    assert defines_local_ip_lookup(_OLD_IP_COPY)
    assert defines_local_ip_lookup("def get_local_ip(h):\n    return h\n")
    assert not defines_local_ip_lookup(_DELEGATING_IP)


def test_celery_detector_separates_an_old_copy_from_a_delegating_caller() -> None:
    assert has_inline_celery_404(_OLD_CELERY_COPY)
    assert not has_inline_celery_404(_DELEGATING_CELERY)


def test_local_ip_cache_is_keyed_by_backend_host() -> None:
    import importlib.util
    import socket
    from unittest import mock

    spec = importlib.util.spec_from_file_location("local_ip_18557", repo_root() / _LOCAL_IP_HOME)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ips = iter(["10.0.0.1", "10.0.0.2"])

    class _Sock:
        def connect(self, addr):
            self.ip = next(ips)

        def getsockname(self):
            return (self.ip, 0)

        def close(self):
            pass

    with mock.patch.object(socket, "socket", lambda *a, **k: _Sock()):
        assert mod.get_local_ip("host-a") == "10.0.0.1"
        assert mod.get_local_ip("host-b") == "10.0.0.2"
        assert mod.get_local_ip("host-a") == "10.0.0.1"
    assert set(mod._local_ip_cache) == {"host-a", "host-b"}
