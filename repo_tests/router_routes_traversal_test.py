# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Nothing may read ``.routes`` on a router that has children (#15093).

``fastapi>=0.139`` — ``requirements-ci/framework.txt`` pins ``0.141.1`` — changed
``include_router`` from *copy the child's routes onto me* to *record that I
include this child*. After the change a parent's ``routes`` list holds one opaque
wrapper per included child: its ``path`` is ``None``, it has no ``methods``, and
the real routes are one level down on ``wrapper.original_router.routes``.

The dangerous property is not that a naive walk raises. It is that the obvious
defensive spelling — ``getattr(route, "path", None)``, ``hasattr(route, "path")``
— does not raise. It finds **nothing**, and a test asserting over nothing passes.
CI job ``98088603289`` caught one: the assembled terminal router enumerated three
entries in CI where the same code enumerated twenty-six locally, because a
development checkout may resolve a FastAPI below the declared floor (#15091) and
still flatten eagerly. **A local pass carries no information about this.**

Four files had each worked this out privately, with four different partial
workarounds and no shared helper — the knowledge existed and did not spread.
``autobot_shared/api_routing/router_routes.py`` is now the one traversal; this is
the guard that stops a fifth private copy, and stops the first genuinely broken
site, which the sweep on #15093 established does not exist yet.

## What this catches

A read of ``<name>.routes`` — or ``getattr(<name>, "routes", ...)``, the same
read written so it cannot raise — where ``<name>`` resolves to an ``APIRouter``
that receives at least one ``include_router`` call. That is exactly the premise
that stopped being true at 0.139. The check is static AST, so it means the same
thing on both FastAPI shapes; a runtime guard would pass locally and fail in CI,
or worse, the reverse (#15091, and AC 7 on #15093 forbids depending on that box
being fixed).

## What this does NOT catch — stated, not implied

* **An attribute chain rooted in a local variable.** ``bridge.router.routes``
  (``services/mcp_bridge_workers/worker_entrypoint.py``) resolves no further than
  its literal text, because knowing what ``bridge`` is needs type inference.
  Those reads are counted as *unresolved* and reported by
  ``test_unresolved_routes_reads_stay_bounded`` so the blind spot cannot grow
  silently, but an unresolved read is not failed.
* **A router reached through a runtime factory** — anything whose target is
  computed rather than written.
* **``app.routes`` on a mounted application.** Deliberate: that is what
  ``api/self_capabilities.py`` and ``scripts/audit_api_wiring.py`` do, feeding it
  to ``get_openapi(routes=...)``, FastAPI's own supported view, which is correct
  on every version. It is why ``EXEMPT_READS`` below is empty — those two sidestep
  the router entirely rather than needing an exemption.
* **Whether the traversal is then done correctly.** This guard sees that a risky
  read exists, not that its result is used well. The helper's own contract is
  pinned by ``autobot_shared/api_routing/router_routes_test.py``, which asserts
  against a real ``APIRouter`` on whatever FastAPI is installed.
* **An include-time ``prefix=`` or ``dependencies=``.** Neither is recoverable
  from the deferred shape through any *public* route attribute -- that is why
  ``api/terminal_tools.py`` carries its gate on its own ``APIRouter(...)``
  constructor, where ``repo_tests/router_mount_parity_test.py`` can read it, and
  why ``api/terminal_websocket_route_test.py`` proves its gate behaviourally with
  a real request instead. (Correction, #15126: the prefix specifically is not
  gone -- fastapi 0.141.1's private ``_IncludedRouter.include_context.prefix``
  carries it -- only unreachable from the stable surface anything here should
  depend on; see ``mount_graph.py`` for the one place that says so.)
* **Whether a reconstructed path is correct.** This guard's premise is the
  deferred-shape *zero-routes* hazard -- a read that silently finds nothing. A
  read that resolves and finds real routes but drops an include-time prefix,
  producing a route that is wrong rather than absent, is a different defect
  (#15126) and outside what this guard checks for, resolved or not.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Set

import pytest

from autobot_shared.api_routing.mount_graph import MountGraph, RoutesRead, build_graph

_REPO = Path(__file__).resolve().parents[1]

#: Never walked: build output, vendored trees, virtualenvs, data.
_SKIP_ROOTS = frozenset({"__pycache__", "node_modules", ".venv", "venv", "data", "debug", "logs", "backups"})

_SKIP = frozenset({"__pycache__", "node_modules", ".venv", "venv", ".git", "site-packages"})


def scan_roots(repo: Path = _REPO) -> List[Path]:
    """Every top-level directory in the repo that could hold Python.

    Derived rather than listed. A hand-written list of trees is the same shape
    of mistake this guard exists to catch: it looks complete, it silently stops
    covering a tree that gets renamed or added, and nothing says so. Each
    top-level directory is also the namespace its router keys are prefixed with,
    which is what keeps ``autobot-backend/api/auth.py`` and
    ``autobot-slm-backend/api/auth.py`` from being read as one router.
    """
    return [
        child
        for child in sorted(repo.iterdir())
        if child.is_dir() and not child.name.startswith(".") and child.name not in _SKIP_ROOTS
    ]


# Modules allowed to read `.routes` on a router that has children, each with its
# reason. Keyed by module rather than by line so a reason cannot be silently
# re-pointed at a different read by an edit above it;
# `test_exemptions_are_named_and_still_real` fails when an entry stops naming a
# module that still contains such a read, so a stale one cannot rot into a hole
# nothing reports (the lifecycle `router_mount_parity_test.EXEMPT_ROUTERS`
# demonstrated when #15096 retired its only entry).
#
# The two "sidestepping" sites named on #15093 are deliberately absent:
# `api/self_capabilities.py` and `scripts/audit_api_wiring.py` read `app.routes`
# on a mounted application and hand it to `get_openapi(routes=...)`, FastAPI's
# own supported view. An app read is not a router read, so the scanner never
# proposes them and an entry for either would be stale on arrival.
EXEMPT_READS: Dict[str, str] = {
    "autobot_shared::api_routing.router_routes_test": (
        "The one place that must see the raw shape: it asserts what `include_router` "
        "leaves in `parent.routes` on the installed FastAPI, which is the fact the shared "
        "traversal is built on. Routing it through the traversal would make it assert the "
        "helper against itself."
    ),
}

#: A read must resolve to a router the graph knows before it can be judged. Well
#: below the 24 observed when this was written, so ordinary churn does not trip
#: it, but far enough above zero that a broken resolver cannot pass.
_MIN_RESOLVED_READS = 10

#: Unresolved reads are the documented blind spot. Bounding them means the spot
#: cannot quietly widen; 71 total reads were found when this was written.
_MAX_UNRESOLVED_SHARE = 0.75


@dataclass
class Scan:
    """Every ``.routes`` read under a tree, classified against its mount graph."""

    routers: Dict[str, object] = field(default_factory=dict)
    parents: Set[str] = field(default_factory=set)
    reads: List[RoutesRead] = field(default_factory=list)
    #: Bare keys defined in more than one tree, which is why keys are namespaced.
    shared_keys: Set[str] = field(default_factory=set)

    def deferred_risk(self) -> List[RoutesRead]:
        """Reads of a router that has children — the #15093 premise."""
        return [read for read in self.reads if read.target in self.parents]

    def resolved(self) -> List[RoutesRead]:
        return [read for read in self.reads if read.target in self.routers]

    def unresolved(self) -> List[RoutesRead]:
        return [read for read in self.reads if read.target is None]


def _bare(namespaced: Dict[str, object]) -> Set[str]:
    """The keys of *namespaced* with their tree prefix removed."""
    return {key.split("::", 1)[1] for key in namespaced}


def scan_tree(*roots: Path, skip: FrozenSet[str] = _SKIP) -> Scan:
    """Build each root's mount graph and collect every ``.routes`` read under it.

    One parse pass per file: ``build_graph`` already walks every module, and the
    reads ride along on the same ``ModuleScan``.

    Keys are prefixed with the tree they came from, and that is load-bearing:
    ``autobot-backend`` and ``autobot-slm-backend`` both define ``api/auth.py``,
    ``api/settings.py`` and seven more, so bare module keys collide and one
    backend's ``include_router`` calls would make the other backend's reads read
    as risky. ``test_key_namespacing_is_load_bearing`` pins that the collisions
    are real, so the prefix cannot be removed as redundant.

    The cost of the prefix is that a read in one tree of a router defined in
    another is not matched. No such read exists — ``repo_tests`` and ``scripts``
    cannot import a backend module, they are not on its path — and it is a false
    negative rather than a false positive if one ever appears.
    """
    scan = Scan()
    for root in roots:
        if not root.is_dir():
            continue
        graph: MountGraph = build_graph(root, skip=skip)
        namespace = root.name
        scan.shared_keys |= {
            key for key in graph.routers if f"{namespace}::{key}" not in scan.routers and key in _bare(scan.routers)
        }
        scan.routers.update({f"{namespace}::{key}": value for key, value in graph.routers.items()})
        scan.parents |= {f"{namespace}::{key}" for key in graph.routers_with_children()}
        scan.reads.extend(
            RoutesRead(
                site=f"{namespace}::{read.site}",
                expr=read.expr,
                target=None if read.target is None else f"{namespace}::{read.target}",
            )
            for read in graph.routes_reads
        )
    return scan


@pytest.fixture(scope="module")
def scan() -> Scan:
    return scan_tree(*scan_roots())


# --- non-vacuity ------------------------------------------------------------
#
# Every assertion below the fold is over an enumeration. #15087 is an open bug
# where exactly this went wrong: a router enumerated zero routes and the test
# reported success. An empty scan must be red here, never green.


def _module_of(read: RoutesRead) -> str:
    """``<tree>::<module>`` for a read, dropping the line number."""
    return read.site.rsplit(":", 1)[0]


def test_every_python_tree_is_scanned():
    """A tree dropped from the sweep is a hole, so name the ones that must be in it.

    ``scan_roots`` derives the list, but a skip entry or a rename could still
    remove a tree that matters while every other assertion here stayed green on
    the trees that remain.
    """
    names = {root.name for root in scan_roots()}
    required = {"autobot-backend", "autobot-slm-backend", "autobot_shared", "repo_tests", "scripts"}

    assert required <= names, f"trees missing from the sweep: {sorted(required - names)}"


def test_scan_resolved_real_routers(scan: Scan):
    resolved = scan.resolved()
    assert len(resolved) >= _MIN_RESOLVED_READS, (
        f"non-vacuity: only {len(resolved)} of {len(scan.reads)} `.routes` reads resolved to a "
        f"router the mount graph knows. Name resolution is broken and the guard below judges nothing."
    )


def test_scan_found_routers_with_children(scan: Scan):
    """The set the guard compares against must not be empty.

    ``llc.api:router`` is named explicitly: it is a package ``__init__`` that
    includes thirty-eight children, so it exercises import resolution, package
    naming and ``include_router`` detection at once. If it drops out, the guard
    still passes while having stopped looking at the largest parent in the repo.
    """
    assert len(scan.parents) >= 8, f"non-vacuity: only {len(scan.parents)} routers with children found"
    assert "autobot-backend::llc.api:router" in scan.parents, (
        "non-vacuity: llc.api:router (38 include_router calls) is not recognised as having children. "
        f"Found: {sorted(scan.parents)[:10]}"
    )


def test_unresolved_routes_reads_stay_bounded(scan: Scan):
    """The documented blind spot may not quietly become the common case."""
    unresolved, total = len(scan.unresolved()), len(scan.reads)
    assert total >= 20, f"non-vacuity: only {total} `.routes` reads found across {len(scan_roots())} trees"
    assert unresolved <= total * _MAX_UNRESOLVED_SHARE, (
        f"{unresolved} of {total} `.routes` reads could not be resolved to a router. "
        "Resolution has regressed; the guard is judging a shrinking slice of the repo."
    )


def test_key_namespacing_is_load_bearing(scan: Scan):
    """The per-tree prefix must not be dropped as redundant.

    ``autobot-backend`` and ``autobot-slm-backend`` both define ``api/auth.py``,
    ``api/settings.py``, ``api/monitoring.py`` and more, so bare module keys
    genuinely collide: without the prefix, one backend's ``include_router``
    calls would make the other backend's ``.routes`` reads report as risky —
    a false positive naming a router that is not the one being read.
    """
    assert scan.shared_keys, (
        "no router key is defined in two trees any more. Either the second backend stopped "
        "mirroring the first, or discovery stopped seeing one of them — check before removing "
        "the namespace prefix in scan_tree()."
    )


# --- the guard --------------------------------------------------------------


def test_no_site_reads_routes_on_a_router_with_children(scan: Scan):
    """The named assertion. Fails on a read whose premise 0.139 removed."""
    offenders = [read for read in scan.deferred_risk() if _module_of(read) not in EXEMPT_READS]
    if not offenders:
        return
    report = "\n".join(
        f"    {read.site}  reads {read.expr}.routes  -> {read.target}"
        for read in sorted(offenders, key=lambda r: r.site)
    )
    pytest.fail(
        "`.routes` read on a router that receives include_router calls (#15093).\n"
        "Under fastapi>=0.139 that list holds one opaque wrapper per included child, not the\n"
        "children's routes, so this read finds nothing and every assertion over it passes vacuously.\n"
        "Use autobot_shared.api_routing.router_routes.effective_routes(), or read a mounted app\n"
        "through fastapi.openapi.utils.get_openapi(routes=app.routes).\n" + report
    )


def test_exemptions_are_named_and_still_real(scan: Scan):
    """A stale exemption is a hole nothing reports, so it is an error."""
    proposed = {_module_of(read) for read in scan.deferred_risk()}
    assert proposed, (
        "non-vacuity: the scanner proposed no risky read at all, so every exemption below is "
        "unverifiable. Candidate detection has broken."
    )
    for module, reason in EXEMPT_READS.items():
        assert reason.strip(), f"exemption {module} has no reason"
        assert module in proposed, f"exemption {module} no longer reads a router with children — drop it"


# --- contrast mutation ------------------------------------------------------
#
# A guard nobody has watched fail is a guess. These build the bad pattern in a
# temp tree, assert it is reported, then remove *only* the `include_router` line
# and assert the byte-identical remainder is not. The first half proves detection;
# the second proves the guard is not simply flagging every `.routes` read, which
# would be an unusable guard that also happened to catch this.

_CHILD = """from fastapi import APIRouter

router = APIRouter()


@router.get("/leaf")
async def leaf():
    return {}
"""

_PARENT = """from fastapi import APIRouter

from .child import router as child_router

router = APIRouter()
{include}
"""

_READER = """from pkg.parent import router as parent_router


def walk():
    return [route.path for route in parent_router.routes]
"""


def _fixture_tree(root: Path, *, include: bool) -> Path:
    package = root / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "child.py").write_text(_CHILD, encoding="utf-8")
    (package / "parent.py").write_text(
        _PARENT.format(include="router.include_router(child_router)" if include else ""),
        encoding="utf-8",
    )
    (root / "reader.py").write_text(_READER, encoding="utf-8")
    return root


def test_the_bad_pattern_is_reported(tmp_path: Path):
    scanned = scan_tree(_fixture_tree(tmp_path / "bad", include=True))

    assert "bad::pkg.parent:router" in scanned.parents, "fixture parent was not seen to include a child"
    sites = {read.site for read in scanned.deferred_risk()}
    assert "bad::reader:5" in sites, f"the bad pattern was not reported; risky reads: {sites}"


def test_the_same_tree_without_the_include_is_not_reported(tmp_path: Path):
    """Byte-identical but for the ``include_router`` line, and it must pass.

    A decorator-only router's ``routes`` list is the same on every FastAPI, so
    reading it is correct. A guard that flagged this too would be noise, and
    noise gets suppressed rather than fixed.
    """
    scanned = scan_tree(_fixture_tree(tmp_path / "good", include=False))

    assert "good::pkg.parent:router" in scanned.routers, "fixture parent was not discovered at all"
    assert "good::pkg.parent:router" not in scanned.parents
    assert not scanned.deferred_risk(), f"a decorator-only router was flagged: {scanned.deferred_risk()}"
    reads = {read.site: read.target for read in scanned.reads}
    assert (
        reads.get("good::reader:5") == "good::pkg.parent:router"
    ), f"the read itself stopped being found, so the negative half proves nothing: {reads}"


def test_the_getattr_spelling_is_reported_too(tmp_path: Path):
    """``getattr(x, "routes", [])`` is the same read, made unable to raise.

    It is the worse spelling — it converts "I cannot see this router's children"
    into an empty list — so a guard blind to it would push code towards it.
    """
    root = _fixture_tree(tmp_path / "getattr", include=True)
    (root / "reader.py").write_text(
        "from pkg.parent import router as parent_router\n\n\n"
        'def walk():\n    return [r.path for r in getattr(parent_router, "routes", [])]\n',
        encoding="utf-8",
    )

    sites = {read.site for read in scan_tree(root).deferred_risk()}
    assert "getattr::reader:5" in sites, f"the getattr spelling was not reported; risky reads: {sites}"


def test_the_scanner_reads_the_helper_as_safe(tmp_path: Path):
    """Routing the same read through the shared helper clears the guard.

    A guard blind to the mechanism that fixes what it guards is not a guard: it
    would fail identically before and after the fix and teach nothing.
    """
    root = _fixture_tree(tmp_path / "helper", include=True)
    (root / "reader.py").write_text(
        "from autobot_shared.api_routing.router_routes import effective_routes\n"
        "from pkg.parent import router as parent_router\n\n\n"
        "def walk():\n    return [m.path for m in effective_routes(parent_router)]\n",
        encoding="utf-8",
    )

    assert not scan_tree(root).deferred_risk()


def test_the_fixture_source_is_what_the_scanner_thinks_it_is(tmp_path: Path):
    """Guards the fixture itself: a typo'd fixture proves nothing either way."""
    root = _fixture_tree(tmp_path / "shape", include=True)
    parent = ast.parse((root / "pkg" / "parent.py").read_text(encoding="utf-8"))
    calls = [
        n for n in ast.walk(parent) if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "include_router"
    ]

    assert len(calls) == 1, "the positive fixture must contain exactly one include_router call"
    assert (root / "reader.py").read_text(encoding="utf-8").count(".routes") == 1
