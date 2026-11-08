# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the py-celery-private-event-loop rule (#20887).

Covers positive/negative/waiver fixtures, import aliases, the scope union, the
exact 3-module allowlist, and the blindness controls from MEASUREMENT_DISCIPLINE:
a census of task files derived independently of the rule, and a control that fails
if the population is empty.
"""

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache
from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_celery_private_event_loop as rule

REPO = repo_root()
FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_celery_private_event_loop"


def _check(path: Path, root: Path) -> list:
    ctx = Context(repo_root=root)
    tree = parse_cache.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return rule.check(path, tree, ctx)


def _fixture(name: str) -> list:
    return _check(FIXTURES / name, FIXTURES)


def test_positive_fixture_flags_every_spelling():
    lines = sorted(d.line for d in _fixture("positive.py"))
    assert len(lines) == 11, lines
    assert all(d.severity == "block" and d.rule_id == "py-celery-private-event-loop" for d in _fixture("positive.py"))


def test_negative_fixture_ignores_strings_comments_docstrings_and_worker_loop():
    assert _fixture("negative.py") == []


def test_waiver_is_honoured():
    assert _fixture("waiver.py") == []


def test_alias_table_resolves_module_and_from_import_aliases():
    tree = parse_cache.parse("import asyncio as aio\nfrom asyncio import run as r, new_event_loop\n")
    table = rule.alias_table(tree)
    assert (
        table["aio"] == "asyncio"
        and table["r"] == "asyncio.run"
        and table["new_event_loop"] == "asyncio.new_event_loop"
    )
    names = {n for _, n in rule.private_loop_calls(parse_cache.parse("import asyncio as aio\naio.run(x)\n"))}
    assert names == {"asyncio.run"}


def test_scope_dirs_apply_without_a_decorator(tmp_path):
    for sub in ("tasks", "workers", "llc/scheduler"):
        f = tmp_path / "autobot-backend" / sub / "m.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("import asyncio\n\ndef f(c):\n    return asyncio.run(c)\n", encoding="utf-8")
        assert len(_check(f, tmp_path)) == 1, sub


def test_a_task_defined_outside_the_scope_dirs_is_covered_by_its_decorator(tmp_path):
    f = tmp_path / "autobot-backend" / "elsewhere" / "m.py"
    f.parent.mkdir(parents=True)
    f.write_text(
        "import asyncio\nfrom celery_app import celery_app\n\n@celery_app.task\ndef f(c):\n    asyncio.run(c)\n",
        encoding="utf-8",
    )
    assert len(_check(f, tmp_path)) == 1


def test_a_plain_module_outside_scope_is_not_flagged(tmp_path):
    f = tmp_path / "autobot-backend" / "services" / "m.py"
    f.parent.mkdir(parents=True)
    f.write_text("import asyncio\n\ndef f(c):\n    return asyncio.run(c)\n", encoding="utf-8")
    assert _check(f, tmp_path) == []


def test_test_files_are_out_of_scope(tmp_path):
    f = tmp_path / "autobot-backend" / "tasks" / "x_test.py"
    f.parent.mkdir(parents=True)
    f.write_text("import asyncio\nasyncio.run(c)\n", encoding="utf-8")
    assert _check(f, tmp_path) == []


def test_allowlist_is_exactly_the_three_decided_modules():
    assert rule.ALLOWLIST == {
        "autobot-backend/services/pricing_refresh.py",
        "autobot-backend/services/provider_key_process_init.py",
        "autobot-backend/migrations/baseline.py",
    }
    for entry in rule.ALLOWLIST:
        assert (REPO / entry).is_file(), entry


def _allowlisted(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "autobot-backend" / "services" / "pricing_refresh.py"
    f.parent.mkdir(parents=True)
    f.write_text(body, encoding="utf-8")
    return f


def test_allowlisted_module_non_task_code_is_not_flagged(tmp_path):
    f = _allowlisted(
        tmp_path,
        "import asyncio\nfrom celery import shared_task\n\n@shared_task\ndef f(c):\n    return c\n\n"
        "def main(c):\n    asyncio.run(c)\n",
    )
    assert _check(f, tmp_path) == []


def test_allowlisted_module_task_body_is_still_flagged(tmp_path):
    f = _allowlisted(
        tmp_path,
        "import asyncio\nfrom celery import shared_task\n\n@shared_task\ndef f(c):\n    asyncio.run(c)\n\n"
        "def main(c):\n    asyncio.run(c)\n",
    )
    assert [d.line for d in _check(f, tmp_path)] == [6]


# --- census / blindness controls -------------------------------------------

_TASK_RE = re.compile(r"^\s*@(?:shared_task|celery_app\.task|app\.task)\b", re.M)


def _census() -> set[str]:
    """Task files found by regex + directory walk, independent of the rule's AST scope test."""
    found: set[str] = set()
    for base in ("autobot-backend", "autobot_shared"):
        for p in (REPO / base).rglob("*.py"):
            rel = p.relative_to(REPO).as_posix()
            if "/.worktrees/" in rel or rel.endswith("_test.py") or "/tests/" in rel or p.name.startswith("test_"):
                continue
            if rel.startswith(rule.SCOPE_DIRS) or _TASK_RE.search(p.read_text(encoding="utf-8")):
                found.add(rel)
    return found


