# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every service entry point starts file logging with the ONE call, ``setup_logging()`` (#20894).

Loggers write to the console only until a service's startup calls
``autobot_shared.logging_manager.setup_logging``, so importing a module creates no file (owner
decision 2026-11-09). An entry point that skips the call silently loses its log file. Enumerated
mechanically, never by hand:

* the source each Python systemd unit template runs (``UNIT_TARGETS``; a new unit fails until mapped),
* modules that build an app at module level (``FastAPI``/``Starlette``/``create_app``/``Celery``),
* modules with an ``if __name__ == "__main__":`` block that import the logging manager.

Each must call that function, imported from ``autobot_shared.logging_manager`` (a local function
of the same name does not count), or be exempt here with a reason. ``NO_MANAGER`` exemptions are
checked: the file must not name the logging manager. Tests are not entry points (pytest runs them).
Library modules whose ``__main__`` demo block predates this are frozen in the baseline module and
only go down.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests.entry_points_start_file_logging_20894_baseline import PENDING
from repo_tests.service_units_set_logs_dir_20894_test import _python_units

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_MANAGER = "autobot_shared.logging_manager"
_CALL = "setup_logging"
_APP_FACTORIES = frozenset({"FastAPI", "Starlette", "create_app", "Celery"})
_TEMPLATES = "autobot-slm-backend/ansible/roles"

#: Every Python unit template -> the tracked source its ExecStart runs; None when that source is not
#: in this repo (#21271 tracks those units).
UNIT_TARGETS: dict[str, str | None] = {
    "autobot-infrastructure/autobot-ai-stack/templates/autobot-ai-stack.service": None,
    "autobot-infrastructure/autobot-backend/templates/autobot-user-backend.service": "autobot-backend/main.py",
    "autobot-infrastructure/autobot-npu-worker/templates/autobot-npu-worker.service": (
        "autobot-infrastructure/autobot-npu-worker/docker/npu_inference_server.py"
    ),
    "autobot-infrastructure/autobot-slm-backend/templates/autobot-slm-backend.service": "autobot-slm-backend/main.py",
    f"{_TEMPLATES}/agent_config/templates/autobot-agent.service.j2": None,
    f"{_TEMPLATES}/ai-stack/templates/autobot-ai-stack.service.j2": (
        "autobot-infrastructure/shared/docker/ai-stack/ai_api_server.py"
    ),
    f"{_TEMPLATES}/backend/templates/autobot-backend.service.j2": "autobot-backend/main.py",
    f"{_TEMPLATES}/backend/templates/autobot-celery-beat.service.j2": "autobot-backend/celery_app.py",
    f"{_TEMPLATES}/backend/templates/autobot-celery.service.j2": "autobot-backend/celery_app.py",
    f"{_TEMPLATES}/backend/templates/autobot-mcp-bridge@.service.j2": (
        "autobot-backend/services/mcp_bridge_workers/worker_entrypoint.py"
    ),
    f"{_TEMPLATES}/distributed_setup/templates/autobot-coordinator.service.j2": None,
    f"{_TEMPLATES}/npu-worker/templates/autobot-npu-worker.service.j2": (
        f"{_TEMPLATES}/npu-worker/templates/npu-worker.py.j2"
    ),
    f"{_TEMPLATES}/slm_agent/templates/slm-agent.service.j2": "autobot-slm-backend/slm/agent/agent.py",
    f"{_TEMPLATES}/slm_manager/templates/autobot-slm-backend.service.j2": "autobot-slm-backend/main.py",
    f"{_TEMPLATES}/tts-worker/templates/autobot-tts-worker.service.j2": (
        f"{_TEMPLATES}/tts-worker/templates/tts-worker.py.j2"
    ),
}

_STDLIB = "stdlib logging only; never uses the logging manager, so it has no deferred file handler"
#: Entry points that never use the logging manager. Checked: the file must not name it.
NO_MANAGER: dict[str, str] = {
    "autobot-infrastructure/autobot-npu-worker/docker/npu_inference_server.py": _STDLIB,
    "autobot-infrastructure/shared/docker/ai-stack/ai_api_server.py": _STDLIB,
    f"{_TEMPLATES}/npu-worker/templates/npu-worker.py.j2": _STDLIB,
    f"{_TEMPLATES}/tts-worker/templates/tts-worker.py.j2": _STDLIB,
    "autobot-slm-backend/slm/agent/agent.py": _STDLIB,
}

#: Entry points that use the manager and deliberately stay console-only.
CONSOLE_ONLY: dict[str, str] = {
    "pipeline-scripts/pr_conflict_gate.py": "CI job script: the job log is its output, a file would be discarded",
}


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        name.endswith("_test.py")
        or name.startswith("test_")
        or name == "conftest.py"
        or path.startswith(("tests/", "repo_tests/"))
        or "/tests/" in path
    )


def _parse(root: Path, path: str) -> ast.Module | None:
    try:
        return ast.parse((root / path).read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _is_main_guard(node: ast.stmt) -> bool:
    test = node.test if isinstance(node, ast.If) else None
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators)
    )


def _builds_app(node: ast.stmt) -> bool:
    value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    return (func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)) in _APP_FACTORIES


