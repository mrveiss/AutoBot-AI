# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: raw ``aiohttp.ClientSession(...)`` outside ``autobot-backend/`` (#12979).

**Scope, stated where the number is read** (``RATCHET_BASELINES.md`` rule 1).
This guard sweeps every tracked ``*.py`` file **except**:

* anything under ``autobot-backend/`` — already ratcheted by
  ``autobot-backend/tests/test_raw_client_session_ceiling_12992.py``, whose
  ceiling is a decreasing budget for a sweep still in progress. Two guards,
  disjoint trees, no file counted twice;
* tests, caches and archived copies, by the *same* rules the sibling applies —
  pinned by ``test_exclusion_rules_mirror_the_backend_sibling`` so the two
  scopes cannot drift apart and leave a tree neither one reads;
* the two sanctioned owners in ``EXEMPT``.

``test_the_two_scopes_cover_every_tracked_python_file`` asserts the union is
the whole tree, so neither boundary can be narrowed silently. A blind spot is
the absence of a line and gets no diff; this turns it into one.

**Why this guard exists when the sibling already does.** The sibling reads
``autobot-backend/`` only. Measured on ``origin/main`` at ``0a4cffced``, the
AST walker finds **59** constructions in **36** non-test files repo-wide, of
which **12** are inside ``autobot-backend/``. The other **47** — four fifths
of the population the issue is about — were under no ratchet at all. #12979's
own batches 4-9 drained and documented the backend tail; nothing was ever
watching the rest.

**What this PR converted.** 9 of those 47, in the two core plugins
(``video-generation-plugin/tools/providers.py`` 6,
``image-generation-plugin/tools/generate_image.py`` 3) — all plain
``async with aiohttp.ClientSession() as session:`` against module-constant
public hosts, with no connector, no TLS context and no lifetime beyond the
statement. They are now on ``get_http_client().tracked_request(...)``. That
leaves the **35** sites in **21** files recorded in ``INVENTORY`` below.

**What ``INVENTORY`` does and does not claim.** It claims those sites exist
and that each file's shape matches a declared category. It does **not** claim
each one is deliberate. #12979 remains open: the per-request sites in the
operator scripts are unconverted work, not carve-outs, and saying otherwise
here would be writing a justification nobody established. The categories
below describe *structure*, which is measurable; they do not describe intent,
which is not.