def _rule_population(census: set[str]) -> set[str]:
    out = set()
    for rel in census:
        tree = parse_cache.parse((REPO / rel).read_text(encoding="utf-8"))
        if rule.in_scope(rel, tree):
            out.add(rel)
    return out


def test_census_population_is_not_empty():
    """Control: an empty population would make every other assertion here pass vacuously."""
    census = _census()
    assert len(census) >= 25, len(census)
    assert "autobot-backend/llc/scheduler/stalled_run_sweep.py" in census


def test_rule_population_covers_the_independent_census():
    census = _census()
    missed = census - _rule_population(census)
    assert not missed, f"task files the rule would not scan: {sorted(missed)}"


def test_rule_can_fail_on_a_known_bad_control_string():
    assert rule.private_loop_calls(parse_cache.parse("import asyncio\nasyncio.run(x)\n"))
    assert not rule.private_loop_calls(parse_cache.parse("x = 'asyncio.run(y)'\n"))


def test_repo_has_no_private_loops_in_scope():
    ctx = Context(repo_root=REPO)
    diags = []
    for rel in sorted(_census()):
        p = REPO / rel
        diags.extend(rule.check(p, ctx.parse(p), ctx))
    assert diags == []


# --- known false negative: loop creation in a helper a task imports -----------


def _module_file(name: str) -> Path | None:
    for root in (REPO / "autobot-backend", REPO):
        for cand in (root / (name.replace(".", "/") + ".py"), root / name.replace(".", "/") / "__init__.py"):
            if cand.is_file():
                return cand
    return None


