# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Container hardening kwargs are built once (#17267).

`autobot_shared/container_hardening.py` is the only place that may spell the Docker
hardening kwargs ``cap_drop`` / ``security_opt``. A client that writes either one as a
dict key, a subscript target or a keyword argument is building the constraint set
inline again. The detector reads the syntax tree, so prose naming them is not a copy.
"""

from __future__ import annotations

import ast
import functools

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.container_hardening import DENIED_RUN_KWARGS
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot_shared/container_hardening.py"
_KEYS = frozenset({"cap_drop", "security_opt"})

#: The two clients that create hardened containers must keep taking them from the builder.
_CONSUMERS = (
    "autobot-backend/secure_sandbox_executor.py",
    "autobot-backend/services/docker_task_workspace.py",
    "autobot-backend/services/execution/docker_backend.py",
    "autobot-backend/services/execution/container_pool.py",
)
_BUILDERS = frozenset({"hardening_kwargs", "baseline_hardening_kwargs", "execution_hardening_kwargs"})
#: Execution containers take the FULL builder (decision (b) on #17267), not just the privilege floor.
_EXECUTION_BUILDER = frozenset({"execution_hardening_kwargs"})
#: Every ``containers.run`` here must itself carry the execution builder output.
_RUN_SITES_FILE = "autobot-backend/services/execution/docker_backend.py"
_POOL_FILE = "autobot-backend/services/execution/container_pool.py"


def _is_key(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value in _KEYS


def builds_hardening_inline(source: str) -> bool:
    """True when `source` spells a hardening kwarg as a dict key, subscript target or keyword."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict) and any(_is_key(k) for k in node.keys):
            return True
        if isinstance(node, ast.keyword) and node.arg in _KEYS:
            return True
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) and _is_key(node.slice):
            return True
    return False


def _calls_builder(source: str) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _BUILDERS
        for n in ast.walk(ast.parse(source))
    )


_CREATING_METHODS = frozenset({"run", "create"})

#: Files whose run/create sites build their config elsewhere (a ``**cfg`` the builder produced);
#: each is separately pinned to call the builder (`_CONSUMERS`, `_POOL_FILE` test).
#: sandbox: containers.create at :373 and :576; workspace: containers.run at :415 and :429.
_ALLOWED_SITE_COUNTS = {
    "autobot-backend/secure_sandbox_executor.py": 2,
    "autobot-backend/services/docker_task_workspace.py": 2,
    _POOL_FILE: 1,
}
_ALLOWED_CFG_SITES = frozenset(_ALLOWED_SITE_COUNTS)


def _is_containers_run(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr in _CREATING_METHODS
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "containers"
    )


def _is_run_site(node: ast.AST) -> bool:
    """``x.containers.run(...)`` or ``to_thread(x.containers.run, ...)``."""
    if not isinstance(node, ast.Call):
        return False
    if _is_containers_run(node.func):
        return True
    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
    return name == "to_thread" and bool(node.args) and _is_containers_run(node.args[0])


def _spreads_builder(call: ast.Call, builders: frozenset[str] = _BUILDERS) -> bool:
    return any(
        kw.arg is None
        and isinstance(kw.value, ast.Call)
        and isinstance(kw.value.func, ast.Name)
        and kw.value.func.id in builders
        for kw in call.keywords
    )


def _names_denied_keyword(call: ast.Call) -> bool:
    """An explicit ``privileged=True``-style keyword defeats a builder spread in the same call."""
    return any(kw.arg in DENIED_RUN_KWARGS for kw in call.keywords)


