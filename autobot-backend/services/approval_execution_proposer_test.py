# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every registered post-approval action has a production proposer (#17315).

The registry shipped holding one action -- ``orphan_storage_delete`` -- that
was registered, unit-tested, wired into a mounted router, and impossible to
reach: nothing in production created an approval naming it. Every existing
test passed, because each tested one end of a chain whose middle was missing.

This guard closes that shape rather than that instance. It finds the
production call sites of ``register_post_approval_action`` by reading the
tree, imports them so registration really happens, and then checks each
registered action against the module it declared as its proposer: the module
must import, must name the action, and must actually create an approval.

It fails loudly when it finds NO registration sites at all, instead of passing
with nothing to check -- a guard that cannot tell "nothing registered" from
"did not look" is the defect it exists to catch (MEASUREMENT_DISCIPLINE).
"""

import importlib
import pathlib

import pytest

from services.approval_execution import registered_action_proposers

_BACKEND = pathlib.Path(__file__).resolve().parent.parent
_REGISTER_CALL = "register_post_approval_action("
#: Where the function is DEFINED -- not a registration, so never a call site.
_DEFINITION = _BACKEND / "services" / "approval_execution.py"
_SKIP_DIRS = {"__pycache__", "node_modules", ".venv", "venv", ".git"}


def _is_test(path: pathlib.Path) -> bool:
    name = path.name
    return name.endswith("_test.py") or name.startswith("test_") or "tests" in path.parts


def _production_registration_sites() -> list[pathlib.Path]:
    sites = []
    for path in _BACKEND.rglob("*.py"):
        if _SKIP_DIRS & set(path.parts) or _is_test(path) or path == _DEFINITION:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _REGISTER_CALL in source:
            sites.append(path)
    return sites


def _module_name(path: pathlib.Path) -> str:
    return ".".join(path.relative_to(_BACKEND).with_suffix("").parts)


def _wiring_modules(site: pathlib.Path) -> list[pathlib.Path]:
    """Production modules that reference *site* -- the ones that trigger it.

    A registration site typically wraps its call in ``register()``, so
    importing the site alone registers nothing: something else must import it
    and call that. ``api/admin_orphan_storage.py`` is the live example, and it
    registers at the router's own import time precisely so the handler is in
    place before any approve() can reach it.
    """
    stem = site.stem
    wiring = []
    for path in _BACKEND.rglob("*.py"):
        if _SKIP_DIRS & set(path.parts) or _is_test(path) or path == site:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if stem in source and "register" in source:
            wiring.append(path)
    return wiring


@pytest.fixture(scope="module")
def registered() -> dict[str, str]:
    """Action -> declared proposer, after importing production's own wiring."""
    sites = _production_registration_sites()
    assert sites, (
        f"found no production call site of {_REGISTER_CALL!r} under {_BACKEND.name}/ -- "
        "this guard looked and found nothing, which is either a real regression "
        "(the registry is empty, so every approved action is a no-op) or a broken "
        "scan. Either way it is not a pass."
    )

    for site in sites:
        wiring = _wiring_modules(site)
        assert wiring, (
            f"{site.relative_to(_BACKEND)} registers a post-approval action, but no other "
            "production module imports it -- its register() never runs, so the handler is "
            "absent at runtime and every approval naming its action records a dispatch "
            "failure instead"
        )
        importlib.import_module(_module_name(site))
        for path in wiring:
            importlib.import_module(_module_name(path))

    proposers = registered_action_proposers()
    assert proposers, (
        f"{len(sites)} module(s) call {_REGISTER_CALL!r} and their wiring imported, but the "
        "registry is still empty -- registration is guarded by something this guard did not trigger"
    )
    return proposers


def test_the_known_action_is_registered_with_a_proposer(registered):
    """The instance that motivated the guard, pinned so it cannot regress."""
    assert registered.get("orphan_storage_delete") == "api.admin_orphan_storage"


def test_every_registered_action_declares_an_importable_proposer(registered):
    for action, proposed_by in registered.items():
        try:
            importlib.import_module(proposed_by)
        except ImportError as exc:  # pragma: no cover - the failure message is the point
            pytest.fail(f"action {action!r} declares proposer {proposed_by!r}, which does not import: {exc}")


def test_every_proposer_actually_names_its_action_and_creates_an_approval(registered):
    """The two things that make a proposer a proposer, checked on the module itself.

    Naming the action can be a literal or the imported constant, so the check
    is on the module's live attributes as well as its source -- a proposer that
    imports ``ACTION`` is as valid as one that spells the string out, and
    neither reads as absent.
    """
    for action, proposed_by in registered.items():
        module = importlib.import_module(proposed_by)
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")

        names_it = (
            f'"{action}"' in source
            or f"'{action}'" in source
            or any(value == action for value in vars(module).values() if isinstance(value, str))
        )
        assert names_it, (
            f"action {action!r} declares proposer {proposed_by!r}, but that module neither "
            "spells the action out nor holds it in a module attribute -- it cannot be the "
            "thing that creates approvals naming it"
        )
        assert "create_approval(" in source, (
            f"action {action!r} declares proposer {proposed_by!r}, but that module never calls "
            "create_approval() -- the action would stay unreachable in production, which is "
            "exactly the defect #17315 fixed"
        )
