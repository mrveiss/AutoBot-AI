# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every LAUNCHED Python target starts file logging with the ONE call, ``setup_logging()`` (#20894).

Loggers write to the console only until a service's startup calls
``autobot_shared.logging_manager.setup_logging``, so importing a module creates no file (owner
decision 2026-11-09). A launched target that skips the call silently loses its log file. The
population is what something actually launches, enumerated mechanically from these sources only:

* the source each Python systemd unit template runs (``UNIT_TARGETS``; a new unit fails until mapped),
* the source each Python docker-compose service runs (``COMPOSE_TARGETS``; a new service fails
  until mapped),
* modules that build an app at module level (``FastAPI``/``Starlette``/``create_app``/``Celery``),
* ``[project.scripts]`` entry points in ``pyproject.toml`` (none today),
* ``__main__`` scripts that import the logging manager under ``SCRIPT_DIRS`` (``scripts/``, ``tools/``,
  ``pipeline-scripts/`` and the infrastructure scripts tree),
* the ops CLIs already wired (``OPS_CLIS``).

A library module's demo ``if __name__ == "__main__":`` block is NOT a service entry point (Trainmaster
ruling 2026-11-09) and is outside the population unless one of the sources above launches it.

Each target must call that function, imported from ``autobot_shared.logging_manager`` (a local
function of the same name does not count), or be exempt here with a reason. ``NO_MANAGER``
exemptions are checked: the file must not name the logging manager. Tests are not entry points.

``calls_setup_logging`` accepts a call at module level, inside the ``__main__`` block, or in a function
that one of those (or a Celery signal handler / app factory) calls, one level deep. It does not prove the
call runs on every path: a call under an unrelated condition still counts.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import tomllib
from pathlib import Path

import yaml
from repo_tests._compose_files import COMPOSE_FILES
from repo_tests._paths import repo_root
from repo_tests.service_units_set_logs_dir_20894_test import _python_units

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._file_size_guard import count_lines
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_MANAGER = "autobot_shared.logging_manager"
_CALL = "setup_logging"
_APP_FACTORIES = frozenset({"FastAPI", "Starlette", "create_app", "Celery"})