def unhardened_run_sites(source: str, builders: frozenset[str] = _BUILDERS) -> list[int]:
    """Line numbers of ``containers.run``/``create`` calls without the builder spread, or that
    also pass a keyword in ``DENIED_RUN_KWARGS``."""
    return [
        n.lineno
        for n in ast.walk(ast.parse(source))
        if _is_run_site(n) and (not _spreads_builder(n, builders) or _names_denied_keyword(n))
    ]


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("dict literal", 'cfg = {"cap_drop": ["ALL"]}\n', True),
        ("security_opt key", 'cfg = {"image": "x", "security_opt": ["no-new-privileges"]}\n', True),
        ("subscript store", 'cfg["cap_drop"] = ["ALL"]\n', True),
        ("keyword argument", 'client.containers.run(image, cap_drop=["ALL"])\n', True),
        ("builder spread", "cfg = {**hardening_kwargs(network_mode='none', read_only=True)}\n", False),
        ("subscript read", 'x = cfg["cap_drop"]\n', False),
        ("comment naming it", '# "cap_drop": ["ALL"]\nx = 1\n', False),
        ("docstring naming it", '"""sets cap_drop=ALL"""\nx = 1\n', False),
    ],
)
def test_the_matcher_tells_an_inline_build_from_a_use(label: str, source: str, expected: bool) -> None:
    assert builds_hardening_inline(source) is expected, label


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("direct run, builder spread", "c.containers.run(i, **baseline_hardening_kwargs())\n", []),
        (
            "to_thread run, builder spread",
            "await to_thread(self.client.containers.run, i, **hardening_kwargs(a=1))\n",
            [],
        ),
        ("direct run, no hardening", "c.containers.run(i, detach=True)\n", [1]),
        ("to_thread run, no hardening", "await asyncio.to_thread(c.containers.run, i, detach=True)\n", [1]),
        ("literal keyword is not the builder", 'c.containers.run(i, cap_drop=["ALL"])\n', [1]),
        ("unrelated run", "proc.run(i)\n", []),
        ("hand-written network_mode, no builder", 'c.containers.run(i, network_mode="none")\n', [1]),
    ],
)
def test_the_run_site_matcher_tells_hardened_from_bare(label: str, source: str, expected: list[int]) -> None:
    assert unhardened_run_sites(source) == expected, label


def test_every_execution_backend_run_site_takes_the_builder() -> None:
    source = (repo_root() / _RUN_SITES_FILE).read_text(encoding="utf-8")
    sites = [n for n in ast.walk(ast.parse(source)) if _is_run_site(n)]
    assert len(sites) == 2, f"#17267: expected the cold-start and snapshot-restore run sites, found {len(sites)}"
    assert not unhardened_run_sites(source, _EXECUTION_BUILDER), (
        f"#17267: {_RUN_SITES_FILE} containers.run at lines {unhardened_run_sites(source, _EXECUTION_BUILDER)} "
        "does not take `**execution_hardening_kwargs(...)`."
    )


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("execution builder", "c.containers.run(i, **execution_hardening_kwargs())\n", []),
        ("floor only is not enough", "c.containers.run(i, **baseline_hardening_kwargs())\n", [1]),
        ("sandbox builder is not enough", "c.containers.run(i, **hardening_kwargs(a=1))\n", [1]),
        (
            "builder spread plus privileged",
            "c.containers.run(i, **execution_hardening_kwargs(), privileged=True)\n",
            [1],
        ),
        (
            "builder spread plus devices",
            "c.containers.create(i, devices=['/dev/x'], **execution_hardening_kwargs())\n",
            [1],
        ),
        ("dropping network_mode by hand", 'c.containers.run(i, network_mode="bridge")\n', [1]),
    ],
)
def test_the_execution_matcher_demands_the_full_builder(label: str, source: str, expected: list[int]) -> None:
    assert unhardened_run_sites(source, _EXECUTION_BUILDER) == expected, label


def unhardened_sites_outside_allowlist(sources: dict[str, str]) -> dict[str, list[int]]:
    """Per-file bare ``containers.run``/``create`` lines, skipping the declared cfg-building files."""
    found = {
        rel: unhardened_run_sites(text)
        for rel, text in sources.items()
        if rel not in _ALLOWED_CFG_SITES and "containers." in text
    }
    return {rel: lines for rel, lines in found.items() if lines}