def _imports_manager(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _MANAGER:
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "autobot_shared":
            if any(a.name == "logging_manager" for a in node.names):
                return True
        if isinstance(node, ast.Import) and any(a.name == _MANAGER for a in node.names):
            return True
    return False


def _bound_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Names bound to the manager's ``setup_logging``, and names bound to the manager module itself."""
    funcs: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _MANAGER:
            funcs |= {a.asname or a.name for a in node.names if a.name == _CALL}
        elif isinstance(node, ast.ImportFrom) and node.module == "autobot_shared":
            modules |= {a.asname or a.name for a in node.names if a.name == "logging_manager"}
        elif isinstance(node, ast.Import):
            modules |= {a.asname for a in node.names if a.name == _MANAGER and a.asname}
    return funcs, modules


def calls_setup_logging(tree: ast.Module) -> bool:
    """True when *tree* calls ``setup_logging`` imported from the logging manager (nested imports count)."""
    funcs, modules = _bound_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in funcs:
            return True
        if isinstance(func, ast.Attribute) and func.attr == _CALL and isinstance(func.value, ast.Name):
            if func.value.id in modules:
                return True
    return False


def entry_points(root: Path, paths: list[str], unit_targets: dict[str, str | None]) -> set[str]:
    """Unit targets present in the tree, module-level app builders, and ``__main__`` modules using the manager."""
    found = {t for t in unit_targets.values() if t and (root / t).is_file()}
    for path in paths:
        if _is_test(path):
            continue
        text = (root / path).read_text(encoding="utf-8")
        if "__main__" not in text and not any(f"{f}(" in text for f in _APP_FACTORIES):
            continue
        tree = _parse(root, path)
        if tree is None:
            continue
        if any(_builds_app(n) for n in tree.body):
            found.add(path)
        elif any(_is_main_guard(n) for n in tree.body) and _imports_manager(tree):
            found.add(path)
    return found


def missing_call(root: Path, entries: set[str], exempt: set[str]) -> list[str]:
    """Entry points that neither call ``setup_logging`` nor are exempt."""
    missing = []
    for path in sorted(entries - exempt):
        tree = _parse(root, path)
        if tree is None or not calls_setup_logging(tree):
            missing.append(path)
    return missing


def _live_entries() -> set[str]:
    return entry_points(_ROOT, tracked_paths(_ROOT, "*.py"), UNIT_TARGETS)


def test_every_python_unit_is_mapped_to_its_source() -> None:
    units = set(_python_units(_ROOT))
    assert units == set(
        UNIT_TARGETS
    ), f"unmapped unit(s): {sorted(units - set(UNIT_TARGETS))}; gone: {sorted(set(UNIT_TARGETS) - units)}"
    gone = [t for t in UNIT_TARGETS.values() if t and not (_ROOT / t).is_file()]
    assert not gone, f"mapped source(s) not in the tree: {gone}"


def test_every_entry_point_calls_setup_logging() -> None:
    entries = _live_entries()
    assert len(entries) >= 100, f"discovery found only {len(entries)} entry points"
    missing = missing_call(_ROOT, entries, set(NO_MANAGER) | set(CONSOLE_ONLY) | set(PENDING))
    assert not missing, f"entry point(s) never call {_MANAGER}.{_CALL}(), so they write no log file: {missing}"


def test_no_manager_exemptions_hold() -> None:
    named = [p for p in NO_MANAGER if "logging_manager" in (_ROOT / p).read_text(encoding="utf-8")]
    assert not named, f"exempt as manager-free, but now name the logging manager -- call {_CALL}(): {named}"


def test_exemptions_and_pending_are_not_stale() -> None:
    entries = _live_entries()
    stale = sorted(p for p in (*NO_MANAGER, *CONSOLE_ONLY, *PENDING) if p not in entries)
    assert not stale, f"no longer an entry point -- drop from the exemptions/PENDING: {stale}"
    done = sorted(p for p in PENDING if calls_setup_logging(_parse(_ROOT, p) or ast.Module(body=[], type_ignores=[])))
    assert not done, f"now call {_CALL}() -- drop from PENDING: {done}"


def _plant(root: Path, files: dict[str, str]) -> list[str]:
    for path, body in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(body, encoding="utf-8")
    return sorted(files)


def test_control_an_entry_point_without_the_call_is_reported(tmp_path: Path) -> None:
    """Control: a synthetic entry point of every kind without the call fails; with it, passes."""
    imp = f"from {_MANAGER} import get_logger\n"
    paths = _plant(
        tmp_path,
        {
            "svc/app.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "svc/cli.py": imp + "if __name__ == '__main__':\n    get_logger(__name__)\n",
            "svc/unit_target.py": "def main():\n    pass\n",
            "svc/ok.py": f"from {_MANAGER} import {_CALL}\napp = FastAPI()\n{_CALL}()\n",
            "svc/lazy.py": f"def main():\n    from {_MANAGER} import {_CALL}\n    {_CALL}()\napp = Celery('x')\n",
            "svc/own_fn.py": imp + f"def {_CALL}():\n    pass\nif __name__ == '__main__':\n    {_CALL}()\n",
            "svc/x_test.py": imp + "if __name__ == '__main__':\n    pass\n",
        },
    )
    entries = entry_points(tmp_path, paths, {"svc/u.service": "svc/unit_target.py"})
    assert "svc/x_test.py" not in entries
    missing = missing_call(tmp_path, entries, set())
    assert missing == ["svc/app.py", "svc/cli.py", "svc/own_fn.py", "svc/unit_target.py"]
    assert missing_call(tmp_path, entries, {"svc/app.py", "svc/cli.py", "svc/own_fn.py", "svc/unit_target.py"}) == []