def _size_ceiling() -> int:
    """``MAX_LINES`` read from the size hook itself, so the exemption follows the real ceiling."""
    spec = importlib.util.spec_from_file_location("check_python_file_size", _ROOT / "scripts/check_python_file_size.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MAX_LINES


MAX_LINES = _size_ceiling()
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

#: Every Python docker-compose service -> the tracked source it runs ("file::service" keys).
_COMPOSE = "docker-compose.yml"
_OVERRIDE = "docker-compose.override.example.yml"
_MCP_WORKER = "autobot-backend/services/mcp_bridge_workers/worker_entrypoint.py"
COMPOSE_TARGETS: dict[str, str | None] = {
    f"{_OVERRIDE}::autobot-backend": "autobot-backend/main.py",
    f"{_OVERRIDE}::autobot-slm": "autobot-slm-backend/main.py",
    "docker/mcp-bridges.yml::mcp-filesystem": _MCP_WORKER,
    "docker/mcp-bridges.yml::mcp-browser": _MCP_WORKER,
    "docker/mcp-bridges.yml::mcp-vnc": _MCP_WORKER,
    f"{_COMPOSE}::autobot-backend": "autobot-backend/main.py",
    f"{_COMPOSE}::autobot-worker": "autobot-backend/celery_app.py",
    f"{_COMPOSE}::autobot-celery-beat": "autobot-backend/celery_app.py",
    f"{_COMPOSE}::autobot-docker-proxy": "docker/docker-proxy/proxy.py",
    f"{_COMPOSE}::autobot-slm": "autobot-slm-backend/main.py",
    (
        "autobot-infrastructure/shared/docker/compose/docker-compose.secure-sandbox.yml::sandbox-monitor"
    ): "autobot-infrastructure/shared/docker/security/security-monitor.py",
}

#: Directories whose ``__main__`` scripts (importing the manager) are launched by hand or by ops.
SCRIPT_DIRS = ("scripts/", "tools/", "pipeline-scripts/", "autobot-infrastructure/shared/scripts/")

#: Ops CLIs and workers launched by name (not by a unit, compose service or script dir).
OPS_CLIS: frozenset[str] = frozenset(
    {
        "autobot-backend/acp/__main__.py",
        "autobot-backend/api/codebase_analytics/indexing_worker.py",
        "autobot-backend/chat_history/session_reply_backfill.py",
        "autobot-backend/chat_history/session_scope_backfill.py",
        "autobot-backend/database/migrations/001_create_conversation_files.py",
        "autobot-backend/eval/run.py",
        "autobot-backend/pki/cli.py",
        "autobot-backend/services/autoresearch/run_experiment.py",
        "autobot-backend/services/mcp_bridge_workers/worker_entrypoint.py",
        "autobot-backend/services/pricing_refresh.py",
        "autobot-backend/services/workflow_redis_backfill.py",
        "autobot_shared/error_boundaries/__main__.py",
    }
)

_STDLIB = "stdlib logging only; never uses the logging manager, so it has no deferred file handler"
#: Entry points that never use the logging manager. Checked: the file must not name it.
NO_MANAGER: dict[str, str] = {
    "autobot-infrastructure/autobot-npu-worker/docker/npu_inference_server.py": _STDLIB,
    "autobot-infrastructure/shared/docker/ai-stack/ai_api_server.py": _STDLIB,
    f"{_TEMPLATES}/npu-worker/templates/npu-worker.py.j2": _STDLIB,
    f"{_TEMPLATES}/tts-worker/templates/tts-worker.py.j2": _STDLIB,
    "autobot-slm-backend/slm/agent/agent.py": _STDLIB,
    "docker/docker-proxy/proxy.py": _STDLIB,
    "autobot-infrastructure/shared/docker/security/security-monitor.py": _STDLIB,
}

_TOO_BIG = (
    "launched script over the 600-line ceiling: the size hook rejects any edit, so it is wired with its split "
    "(#20894); the exemption leaves once it is under the ceiling"
)
#: Launched scripts that cannot take the call until split. Checked: gone from here once they call it.
OVERSIZE: dict[str, str] = {
    "autobot-infrastructure/shared/scripts/analysis/npu_performance_measurement.py": _TOO_BIG,
    "autobot-infrastructure/shared/scripts/utilities/enhance_workflow_ui.py": _TOO_BIG,
}

#: Entry points that use the manager and deliberately stay console-only.
CONSOLE_ONLY: dict[str, str] = {
    "pipeline-scripts/pr_conflict_gate.py": "CI job script: the job log is its output, a file would be discarded",
}


def _is_test(path: str) -> bool:
    return is_test_filename(path) or path.startswith(("tests/", "repo_tests/")) or "/tests/" in path


def _parse(root: Path, path: str) -> ast.Module | None:
    try:
        return parse_cache.parse((root / path).read_text(encoding="utf-8"))
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


def _bound_in(nodes: list[ast.AST]) -> tuple[set[str], set[str]]:
    """Names bound to the manager's ``setup_logging``, and to the manager module, by imports among *nodes*."""
    funcs: set[str] = set()
    modules: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and node.module == _MANAGER:
            funcs |= {a.asname or a.name for a in node.names if a.name == _CALL}
        elif isinstance(node, ast.ImportFrom) and node.module == "autobot_shared":
            modules |= {a.asname or a.name for a in node.names if a.name == "logging_manager"}
        elif isinstance(node, ast.Import):
            # `import a.b as m` binds m; the unaliased `import a.b` is reached by its dotted name
            modules |= {a.asname or a.name for a in node.names if a.name == _MANAGER}
    return funcs, modules


_HANDLER_DECORATORS = frozenset({"connect", "on_event", "on_startup"})
_FACTORY_NAMES = frozenset({"create_app", "lifespan"})
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _walk_no_defs(nodes: list[ast.stmt]) -> list[ast.AST]:
    """Every node under *nodes* without descending into a def, class or lambda body."""
    out: list[ast.AST] = []
    stack: list[ast.AST] = list(nodes)
    while stack:
        node = stack.pop()
        out.append(node)
        if not isinstance(node, _DEFS):
            stack.extend(ast.iter_child_nodes(node))
    return out


def _startup_statements(tree: ast.Module) -> list[ast.stmt]:
    """Module-level statements, with the ``if __name__ == "__main__":`` body included (not its def)."""
    return list(tree.body) + [s for n in tree.body if _is_main_guard(n) for s in n.body]  # type: ignore[attr-defined]


def _is_handler(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if fn.name in _FACTORY_NAMES:
        return True
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if getattr(target, "attr", getattr(target, "id", None)) in _HANDLER_DECORATORS:
            return True
    return False


def _is_setup_call(node: ast.AST, funcs: set[str], modules: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in funcs
    return isinstance(func, ast.Attribute) and func.attr == _CALL and _dotted(func.value) in modules


def _dotted(node: ast.AST) -> str:
    """``a.b.c`` for a Name/Attribute chain, else an empty string (which is never a bound module)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (head := _dotted(node.value)):
        return f"{head}.{node.attr}"
    return ""


def calls_setup_logging(tree: ast.Module) -> bool:
    """True when startup reaches a ``setup_logging`` imported from the logging manager.

    Reachable means: a call at module level or in the ``__main__`` block; or in a top-level function that
    those reference by name (called or passed, one level deep), that a signal/startup decorator
    registers, or that is an app factory (``create_app``/``lifespan``). A call in a def nothing
    references, or in a nested def, does not count. An import binds ``setup_logging`` only in its own
    lexical scope: module level, or the function that holds it, never a sibling's (#20894).
    """
    startup = _walk_no_defs(_startup_statements(tree))
    funcs, modules = _bound_in(startup)  # module scope: visible to startup and to every function
    if any(_is_setup_call(n, funcs, modules) for n in startup):
        return True
    referenced = {n.id for n in startup if isinstance(n, ast.Name)}
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name not in referenced and not _is_handler(fn):
            continue
        body = _walk_no_defs(fn.body)
        local_funcs, local_modules = _bound_in(body)  # a function's own imports are visible only inside it
        if any(_is_setup_call(n, funcs | local_funcs, modules | local_modules) for n in body):
            return True
    return False


_PY_TOKEN = re.compile(r"^python[\d.]*$")


def compose_python_services(root: Path) -> set[str]:
    """``file::service`` for every compose service (the shared compose enumeration) whose command/entrypoint runs python."""
    return compose_python_services_in(root, list(COMPOSE_FILES.examined(root)))


def compose_python_services_in(root: Path, paths: list[str]) -> set[str]:
    """Same, over an explicit list of compose files."""
    found = set()
    for path in paths:
        services = (yaml.safe_load((root / path).read_text(encoding="utf-8")) or {}).get("services") or {}
        for name, svc in services.items():
            tokens: list[str] = []
            for key in ("entrypoint", "command"):
                value = svc.get(key) or []
                tokens += value.split() if isinstance(value, str) else [str(v) for v in value]
            if any(_PY_TOKEN.match(t) for t in tokens):
                found.add(f"{path}::{name}")
    return found


def console_scripts(root: Path) -> set[str]:
    """Tracked sources of the ``[project.scripts]`` entry points in ``pyproject.toml``."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    found = set()
    for target in (data.get("project", {}).get("scripts") or {}).values():
        module = target.split(":")[0].replace(".", "/")
        found |= {c for c in (f"{module}.py", f"{module}/__init__.py") if (root / c).is_file()}
    return found


def _is_launched_script(root: Path, path: str) -> bool:
    if not path.startswith(SCRIPT_DIRS):
        return False
    tree = _parse(root, path)
    return tree is not None and any(_is_main_guard(n) for n in tree.body) and _imports_manager(tree)


def entry_points(
    root: Path,
    paths: list[str],
    unit_targets: dict[str, str | None],
    compose_targets: dict[str, str | None] | None = None,
    ops_clis: frozenset[str] = frozenset(),
) -> set[str]:
    """The launched population: unit/compose targets, app builders, console scripts, scripts, ops CLIs."""
    targets = [*unit_targets.values(), *(compose_targets or {}).values(), *ops_clis]
    found = {t for t in targets if t and (root / t).is_file()}
    if (root / "pyproject.toml").is_file():
        found |= console_scripts(root)
    for path in paths:
        if _is_test(path):
            continue
        text = (root / path).read_text(encoding="utf-8")
        if "__main__" not in text and not any(f"{f}(" in text for f in _APP_FACTORIES):
            continue
        tree = _parse(root, path)
        if tree is None:
            continue
        if any(_builds_app(n) for n in tree.body) or _is_launched_script(root, path):
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
    return entry_points(_ROOT, tracked_paths(_ROOT, "*.py"), UNIT_TARGETS, COMPOSE_TARGETS, OPS_CLIS)


def test_every_python_unit_is_mapped_to_its_source() -> None:
    units = set(_python_units(_ROOT))
    assert units == set(
        UNIT_TARGETS
    ), f"unmapped unit(s): {sorted(units - set(UNIT_TARGETS))}; gone: {sorted(set(UNIT_TARGETS) - units)}"
    gone = [t for t in UNIT_TARGETS.values() if t and not (_ROOT / t).is_file()]
    assert not gone, f"mapped source(s) not in the tree: {gone}"


def test_every_python_compose_service_is_mapped_to_its_source() -> None:
    services = compose_python_services(_ROOT)
    assert services == set(COMPOSE_TARGETS), (
        f"unmapped compose service(s): {sorted(services - set(COMPOSE_TARGETS))}; "
        f"gone: {sorted(set(COMPOSE_TARGETS) - services)}"
    )
    gone = [t for t in (*COMPOSE_TARGETS.values(), *OPS_CLIS) if t and not (_ROOT / t).is_file()]
    assert not gone, f"mapped source(s) not in the tree: {gone}"


def test_every_launched_target_calls_setup_logging() -> None:
    entries = _live_entries()
    assert len(entries) >= 30, f"discovery found only {len(entries)} launched targets"
    missing = missing_call(_ROOT, entries, set(NO_MANAGER) | set(CONSOLE_ONLY) | set(OVERSIZE))
    assert not missing, f"launched target(s) never call {_MANAGER}.{_CALL}(), so they write no log file: {missing}"


def test_no_manager_exemptions_hold() -> None:
    named = [p for p in NO_MANAGER if "logging_manager" in (_ROOT / p).read_text(encoding="utf-8")]
    assert not named, f"exempt as manager-free, but now name the logging manager -- call {_CALL}(): {named}"


def test_exemptions_are_not_stale() -> None:
    entries = _live_entries()
    stale = sorted(p for p in (*NO_MANAGER, *CONSOLE_ONLY, *OVERSIZE) if p not in entries)
    assert not stale, f"no longer launched -- drop from the exemptions: {stale}"
    small = sorted(p for p in OVERSIZE if (count_lines(_ROOT / p) or 0) <= MAX_LINES)
    assert not small, f"now at or under {MAX_LINES} lines -- wire {_CALL}() and drop from OVERSIZE (#20894): {small}"
    done = completed_exemptions(_ROOT, {"OVERSIZE": OVERSIZE, "CONSOLE_ONLY": CONSOLE_ONLY})
    assert not done, f"now call {_CALL}() -- drop from the exemption: {done}"


def completed_exemptions(root: Path, tables: dict[str, dict[str, str]]) -> list[str]:
    """`TABLE: path` for each exempted entry that now calls the setup, so its exemption is stale (#20894)."""
    empty = ast.Module(body=[], type_ignores=[])
    return sorted(
        f"{name}: {p}" for name, table in tables.items() for p in table if calls_setup_logging(_parse(root, p) or empty)
    )


def test_control_a_completed_exemption_is_reported_in_either_table(tmp_path: Path) -> None:
    """Control: an OVERSIZE or CONSOLE_ONLY entry that calls the setup is stale; one that does not is not."""
    done = f"from {_MANAGER} import {_CALL}\n{_CALL}()\n"
    _plant(tmp_path, {"a.py": done, "b.py": done, "c.py": "x = 1\n"})
    tables = {"OVERSIZE": {"a.py": "r", "c.py": "r"}, "CONSOLE_ONLY": {"b.py": "r"}}
    assert completed_exemptions(tmp_path, tables) == ["CONSOLE_ONLY: b.py", "OVERSIZE: a.py"]
    assert completed_exemptions(tmp_path, {"CONSOLE_ONLY": {"c.py": "r"}}) == []


def _plant(root: Path, files: dict[str, str]) -> list[str]:
    for path, body in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(body, encoding="utf-8")
    return sorted(files)


def test_control_a_launched_target_without_the_call_is_reported(tmp_path: Path) -> None:
    """Control: a synthetic launched target of every kind without the call fails; with it, passes."""
    imp = f"from {_MANAGER} import get_logger\n"
    demo = imp + "if __name__ == '__main__':\n    get_logger(__name__)\n"
    paths = _plant(
        tmp_path,
        {
            "svc/app.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "scripts/cli.py": demo,
            "svc/unit_target.py": "def main():\n    pass\n",
            "svc/compose_target.py": "def main():\n    pass\n",
            "svc/ops.py": "def main():\n    pass\n",
            "svc/ok.py": f"from {_MANAGER} import {_CALL}\napp = FastAPI()\n{_CALL}()\n",
            "svc/lazy.py": f"def main():\n    from {_MANAGER} import {_CALL}\n    {_CALL}()\napp = Celery('x')\nmain()\n",
            "svc/leaky.py": f"app = FastAPI()\n{_CALL}()\ndef helper():\n    from {_MANAGER} import {_CALL}\n",
            "svc/uncalled.py": f"from {_MANAGER} import {_CALL}\napp = FastAPI()\ndef unused():\n    {_CALL}()\n",
            "svc/handler.py": (
                f"from {_MANAGER} import {_CALL}\napp = Celery('x')\n"
                f"@signals.setup_logging.connect\ndef h(**kw):\n    {_CALL}()\n"
            ),
            "scripts/own_fn.py": imp + f"def {_CALL}():\n    pass\nif __name__ == '__main__':\n    {_CALL}()\n",
            "svc/x_test.py": demo,
        },
    )
    entries = entry_points(
        tmp_path,
        paths,
        {"svc/u.service": "svc/unit_target.py"},
        {"compose.yml::svc": "svc/compose_target.py"},
        frozenset({"svc/ops.py"}),
    )
    assert "svc/x_test.py" not in entries
    expected = [
        "scripts/cli.py",
        "scripts/own_fn.py",
        "svc/app.py",
        "svc/compose_target.py",
        "svc/leaky.py",
        "svc/ops.py",
        "svc/uncalled.py",
        "svc/unit_target.py",
    ]
    assert missing_call(tmp_path, entries, set()) == expected
    assert missing_call(tmp_path, entries, set(expected)) == []


def test_control_a_library_demo_main_is_not_in_the_population(tmp_path: Path) -> None:
    """Control: a ``__main__`` demo in a library module that nothing launches is outside the guard."""
    imp = f"from {_MANAGER} import get_logger\n"
    paths = _plant(tmp_path, {"lib/demo.py": imp + "if __name__ == '__main__':\n    get_logger(__name__)\n"})
    assert entry_points(tmp_path, paths, {}) == set()
    assert entry_points(tmp_path, paths, {}, {}, frozenset({"lib/demo.py"})) == {"lib/demo.py"}


def test_control_a_new_compose_service_without_the_call_is_reported(tmp_path: Path) -> None:
    """Control: an unmapped compose service is detected, and once mapped its target must call the function."""
    _plant(
        tmp_path,
        {
            "docker-compose.yml": "services:\n  web:\n    command: [python3, /app/web.py]\n  db:\n    command: [postgres]\n",
            "web.py": "def main():\n    pass\n",
        },
    )
    assert compose_python_services_in(tmp_path, ["docker-compose.yml"]) == {"docker-compose.yml::web"}
    entries = entry_points(tmp_path, [], {}, {"docker-compose.yml::web": "web.py"})
    assert missing_call(tmp_path, entries, set()) == ["web.py"]


def installs_paths_before_importing_shared(source: str, func: str, installer: str) -> bool:
    """In *func*, the call to *installer* precedes the first ``autobot_shared`` import.

    A function-level import of ``autobot_shared`` only resolves from a direct launch (``python3 script.py``,
    whose ``sys.path`` holds the script's directory, not the repo root) after the paths are installed.
    """
    fn = next(n for n in ast.walk(parse_cache.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == func)
    inner = _walk_no_defs(fn.body)
    imports = [
        n.lineno for n in inner if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("autobot_shared")
    ]
    installs = [
        n.lineno for n in inner if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == installer
    ]
    return bool(imports) and bool(installs) and min(installs) < min(imports)


def test_index_documentation_installs_import_paths_before_its_shared_import() -> None:
    source = (_ROOT / "tools/index_documentation.py").read_text(encoding="utf-8")
    assert installs_paths_before_importing_shared(source, "main", "_install_import_paths")


def test_control_an_import_before_the_path_install_is_caught() -> None:
    body = "def main():\n    {a}\n    {b}\n"
    late = body.format(a=f"from {_MANAGER} import {_CALL}", b="_install()")
    early = body.format(a="_install()", b=f"from {_MANAGER} import {_CALL}")
    assert not installs_paths_before_importing_shared(late, "main", "_install")
    assert installs_paths_before_importing_shared(early, "main", "_install")
    assert not installs_paths_before_importing_shared("def main():\n    pass\n", "main", "_install")


def test_control_an_unaliased_dotted_import_counts_and_a_near_miss_does_not() -> None:
    """Control: `import <manager>` + `<manager>.setup_logging()` is a startup call; importing it without the call,
    or calling the same name on another module, is not."""
    dotted = f"import {_MANAGER}\n{_MANAGER}.{_CALL}()\n"
    assert calls_setup_logging(ast.parse(dotted))
    assert calls_setup_logging(ast.parse(f"import {_MANAGER} as lm\nlm.{_CALL}()\n"))
    assert not calls_setup_logging(ast.parse(f"import {_MANAGER}\n"))
    assert not calls_setup_logging(ast.parse(f"import {_MANAGER}\nother.{_MANAGER}.{_CALL}()\n"))
    assert not calls_setup_logging(ast.parse(f"import os.path\n{_MANAGER}.{_CALL}()\n"))