def test_a_new_module_with_a_bare_run_or_create_is_caught() -> None:
    bare_run = "def f(client, img):\n    return client.containers.run(img)\n"
    bare_create = "def f(client):\n    return client.containers.create(image='x')\n"
    ok = "def f(c, i):\n    return c.containers.run(i, **execution_hardening_kwargs())\n"
    sources = {"new/a.py": bare_run, "new/b.py": bare_create, "new/c.py": ok, sorted(_ALLOWED_CFG_SITES)[0]: bare_run}
    assert unhardened_sites_outside_allowlist(sources) == {"new/a.py": [2], "new/b.py": [2]}


def test_every_run_and_create_site_in_the_tree_takes_the_builder_or_is_allowlisted() -> None:
    root = repo_root()
    sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in REACH.examined(root)}
    offenders = unhardened_sites_outside_allowlist(sources)
    assert not offenders, f"#17267: containers.run/create without the shared hardening builder: {offenders}"


def test_each_allowlisted_file_has_exactly_its_pinned_run_or_create_sites() -> None:
    root = repo_root()
    for rel, expected in _ALLOWED_SITE_COUNTS.items():
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        found = sum(1 for n in ast.walk(tree) if _is_run_site(n))
        assert found == expected, (
            f"#17267: {rel} has {found} containers.run/create sites, pinned at {expected}; a new site must "
            "take the builder directly or be reviewed into _ALLOWED_SITE_COUNTS"
        )


def test_the_warm_pool_run_kwargs_come_from_the_full_builder() -> None:
    source = (repo_root() / _POOL_FILE).read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_kwargs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_run_kwargs"]
    assert len(run_kwargs) == 1
    called = {c.func.id for c in ast.walk(run_kwargs[0]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert called & _EXECUTION_BUILDER, f"#17267: {_POOL_FILE}._run_kwargs does not call execution_hardening_kwargs"


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "container-hardening-inline",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=2580,
    what="non-test python source",
    roots=("autobot-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _inline_builders() -> tuple[str, ...]:
    root = repo_root()
    return tuple(
        rel
        for rel in REACH.examined(root)
        if rel != _CANONICAL and builds_hardening_inline((root / rel).read_text(encoding="utf-8"))
    )


def test_no_client_builds_hardening_kwargs_inline() -> None:
    assert not _inline_builders(), (
        f"#17267: {list(_inline_builders())} spell cap_drop/security_opt directly; "
        f"take them from `hardening_kwargs(...)` in {_CANONICAL}."
    )


@pytest.mark.parametrize("rel", _CONSUMERS)
def test_each_hardened_client_calls_the_builder(rel: str) -> None:
    assert _calls_builder(
        (repo_root() / rel).read_text(encoding="utf-8")
    ), f"#17267: {rel} no longer calls hardening_kwargs"


def test_the_canonical_module_does_build_them() -> None:
    assert builds_hardening_inline((repo_root() / _CANONICAL).read_text(encoding="utf-8"))


def test_ci_declares_the_docker_sdk_the_run_kwarg_pins_need() -> None:
    """The run-kwarg pins skip only where the docker SDK is absent; CI must always have it.

    ``autobot-backend/tests/test_execution_hardening_pin_17267.py`` checks every run site's
    kwargs against docker-py's accepted set. It skips in an interpreter without the SDK, so
    this asserts CI installs it, which keeps that skip from ever firing in CI.
    """
    text = (repo_root() / "requirements-ci" / "utilities.txt").read_text(encoding="utf-8")
    declared = [ln.split("#", 1)[0].strip() for ln in text.splitlines()]
    assert any(
        ln.lower().startswith("docker") and not ln.lower().startswith("docker-") for ln in declared if ln
    ), "requirements-ci/utilities.txt no longer declares the docker SDK; the #17267 run-kwarg pins would skip in CI"