def _module_level_imports(tree: ast.Module) -> set[str]:
    """Imports executed at import time (module body, not function bodies)."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names |= {f"{node.module}.{a.name}" for a in node.names}
    return names


def _closure(start: set[str]) -> set[str]:
    seen: set[str] = set()
    stack = list(start)
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        tree = parse_cache.parse((REPO / rel).read_text(encoding="utf-8"))
        for mod in _module_level_imports(tree):
            f = _module_file(mod)
            if f is not None:
                stack.append(f.relative_to(REPO).as_posix())
    return seen


# The canonical helpers: async_compat keeps the documented no-worker branch, worker_loop owns the one loop.
_HELPERS = frozenset({"autobot_shared/async_compat.py", "autobot_shared/worker_loop.py"})


def test_no_task_module_imports_a_helper_that_creates_a_private_loop():
    census = _census()
    reachable = _closure(_rule_population(census)) - {p for p in census}
    offenders = {}
    for rel in sorted(reachable):
        if rel in rule.ALLOWLIST or rel in _HELPERS or rel.endswith("_test.py"):
            continue
        calls = rule.private_loop_calls(parse_cache.parse((REPO / rel).read_text(encoding="utf-8")))
        names = [n for _, n in calls if not n.endswith("run_or_schedule")]  # run_or_schedule is worker-aware
        if names:
            offenders[rel] = names
    assert offenders == {}, offenders


def _calls(src: str) -> set[str]:
    return {n for _, n in rule.private_loop_calls(parse_cache.parse(src))}


def test_import_alias_in_one_function_does_not_leak_into_another():
    src = "def a():\n    import asyncio as aio\n    aio.run(x)\n\n" "def b():\n    aio.run(y)\n"
    found = [(c.lineno, n) for c, n in rule.private_loop_calls(parse_cache.parse(src))]
    assert found == [(3, "asyncio.run")]


def test_function_alias_shadows_module_alias_only_inside_that_function():
    src = "import asyncio as aio\n" "def a():\n    import json as aio\n    aio.run(x)\n\n" "def b():\n    aio.run(y)\n"
    found = [(c.lineno, n) for c, n in rule.private_loop_calls(parse_cache.parse(src))]
    assert found == [(7, "asyncio.run")]


def test_decorator_alias_from_import_is_resolved_as_a_task():
    src = "from celery import shared_task as task\n\n@task\ndef f():\n    pass\n"
    assert rule.is_task_module(parse_cache.parse(src))
    src = "import celery as c\n\n@c.shared_task(bind=True)\ndef f(self):\n    pass\n"
    assert rule.is_task_module(parse_cache.parse(src))


def test_unrelated_decorator_alias_is_not_a_task():
    src = "from functools import cache as task\n\n@task\ndef f():\n    pass\n"
    assert not rule.is_task_module(parse_cache.parse(src))


def test_decorator_alias_imported_inside_a_helper_function_is_a_task():
    src = "def helper():\n    from celery import shared_task as task\n\n    @task\n    def inner():\n        pass\n"
    assert rule.is_task_module(parse_cache.parse(src))


def test_decorator_alias_in_one_function_does_not_mark_a_sibling_as_a_task():
    src = (
        "def a():\n    from celery import shared_task as task\n\n    @task\n    def inner():\n        pass\n\n"
        "def b():\n    @task\n    def other():\n        pass\n"
    )
    names = [fn.name for fn in rule.task_functions(parse_cache.parse(src))]
    assert names == ["inner"]


def test_class_level_decorator_alias_is_a_task():
    src = "class K:\n    from celery import shared_task as task\n\n    @task\n    def f():\n        pass\n"
    assert rule.is_task_module(parse_cache.parse(src))


def test_class_level_import_is_seen_in_the_class_body_but_not_in_methods():
    src = "class K:\n    import asyncio as aio\n    X = aio.run(c)\n\n    def m(self):\n        aio.run(d)\n"
    found = [(c.lineno, n) for c, n in rule.private_loop_calls(parse_cache.parse(src))]
    assert found == [(3, "asyncio.run")]


def test_lambda_parameter_shadows_an_import_alias():
    src = "import asyncio as aio\nf = lambda aio: aio.run(1)\ng = lambda: aio.run(2)\n"
    found = [(c.lineno, n) for c, n in rule.private_loop_calls(parse_cache.parse(src))]
    assert found == [(3, "asyncio.run")]


def test_nested_function_inherits_enclosing_imports():
    src = (
        "def outer():\n    import asyncio as aio\n    from celery import shared_task as task\n\n"
        "    @task\n    def inner():\n        aio.run(x)\n"
    )
    tree = parse_cache.parse(src)
    assert rule.is_task_module(tree)
    assert [name for _, name in rule.private_loop_calls(tree)] == ["asyncio.run"]


def test_decorator_match_is_on_whole_components_not_a_suffix():
    src = "import webapp as router\n\n@router.task\ndef f():\n    pass\n"
    assert not rule.is_task_module(parse_cache.parse(src))


def test_deeply_nested_expression_does_not_overflow_the_stack():
    src = "x = " + "(" * 90 + "1" + ")" * 90 + "\nasyncio_value = " + "-" * 400 + "1\n"
    assert _calls(src) == set()


def test_global_declared_name_is_not_rebound_by_a_function_local_import():
    src = "import asyncio as aio\n\ndef f():\n    global aio\n    aio.run(x)\n    import json as aio\n"
    found = [(c.lineno, n) for c, n in rule.private_loop_calls(parse_cache.parse(src))]
    assert found == [(5, "asyncio.run")]


def test_global_declared_import_binds_in_the_function_and_at_module_scope():
    src = "def f():\n    global aio\n    import asyncio as aio\n    aio.run(x)\n\ndef g():\n    aio.run(y)\n"
    found = [(c.lineno, n) for c, n in rule.private_loop_calls(parse_cache.parse(src))]
    assert found == [(4, "asyncio.run"), (7, "asyncio.run")]


def test_global_rebind_to_another_target_is_a_known_limit():
    # Known limit (rule docstring): the module-level import wins; execution order is not modelled.
    src = "import json as aio\n\ndef f():\n    global aio\n    import asyncio as aio\n    aio.run(x)\n"
    assert rule.private_loop_calls(parse_cache.parse(src)) == []


def test_function_parameter_shadows_an_import_alias():
    src = "import asyncio as aio\n\ndef f(aio):\n    aio.run(1)\n\ndef g():\n    aio.run(2)\n"
    found = [(c.lineno, n) for c, n in rule.private_loop_calls(parse_cache.parse(src))]
    assert found == [(7, "asyncio.run")]
