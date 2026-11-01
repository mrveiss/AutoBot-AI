# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""New code that nothing connects to fails CI; existing cases are frozen, and only shrink (#20512).

Built, merged, never wired: the chat frontend never called the approval resume route (#20401),
``file_cleanup_queue`` has no consumer (#20234), role credentials are attached and never used at
runtime, ``get_api_key_user`` is reachable only through a dependency no route uses. This guard
fails a change that adds the next one.

WHAT IT FAILS ON
----------------
Detected, compared with ``unconnected_code_baseline.txt`` (a key not in it fails):

``module:``  a backend module (autobot-backend, autobot-slm-backend, autobot_shared) that no
             production file imports, names as a dotted string, or launches. Population form of
             ``pipeline-scripts/check-new-module-callers.sh`` -- see ``_unconnected_modules``.
``route:``   a route decorator in the two backends that no frontend, production client or
             declared external prefix calls -- see ``_unconnected_routes``.
``queue:``   a Redis list or stream pushed and never read -- see ``_unconnected_stores``.
``table:``   a SQL table defined and never read or written -- see ``_unconnected_stores``.

``declared:`` entries are hand-recorded for what no detector can see; each is true only while its
stated set of referencing files is exactly the live one.

WHAT IT CANNOT SEE (each detector's module docstring has the full list)
------------------------------------------------------------------------
* Dead code that is *referenced*: A imported only by an unused B counts A as connected. A
  function nobody calls inside a module somebody imports is invisible. Only module, route, queue
  and table granularity exists; a new function in an old module is not seen.
* A caller that is itself dead, or that builds its path or key at runtime.
* Loading by directory scan (plugins, ``skills/builtin``, migrations): no textual reference.
* Redis keys held in a variable or another module's constant; non-list/stream Redis types.
* Anything outside the trees named in the detectors. Frontend, Ansible and shell code that is
  never called is not judged.

WHICH CI JOB
------------
``repo_tests`` run inside the ``python-shard`` matrix of ``.github/workflows/ci.yml`` (the shard
``repo_tests/stable_shard.py`` assigns this file), reported through the **required** context
``python-suite``, which re-asserts the matrix result. It also runs in pre-push, selected by the
``roots=`` below. Two gaps follow from that wiring: the matrix runs only when the ``changes`` job
sees a path in ``.github/filters/python-paths.yml``, so a frontend-only change that removes the
last caller of a route is not judged until the next Python change; and ``roots=`` cannot name the
frontends, so pre-push does not run this guard for a frontend-only edit either.

THE REMEDY IS WIRING, NEVER DELETION
------------------------------------
A key that fails is code somebody built. Connect it (import it, call the route from the UI or
declare its external caller, add the consumer) in the same change. The baseline never grows: if
the wiring genuinely cannot land with the code, split the code, do not add an entry. When an
entry's code is wired in, delete its line -- ``test_every_baseline_entry_is_still_unconnected``
fails until you do, which is what keeps the file shrinking.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pytest
from repo_tests import _unconnected_code as uc
from repo_tests import _unconnected_modules as modules
from repo_tests import _unconnected_routes as routes
from repo_tests import _unconnected_stores as stores
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_text
from repo_tests._reach import declare
from repo_tests._unconnected_common import Tree


@functools.lru_cache(maxsize=2)
def _state(root: Path) -> tuple[Tree, routes.Audit]:
    return Tree.of_repo(root), routes.Audit(root, scripts_root=repo_root())


def _module_files(root: Path) -> list[str]:
    return modules.candidates(_state(root)[0])


def _route_files(root: Path) -> list[str]:
    tree, audit = _state(root)
    return routes.route_files(tree, audit)


def _store_files(root: Path) -> list[str]:
    return stores.store_files(_state(root)[0])


MODULES_REACH = declare(
    "unconnected-code-modules",
    discover=_module_files,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=2747,
    what="non-test python modules of autobot-backend, autobot-slm-backend and autobot_shared that could have a caller",
    roots=modules.BACKEND_ROOTS,
    growth=300,
)
ROUTES_REACH = declare(
    "unconnected-code-routes",
    discover=_route_files,
    floor=404,
    what="non-test python files of autobot-backend and autobot-slm-backend that declare a route decorator",
    roots=routes.ROUTE_ROOTS,
    growth=40,
)
STORES_REACH = declare(
    "unconnected-code-stores",
    discover=_store_files,
    floor=79,
    what="non-test files of the backends, shared library and infrastructure that push to a Redis queue or define a table",
    roots=stores.STORE_ROOTS,
    growth=15,
)


@functools.lru_cache(maxsize=1)
def _live() -> frozenset[str]:
    root = repo_root()
    for reach in (MODULES_REACH, ROUTES_REACH, STORES_REACH):
        reach.examined(root)  # a sweep that reached implausibly little must not read as "nothing unconnected"
    tree, audit = _state(root)
    return frozenset(uc.detected(tree, audit))


def _baseline() -> dict[str, str]:
    return uc.parse_baseline((repo_root() / uc.BASELINE_REL).read_text(encoding="utf-8"))


def _detected_entries() -> dict[str, str]:
    return {k: v for k, v in _baseline().items() if not k.startswith("declared:")}


def _declared_entries() -> list[str]:
    return [k for k in _baseline() if k.startswith("declared:")]


def test_no_new_unconnected_code() -> None:
    new = sorted(_live() - set(_baseline()))
    assert not new, (
        f"#20512: {len(new)} backend module(s), route(s), queue(s) or table(s) have nothing connected to them:\n  "
        + "\n  ".join(new[:40])
        + "\nWire them in in this change: import the module from production code, call the route from the UI "
        "(or add its external caller to EXTERNAL_CALLER_PREFIXES with who calls it), or add the consumer of the "
        "queue or table. Do not delete the code, and do not add a baseline entry: the baseline only shrinks."
    )


def test_every_baseline_entry_is_still_unconnected() -> None:
    stale = sorted(set(_detected_entries()) - _live())
    assert not stale, (
        f"#20512: {len(stale)} baseline entr(ies) are no longer unconnected -- the code was wired in, or "
        "removed. Delete these lines from repo_tests/unconnected_code_baseline.txt (the baseline only "
        "shrinks):\n  " + "\n  ".join(stale[:40])
    )


def test_every_baseline_entry_links_its_wiring_issue() -> None:
    bad = {k: v for k, v in _baseline().items() if not (v.startswith("#") and v[1:].isdigit())}
    unknown = [k for k in _baseline() if k.split(":", 1)[0] not in uc.KINDS]
    assert not bad and not unknown, f"#20512: entries without a '#<issue>' link: {bad}; unknown kinds: {unknown}"


def test_declared_entries_describe_the_live_references() -> None:
    tree = _state(repo_root())[0]
    wrong = {}
    for entry in _declared_entries():
        defining, refs = uc.declared_state(tree, entry)
        if not defining or refs != uc.declared_allowed(entry):
            wrong[entry] = {"defined in": defining, "referenced from": refs}
    assert not wrong, (
        "#20512: a declared entry no longer matches the code. A new reference means the symbol may now be "
        "wired in (delete the entry if so); no definition means it was removed:\n" + repr(wrong)
    )


def test_the_baseline_only_shrinks_against_the_base() -> None:
    base = base_text(repo_root(), uc.BASELINE_REL)
    if base is None:
        return  # this file is new at the base: the baseline is being introduced, not raised
    added = sorted(set(_baseline()) - set(uc.parse_baseline(base)))
    assert not added, f"#20512: baseline entries were added against the base: {added}. Wire the code in instead."


def test_the_baseline_states_what_it_cannot_see() -> None:
    header = (repo_root() / uc.BASELINE_REL).read_text(encoding="utf-8").split("\n\n", 1)[0].lower()
    assert "cannot see" in header and "shrink" in header, "the baseline header must state its boundary (rule 1)"


# ---------------------------------------------------------------------------
# Controls: each detector fires on a planted case, and the connected twin of the same case is
# clean -- so an empty result is a measurement ("looked, found nothing"), not "looked at nothing".
# Everything that is not the subject sits outside the judged backend trees, or it would itself be
# an unconnected module.
# ---------------------------------------------------------------------------


def _plant(tmp_path: Path, files: dict[str, str]) -> tuple[Tree, routes.Audit]:
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    tree = Tree(list(files), lambda rel: (tmp_path / rel).read_text(encoding="utf-8"))
    return tree, routes.Audit(tmp_path, scripts_root=repo_root())


def _fired(tmp_path: Path, files: dict[str, str]) -> set[str]:
    tree, audit = _plant(tmp_path, files)
    return uc.detected(tree, audit)


_ROUTER = 'from fastapi import APIRouter\nrouter = APIRouter(prefix="/{prefix}")\n\n\n@router.{verb}("/{path}")\nasync def h():\n    return {{}}\n'
_MODULE = {"autobot-backend/pkg/planted.py": "VALUE = 1\n"}
_ROUTE = {"autobot-backend/api/planted_route.py": _ROUTER.format(prefix="planted", verb="get", path="orphan")}
_HOOK = {"autobot-backend/api/planted_hook.py": _ROUTER.format(prefix="webhooks", verb="post", path="planted")}
_QUEUE = {"autobot-backend/services/planted_queue.py": 'async def put(r, x):\n    await r.lpush("planted:work", x)\n'}
_TABLE = {"autobot-backend/database/schemas/planted.sql": "CREATE TABLE IF NOT EXISTS planted_jobs (id INTEGER);\n"}
#: Imports every planted module, so the subject under test is the route, queue or table and not its file.
_WIRED = {"scripts/wire.py": "import api.planted_route\nimport api.planted_hook\nimport services.planted_queue\n"}


@pytest.mark.parametrize(
    ("label", "files", "expected"),
    [
        ("module", _MODULE, "module:autobot-backend/pkg/planted.py"),
        ("route", {**_ROUTE, **_WIRED}, "route:autobot-backend/api/planted_route.py:GET /orphan"),
        ("queue", {**_QUEUE, **_WIRED}, "queue:autobot-backend/services/planted_queue.py:planted:work"),
        ("table", _TABLE, "table:planted_jobs"),
    ],
)
def test_a_planted_unconnected_case_fires(tmp_path: Path, label: str, files: dict[str, str], expected: str) -> None:
    assert _fired(tmp_path, files) == {expected}, label


@pytest.mark.parametrize(
    ("label", "files", "caller"),
    [
        ("module imported", _MODULE, {"scripts/use.py": "from pkg import planted\n"}),
        ("module imported relatively", _MODULE, {"autobot-backend/pkg/__init__.py": "from .planted import VALUE\n"}),
        ("module named by dotted string", _MODULE, {"scripts/use.py": 'load("pkg.planted")\n'}),
        ("module launched by a unit file", _MODULE, {"deploy/x.service": "ExecStart=python -m pkg.planted\n"}),
        (
            "module is a __main__ script",
            {"autobot-backend/pkg/planted.py": 'if __name__ == "__main__":\n    pass\n'},
            {},
        ),
        (
            "route called by the frontend",
            {**_ROUTE, **_WIRED},
            {"autobot-frontend/src/api.ts": "get('/api/planted/orphan')\n"},
        ),
        ("route called by a script", {**_ROUTE, **_WIRED}, {"scripts/probe.py": 'URL = "/api/planted/orphan"\n'}),
        ("route under a declared external prefix", {**_HOOK, **_WIRED}, {}),
        ("queue read by a consumer", {**_QUEUE, **_WIRED}, {"scripts/w.py": 'x = await r.brpop("planted:work")\n'}),
        ("table read by production code", _TABLE, {"scripts/j.py": 'q = "SELECT * FROM planted_jobs"\n'}),
    ],
)
def test_the_connected_twin_of_each_planted_case_is_clean(
    tmp_path: Path, label: str, files: dict[str, str], caller: dict[str, str]
) -> None:
    fired = _fired(tmp_path, {**files, **caller})
    # `_WIRED` imports the hook and route files whether or not a given case plants them.
    assert {k for k in fired if not k.startswith("module:")} == set(), label
    assert not {k for k in fired if k.startswith("module:autobot-backend/pkg")}, label


@pytest.mark.parametrize(
    ("label", "files", "decoy", "kind"),
    [
        (
            "a test importing the module",
            _MODULE,
            {"autobot-backend/pkg/planted_test.py": "from pkg import planted\n"},
            "module:",
        ),
        (
            "a test calling the route",
            {**_ROUTE, **_WIRED},
            {"autobot-frontend/src/api.test.ts": "get('/api/planted/orphan')\n"},
            "route:",
        ),
        (
            "the route's own file naming its path",
            {
                **_WIRED,
                "autobot-backend/api/planted_route.py": _ROUTE["autobot-backend/api/planted_route.py"]
                + 'DOC = "/api/planted/orphan"\n',
            },
            {},
            "route:",
        ),
        (
            "a test reading the queue",
            {**_QUEUE, **_WIRED},
            {"scripts/w_test.py": 'r.brpop("planted:work")\n'},
            "queue:",
        ),
        (
            "the schema's own trigger writing the table",
            _TABLE,
            {"autobot-backend/database/schemas/t.sql": "INSERT INTO planted_jobs VALUES (1);\n"},
            "table:",
        ),
    ],
)
def test_a_caller_that_does_not_count_leaves_the_case_unconnected(
    tmp_path: Path, label: str, files: dict[str, str], decoy: dict[str, str], kind: str
) -> None:
    assert any(k.startswith(kind) for k in _fired(tmp_path, {**files, **decoy})), label


def test_the_module_detector_finds_a_real_module_once_its_importers_are_removed() -> None:
    """Known positive on real files: `autobot_shared/paths.py` is connected; alone, it is not."""
    root, name = repo_root(), "autobot_shared.paths"
    tree = _state(root)[0]
    importer = next(
        rel
        for rel in tree.select(".py")
        if rel != "autobot_shared/paths.py" and name in modules.import_refs(rel, tree.text(rel))
    )
    real = {rel: tree.text(rel) for rel in ("autobot_shared/paths.py", importer)}
    assert "autobot_shared/paths.py" not in modules.unconnected(Tree.of_files(real))
    alone = {"autobot_shared/paths.py": real["autobot_shared/paths.py"]}
    assert modules.unconnected(Tree.of_files(alone)) == ["autobot_shared/paths.py"]