**The two-record hole (#17970), and what is done about it.** A ratchet whose
baseline and whose measurement are both edited in one commit passes every
check — the records move together and nothing enforces direction. A bare
count would have exactly that hole. What does not move with a baseline edit
is ``test_every_inventory_entry_satisfies_its_declared_category``: every entry
must satisfy a predicate evaluated against the **code**, not against the
inventory. A new per-request session in an ordinary library module — no
``__main__`` entrypoint, not a foreign runtime, not stored on an instance —
satisfies no category, so no number anyone writes here will make it pass. The
honest limit: a determined author could bolt an unused ``__main__`` block onto
a library module to buy the ``entrypoint`` category. That is a visible and
absurd diff, which is the most a guard in the same repository can achieve.

Refs #12979, #12992, #13625, #17970.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Iterator

import pytest
from repo_tests._paths import repo_root
from repo_tests._raw_aiohttp_session import Site, client_session_sites, scan_paths

from tools.lint._scan_helpers import tracked_paths

#: Owners allowed to construct a session: the pooled client itself, and the
#: SSRF guard, whose entire job is handing callers a session pinned to a
#: pre-resolved IP. Neither is a per-request construction.
EXEMPT = frozenset(
    {
        "autobot_shared/http_client_manager.py",
        "autobot_shared/security/ssrf_guard.py",
    }
)

#: The tree this guard does not read, because its sibling does.
SIBLING_TREE = "autobot-backend/"
SIBLING_GUARD = "autobot-backend/tests/test_raw_client_session_ceiling_12992.py"

#: Recorded sites, repo-relative path -> construction count. Measured with
#: ``repo_tests._raw_aiohttp_session`` against ``origin/main`` at
#: ``0a4cffced`` with this PR's 9 conversions applied. Lowering an entry (by
#: routing the call through ``get_http_client()``) is the only change that
#: needs no argument. Raising one, or adding a key, must also satisfy
#: ``CATEGORY`` below — the inventory alone cannot authorise it.
INVENTORY: dict[str, int] = {
    "autobot-infrastructure/shared/mcp/servers/prometheus-mcp/server.py": 3,
    "autobot-infrastructure/shared/scripts/analysis/npu_performance_measurement.py": 2,
    "autobot-infrastructure/shared/scripts/automated_testing_procedure.py": 1,
    "autobot-infrastructure/shared/scripts/comprehensive_log_aggregator.py": 1,
    "autobot-infrastructure/shared/scripts/monitoring_system.py": 2,
    "autobot-infrastructure/shared/scripts/phase_validation_system.py": 2,
    "autobot-infrastructure/shared/scripts/seq_log_forwarder.py": 2,
    "autobot-infrastructure/shared/scripts/startup_coordinator.py": 1,
    "autobot-infrastructure/shared/scripts/utilities/demo_workflow_system.py": 3,
    "autobot-infrastructure/shared/scripts/utilities/diagnose_backend_timeout.py": 2,
    "autobot-infrastructure/shared/scripts/validate-native-deployment.py": 2,
    "autobot-infrastructure/shared/scripts/zero_downtime_deploy.py": 2,
    "autobot-npu-worker/resources/windows-npu-worker/app/utils/backend_telemetry.py": 1,
    "autobot-npu-worker/resources/windows-npu-worker/app/utils/http_retry.py": 1,
    "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/agent.py": 1,
    "autobot-slm-backend/monitoring/performance_benchmark.py": 2,
    "autobot-slm-backend/monitoring/performance_monitor.py": 1,
    "autobot-slm-backend/scripts/remove_orphaned_node.py": 3,
    "autobot-slm-backend/slm/agent/agent.py": 1,
    "autobot_shared/paperclip_client.py": 1,
    "docs/examples/mcp_agent_workflows/base.py": 1,
}

#: Structural category claimed for each inventory entry. Four values, each
#: with a predicate below that reads the file rather than this table.
CATEGORY: dict[str, str] = {
    "autobot-npu-worker/resources/windows-npu-worker/app/utils/backend_telemetry.py": "foreign-runtime",
    "autobot-npu-worker/resources/windows-npu-worker/app/utils/http_retry.py": "foreign-runtime",
    "autobot_shared/paperclip_client.py": "long-lived",
    "docs/examples/mcp_agent_workflows/base.py": "docs-example",
}
CATEGORY.update({path: "entrypoint" for path in INVENTORY if path not in CATEGORY})

#: A separately packaged deployable: a Windows worker shipped as its own app
#: directory with its own requirements, which does not have ``autobot_shared``
#: on its path at runtime.
FOREIGN_RUNTIME_PREFIX = "autobot-npu-worker/resources/windows-npu-worker/"


def _tracked_python_files(root: Path) -> list[str]:
    """Every tracked ``*.py`` path, or fail — an empty list is not a clean tree."""
    # The one sanctioned enumeration (#15926): it scrubs the inherited GIT_DIR a
    # hook exports, anchors on cwd, and raises on an empty listing.
    paths = tracked_paths(root, "*.py")
    assert len(paths) > 3000, (
        f"tracked_paths returned {len(paths)} python paths from {root}; expected the whole tree. "
        "FIX THE ENUMERATION — a truncated listing reads exactly like a tree with no raw sessions."
    )
    return paths


def _is_test_or_archive(path: str) -> bool:
    """The sibling guard's exclusion rules, applied to a repo-relative path.

    Kept in this spelling (not the sibling's ``pathlib`` walk) because the
    population here comes from ``git ls-files`` rather than ``rglob``. The two
    rule *sets* are pinned equal by
    ``test_exclusion_rules_mirror_the_backend_sibling``; the traversal differs
    on purpose, so the second derivation shares no enumeration with the first
    (``RATCHET_BASELINES.md`` rule 3).
    """
    for part in path.split("/")[:-1]:
        if part in _sibling().EXCLUDED_DIR_NAMES or _sibling().EXCLUDED_DIR_SUBSTRING in part:
            return True
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


_SIBLING_MODULE = None


def _sibling():
    """The backend ceiling guard, loaded by path (its directory is hyphenated).

    Imported rather than restated so a change to its exclusion rules turns
    *this* guard red instead of silently opening a gap between the two scopes.
    """
    global _SIBLING_MODULE
    if _SIBLING_MODULE is None:
        spec = importlib.util.spec_from_file_location("raw_client_session_ceiling_sibling", repo_root() / SIBLING_GUARD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLING_MODULE = module
    return _SIBLING_MODULE


def scoped_paths() -> list[str]:
    """The population this guard reads: tracked, non-test, non-backend, non-exempt."""
    return [
        path
        for path in _tracked_python_files(repo_root())
        if not path.startswith(SIBLING_TREE) and not _is_test_or_archive(path) and path not in EXEMPT
    ]


def discovered() -> dict[str, int]:
    """Repo-relative path -> construction count, for every scoped file with any."""
    return {path: len(sites) for path, sites in scan_paths(repo_root(), scoped_paths()).items()}


# --- the instrument, before any count it produces is read -------------------


def test_the_detector_finds_a_known_construction() -> None:
    """A known positive, so a zero from the walk below means something.

    ``http_client_manager.py`` is exempt precisely *because* it constructs the
    shared session, which makes it the one file in this tree guaranteed to
    contain the thing being detected. A floor on the count would break the day
    the population is legitimately empty; a claim about the instrument holds at
    any size including zero.
    """
    control = repo_root() / "autobot_shared/http_client_manager.py"
    sites = client_session_sites(control.read_text(encoding="utf-8"))
    assert sites, "detector found no construction in the pooled client itself — every count below is meaningless"


def test_the_walk_reaches_the_tree_it_claims_to_scan() -> None:
    """The scope must be a real population, or the inventory check passes vacuously."""
    paths = scoped_paths()
    # Measured on origin/main at 0a4cffced: 6363 tracked *.py, 4394 under
    # autobot-backend/, 961 left in this scope once tests and archives are
    # dropped. The floor is well under that so ordinary churn does not trip
    # it, and far enough above zero that a collapsed walk cannot read clean.
    assert len(paths) > 800, f"scope collapsed to {len(paths)} files — fix the walk, not the inventory"
    assert "autobot_shared/paperclip_client.py" in paths, "scope did not reach autobot_shared/ — fix the walk"
    assert not any(p.startswith(SIBLING_TREE) for p in paths), "scope overlaps the sibling guard's tree"


# --- the substantive checks -------------------------------------------------


def test_no_raw_session_outside_the_recorded_inventory() -> None:
    """Sets, not totals: two populations can agree on a count and differ in membership."""
    found = discovered()
    added = sorted(set(found) - set(INVENTORY))
    removed = sorted(set(INVENTORY) - set(found))
    grew = sorted(p for p in set(found) & set(INVENTORY) if found[p] > INVENTORY[p])
    shrank = sorted(p for p in set(found) & set(INVENTORY) if found[p] < INVENTORY[p])

    assert not added and not grew, (
        "New raw aiohttp.ClientSession(...) construction(s) outside autobot-backend/ (#12979).\n"
        "Route the call through autobot_shared.http_client.get_http_client() — get_json()/post_json(), "
        "or tracked_request() when the response object itself must be inspected. A per-call session opens "
        "its own connector, bypasses the shared pool's sizing and active-request accounting, and leaks the "
        "connector when it is not closed.\n"
        f"  new files: {added}\n"
        f"  grown files: {[(p, INVENTORY[p], found[p]) for p in grew]}"
    )
    assert not removed and not shrank, (
        "Raw sessions were removed but INVENTORY still records them — lower the entries so the next "
        "author inherits the true baseline rather than slack.\n"
        f"  gone: {removed}\n"
        f"  lowered: {[(p, INVENTORY[p], found[p]) for p in shrank]}"
    )


def _module_has_main_guard(tree: ast.Module) -> bool:
    """True when the module has a top-level ``if __name__ == "__main__":``."""
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if _is_name_eq_main(node.test):
            return True
    return False


def _is_name_eq_main(test: ast.Compare) -> bool:
    """True only for ``__name__ == "__main__"`` -- not ``!=``, not another constant."""
    left = test.left
    if not (isinstance(left, ast.Name) and left.id == "__name__"):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    comparator = test.comparators[0]
    return isinstance(comparator, ast.Constant) and comparator.value == "__main__"


@pytest.mark.parametrize(
    "source,expected",
    [
        ('if __name__ == "__main__":\n    pass\n', True),
        ('if __name__ == "foo":\n    pass\n', False),
        ('if __name__ != "__main__":\n    pass\n', False),
        ('if __name__ in ("__main__",):\n    pass\n', False),
        ("if __name__ == other:\n    pass\n", False),
        ("x = 1\n", False),
    ],
)
def test_main_guard_requires_eq_and_the_main_constant(source: str, expected: bool) -> None:
    """Contrast fixtures: a lookalike comparison must not satisfy the ``entrypoint`` category."""
    assert _module_has_main_guard(ast.parse(source)) is expected


def _category_holds(path: str, category: str, source: str, sites: tuple[Site, ...]) -> bool:
    """Evaluate *category*'s predicate against the file's own code."""
    if category == "foreign-runtime":
        return path.startswith(FOREIGN_RUNTIME_PREFIX)
    if category == "docs-example":
        return path.startswith("docs/")
    if category == "long-lived":
        # Every site stores the session rather than consuming it inside one
        # ``async with`` — the shape the pooled client cannot express, since a
        # stored session outlives the request it was opened for.
        return bool(sites) and all(site.bound for site in sites)
    if category == "entrypoint":
        return _module_has_main_guard(ast.parse(source))
    return False


def _inventory_sources() -> Iterator[tuple[str, str, tuple[Site, ...]]]:
    root = repo_root()
    for path in sorted(INVENTORY):
        source = (root / path).read_text(encoding="utf-8")
        yield path, source, client_session_sites(source)


def test_every_inventory_entry_satisfies_its_declared_category() -> None:
    """The half a baseline edit cannot satisfy (#17970).

    Each entry names a structural category, and each category is a predicate
    over the file. An ordinary library module that opens a session per request
    matches none of them, so it cannot be admitted by writing a number here.
    """
    assert set(CATEGORY) == set(INVENTORY), "every inventory entry needs a category and vice versa"
    offenders = [
        (path, CATEGORY[path])
        for path, source, sites in _inventory_sources()
        if not _category_holds(path, CATEGORY[path], source, sites)
    ]
    assert not offenders, (
        "Inventory entries whose declared category is not true of the code:\n"
        + "\n".join(f"  {path}: claims {category}" for path, category in offenders)
        + "\nFix the code or convert the call — do not widen the category."
    )


def test_every_category_is_one_of_the_four_declared_values() -> None:
    """A closed enum: a fifth category is a decision, not an edit."""
    assert set(CATEGORY.values()) <= {"entrypoint", "foreign-runtime", "long-lived", "docs-example"}


# --- the boundary -----------------------------------------------------------


def test_exclusion_rules_mirror_the_backend_sibling() -> None:
    """The two guards must exclude the same things, or the union has a hole."""
    sibling = _sibling()
    assert sibling.EXCLUDED_DIR_NAMES == {"__pycache__", "tests", "test", ".pytest_cache", "node_modules"}
    assert sibling.EXCLUDED_DIR_SUBSTRING == "archive"


def test_the_two_scopes_partition_the_tracked_tree() -> None:
    """Every tracked ``.py`` lands in exactly one bucket, and none is empty.

    Phrasing this as "nothing is uncovered" would be a tautology — the
    leftover set is computed from the same predicate ``scoped_paths`` uses, so
    it is empty by construction and the test would consume nothing. The claim
    worth making is a *partition*: the four buckets are disjoint, they sum to
    the tracked population, and each is non-empty. A rename of
    ``autobot-backend/`` empties one and fails here; a widened exclusion moves
    files into the excluded bucket and fails the inventory check next door.
    """
    tracked = _tracked_python_files(repo_root())
    mine = set(scoped_paths())
    sibling = {p for p in tracked if p.startswith(SIBLING_TREE)}
    exempt = {p for p in tracked if p in EXEMPT}
    excluded = {p for p in tracked if p not in sibling and p not in exempt and _is_test_or_archive(p)}

    buckets = {"scoped": mine, "sibling": sibling, "exempt": exempt, "excluded": excluded}
    for name, bucket in buckets.items():
        assert bucket, f"bucket {name!r} is empty — the boundary moved and this guard now reads a different tree"
    assert len(mine) + len(sibling) + len(exempt) + len(excluded) == len(tracked), (
        "the four buckets do not partition the tracked tree: "
        f"{len(mine)} + {len(sibling)} + {len(exempt)} + {len(excluded)} != {len(tracked)}"
    )
    assert exempt == set(EXEMPT), f"an exempt owner is no longer tracked at its recorded path: {EXEMPT - exempt}"


def test_the_sibling_guard_still_exists_where_the_boundary_says_it_does() -> None:
    """The exclusion of ``autobot-backend/`` is justified only while it is guarded."""
    assert (repo_root() / SIBLING_GUARD).is_file(), (
        f"{SIBLING_GUARD} is gone — autobot-backend/ is excluded here on the strength of it. "
        "Either restore it or widen this guard's scope."
    )


if __name__ == "__main__":  # pragma: no cover - convenience for a local re-measure
    for _path, _count in sorted(discovered().items()):
        print(f'    "{_path}": {_count},')
    pytest.main([__file__, "-q"])
