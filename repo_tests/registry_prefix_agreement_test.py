# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``api/registry.py`` must advertise the prefix the app actually mounts (#15120).

Two tables describe the same API surface and nothing held them together:

* ``autobot-backend/api/registry.py`` — ``RouterConfig(module_path=…, prefix=…)``,
  served to clients through the ``/api/registry/*`` endpoints.
* ``autobot-backend/initialization/router_registry/*.py`` — the tuples
  ``app_factory`` iterates, mounting each at ``f"/api{prefix}"``.

They had diverged in **ten** of thirty-one entries. Six advertised a prefix the
app does not serve (``/api/agent-config`` against the mounted
``/api/agent_config``, and five more); four named a module deleted by a
consolidation that never updated this table. ``api.service_monitor`` was the
worst of them: it advertised ``/api/monitoring``, which is real — it belongs to
``api.monitoring`` — so a reader following the registry landed on a live
namespace serving something else entirely.

Nothing routes with these values, which is exactly why they rotted unnoticed.
They are read by humans and by clients introspecting the surface, and #15114 /
#15116 / #15118 / #15119 are all instances of a client trusting a stale picture
of a route.

Static, not runtime
-------------------

Under ``fastapi>=0.139`` — which CI resolves — ``include_router`` defers, and an
include-time ``prefix=`` is not recoverable from the route objects afterwards
(#15093). A development checkout may resolve a lower FastAPI where it partly is
(#15091), so a runtime-introspection guard would mean one thing locally and
another in CI. Both sides are therefore read from source, through
``autobot_shared.api_routing.router_prefixes`` — the single grammar #12985
established, already relied on by the blocking ``api-wiring`` gate. No traversal
is written here.

Non-vacuity
-----------

Every assertion below is over an enumeration, and each enumeration is asserted
non-empty first. A resolver change that returns nothing must redden this file,
not silence it: an empty comparison reading as a clean comparison is the failure
mode that let ten entries drift in the first place.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set, Tuple

from autobot_shared.api_routing.router_prefixes import registry_entries, resolve_registry_targets

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"
_REGISTRY_FILE = _BACKEND / "api" / "registry.py"
_MOUNT_DIR = _BACKEND / "initialization" / "router_registry"

#: ``app_factory.py`` mounts every registry tuple at ``f"/api{prefix}"``; the
#: tuples carry the suffix only, while ``api/registry.py`` spells the whole
#: path. Applied here so both sides are compared in the same coordinates.
_APP_MOUNT_PREFIX = "/api"

#: Below this the comparison has stopped describing the registry and the
#: assertions no longer mean what they claim. The file holds 31 entries; the
#: floor is deliberately far under that so adding or retiring a router is not a
#: reason to edit this test, while a resolver returning a handful still fails.
_MIN_ENTRIES = 20


def _advertised_entries() -> Tuple[Tuple[str, str], ...]:
    """``(module_path, prefix)`` for every ``RouterConfig`` in ``api/registry.py``.

    Parsed rather than imported: importing the module pulls in the whole
    backend, and every value read here is a string literal in the source.
    """
    tree = ast.parse(_REGISTRY_FILE.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "RouterConfig"):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        module = _string_literal(kwargs.get("module_path"))
        prefix = _string_literal(kwargs.get("prefix"))
        if module is not None and prefix is not None:
            found.append((module, prefix.rstrip("/")))
    return tuple(found)


def _string_literal(node: ast.AST | None) -> str | None:
    """The value of a string-literal argument, or ``None`` if it is computed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _prefixes_by_file(entries) -> Dict[Path, Set[str]]:
    """Mount prefixes keyed by the file that serves them.

    Keyed by file, not by dotted module, so a package entry lines up with a
    mount of one of its submodules — ``api.user_management`` against the mounted
    ``api.user_management.router``. ``resolve_registry_targets`` performs that
    resolution for both sides identically, so the two stay comparable.
    """
    by_file: Dict[Path, Set[str]] = {}
    for entry in entries:
        for path, prefix in resolve_registry_targets(_BACKEND, [entry]).items():
            by_file.setdefault(path, set()).add(prefix)
    return by_file


def _mounted_entries() -> Tuple[Tuple[str, str], ...]:
    """``(module_path, served_prefix)`` for every tuple the app factory mounts."""
    return tuple((module, _APP_MOUNT_PREFIX + prefix) for module, prefix in registry_entries(_MOUNT_DIR))


def _module_is_importable(module_path: str) -> bool:
    target = _BACKEND.joinpath(*module_path.split("."))
    return target.with_suffix(".py").is_file() or (target / "__init__.py").is_file()


# --- non-vacuity: the enumerations the assertions below range over ----------


def test_the_advertised_table_is_read_and_is_not_empty():
    advertised = _advertised_entries()

    assert len(advertised) >= _MIN_ENTRIES, (
        f"only {len(advertised)} RouterConfig entries parsed out of {_REGISTRY_FILE.name}; "
        "the agreement assertions below would range over almost nothing"
    )


def test_the_mounted_table_is_read_and_is_not_empty():
    mounted = _mounted_entries()

    assert len(mounted) >= _MIN_ENTRIES, (
        f"only {len(mounted)} registry tuples parsed out of {_MOUNT_DIR.name}/; "
        "with no mounts to compare against, agreement is vacuously true"
    )


def test_the_comparison_actually_pairs_the_two_tables():
    """The intersection is what the agreement test ranges over.

    Both tables can be read in full and still share no key if the two
    resolutions disagree, and the agreement assertion would then pass having
    compared nothing at all.
    """
    advertised = _prefixes_by_file(_advertised_entries())
    mounted = _prefixes_by_file(_mounted_entries())

    paired = set(advertised) & set(mounted)

    assert len(paired) >= _MIN_ENTRIES, (
        f"only {len(paired)} files are named by both tables "
        f"({len(advertised)} advertised, {len(mounted)} mounted) — the two "
        "resolutions no longer line up, so agreement means nothing"
    )


# --- the agreement itself ---------------------------------------------------


def test_every_advertised_module_is_a_module_that_exists():
    """A registry entry naming a deleted module cannot be checked against anything.

    Four entries survived their module's consolidation (#1286, #1287) and would
    otherwise drop silently out of the comparison below.
    """
    advertised = _advertised_entries()
    assert advertised, "no RouterConfig entries parsed; nothing was checked"

    missing = sorted((module, prefix) for module, prefix in advertised if not _module_is_importable(module))

    assert not missing, "api/registry.py names modules that do not exist: " + ", ".join(
        f"{module} (advertised at {prefix!r})" for module, prefix in missing
    )


def test_every_advertised_prefix_is_the_prefix_the_app_mounts():
    """The defect itself: the advertised path must be the path served."""
    advertised = _prefixes_by_file(_advertised_entries())
    mounted = _prefixes_by_file(_mounted_entries())
    paired = sorted(set(advertised) & set(mounted))
    assert paired, "no advertised router resolved to a mounted file; nothing was compared"

    wrong = [
        (path, sorted(advertised[path]), sorted(mounted[path]))
        for path in paired
        if not (advertised[path] & mounted[path])
    ]

    assert not wrong, "api/registry.py advertises prefixes the app does not serve:\n" + "\n".join(
        f"  {path.relative_to(_BACKEND)}: advertised {adv} but mounted at {mnt}" for path, adv, mnt in wrong
    )


def test_every_advertised_router_is_one_the_app_factory_mounts():
    """An entry for a router nothing mounts advertises a path that 404s."""
    advertised = _prefixes_by_file(_advertised_entries())
    mounted = _prefixes_by_file(_mounted_entries())
    assert advertised, "no advertised router resolved to a file; nothing was checked"

    unmounted = sorted(set(advertised) - set(mounted))

    assert not unmounted, "api/registry.py advertises routers the app factory never mounts: " + ", ".join(
        f"{path.relative_to(_BACKEND)} (advertised at {sorted(advertised[path])})" for path in unmounted
    )
