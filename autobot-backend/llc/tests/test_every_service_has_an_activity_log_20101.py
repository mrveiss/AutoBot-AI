# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No Company OS service can run without an activity log (#20101).

``LLCServiceBase`` gave ``activity_log`` a default of ``None`` and each service guarded its write
with ``if self.activity_log``, so most audit records were never written and nothing said so. The
slot is now always populated, and this guard keeps it that way. It reads the source with ``ast``
(the shapes that put the silent skip back) and builds every service the way a route does, with
no log, to see that it has one.

What it cannot see: a service that is not an ``LLCServiceBase`` and not named below, and a
write that is simply never made (a mutating method with no ``record`` call at all). Those are a
coverage question, not a wiring one.

``EXEMPT`` names a file and the EXACT number of skips it may keep; once the file is fixed the
entry fails too and has to be deleted. The control cases at the bottom prove each detector can fail.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Iterator

import pytest

import llc.services as services_pkg
from llc.models.enums import ActivityEventType
from llc.services.activity_log import LLCActivityLogService
from llc.services.base import LLCServiceBase

LLC_ROOT = Path(__file__).resolve().parent.parent
SLOT_NAMES = {"activity_log", "_activity_log"}
MIN_SERVICES_EXPECTED = 30

EXEMPT: dict[str, tuple[int, str]] = {
    # file -> (allowed skips, why). Empty: the last one, liveness_monitor, now has a real log.
}

# Not an LLCServiceBase, but its own slot is filled with a real LLCActivityLogService when none is passed.
OWN_REAL_DEFAULT = {
    "services/controls_service.py": "takes the real log when none is passed",
    "scheduler/liveness_monitor.py": "takes the real log when none is passed (tested in test_liveness_monitor.py)",
}


def _is_slot(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr in SLOT_NAMES


def _tests_slot(test: ast.AST) -> bool:
    """True when a condition reads the slot itself: ``if self.activity_log``, ``not ...``, ``... is None``."""
    return any(_is_slot(n) for n in ast.walk(test))


def _skips(tree: ast.AST) -> list[int]:
    """Lines where code branches on whether the activity log is there, or assigns the slot outside the base."""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.Assert)) and _tests_slot(
            node.test if hasattr(node, "test") else node
        ):
            lines.append(node.lineno)
        elif isinstance(node, ast.BoolOp) and any(_is_slot(v) for v in node.values):
            lines.append(node.lineno)
    return sorted(set(lines))


def _slot_assignments(tree: ast.AST) -> list[int]:
    """Lines that assign ``self.activity_log`` — only ``LLCServiceBase.__init__`` may."""
    found = []
    for node in ast.walk(tree):
        targets = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        found += [node.lineno for t in targets if _is_slot(t) and getattr(t.value, "id", "") == "self"]
    return found


def _unknown_methods(tree: ast.AST) -> list[str]:
    """Calls like ``self.activity_log.log(...)`` to a method LLCActivityLogService does not have.

    Under the old ``if self.activity_log`` guard such a call never ran, so it never failed; with the
    log always present it raises ``AttributeError`` on every operation.
    """
    known = set(dir(LLCActivityLogService))
    return sorted(
        f"{node.func.attr}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and _is_slot(node.func.value)
        and node.func.attr not in known
    )


def _unknown_event_types(tree: ast.AST) -> list[str]:
    """``ActivityEventType.X`` names the enum does not have: an AttributeError the moment the write runs."""
    return sorted(
        f"{node.attr}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "ActivityEventType"
        and not hasattr(ActivityEventType, node.attr)
    )


def _sources() -> Iterator[tuple[str, ast.AST]]:
    for path in sorted(LLC_ROOT.rglob("*.py")):
        rel = path.relative_to(LLC_ROOT).as_posix()
        if rel.startswith(("tests/", "migrations/")) or path.name.endswith("_test.py") or path.name.startswith("test_"):
            continue
        yield rel, ast.parse(path.read_text(encoding="utf-8"))


def _all_services() -> list[type]:
    for info in pkgutil.walk_packages(services_pkg.__path__, "llc.services."):
        importlib.import_module(info.name)
    found, queue = [], [LLCServiceBase]
    while queue:
        for sub in queue.pop().__subclasses__():
            found.append(sub)
            queue.append(sub)
    return found


def _built_like_a_route(cls: type) -> object:
    """Construct *cls* with nothing for the log, and a stand-in for any other required argument."""
    required = [
        p.name
        for p in inspect.signature(cls.__init__).parameters.values()
        if p.name != "self" and p.default is p.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]
    return cls(**{name: object() for name in required})


def _without_a_log(cls: type) -> bool:
    return not isinstance(getattr(_built_like_a_route(cls), "activity_log", None), LLCActivityLogService)


def test_no_service_branches_on_whether_it_has_a_log():
    found = {}
    for rel, tree in _sources():
        lines = [n for n in _skips(tree) if rel != "services/activity_log.py"]
        if lines:
            found[rel] = lines
    allowed = {rel: count for rel, (count, _why) in EXEMPT.items()}
    over = {rel: v for rel, v in found.items() if len(v) != allowed.get(rel, 0)}
    stale = [rel for rel in allowed if rel not in found]
    assert not over, f"code that skips its audit write when the log is absent (file -> lines): {over}"
    assert not stale, f"EXEMPT entries for files with no skip left; delete them: {stale}"


def test_every_call_on_a_log_is_to_a_method_it_has():
    found = {rel: _unknown_methods(tree) for rel, tree in _sources() if _unknown_methods(tree)}
    assert not found, f"calls to a method LLCActivityLogService does not define (file -> method:line): {found}"


def test_every_event_type_a_service_names_exists():
    found = {rel: _unknown_event_types(tree) for rel, tree in _sources() if _unknown_event_types(tree)}
    assert not found, f"ActivityEventType members that do not exist (file -> name:line): {found}"


def test_only_the_base_assigns_the_slot():
    found = {rel: _slot_assignments(tree) for rel, tree in _sources() if _slot_assignments(tree)}
    found.pop("services/base.py", None)
    held = {rel: v for rel, v in found.items() if rel not in EXEMPT and rel not in OWN_REAL_DEFAULT}
    assert not held, f"a class sets its own activity log instead of taking the base's (file -> lines): {held}"


def test_every_service_is_built_with_a_real_log():
    services = _all_services()
    assert len(services) >= MIN_SERVICES_EXPECTED, f"found only {len(services)} services; the walk is broken"
    bare = [cls.__qualname__ for cls in services if _without_a_log(cls)]
    assert not bare, f"services built with no log have none: {bare}"


def test_the_service_that_bypasses_the_base_takes_the_same_default():
    from llc.services.template import TemplateService

    assert issubclass(TemplateService, LLCServiceBase)
    assert isinstance(_built_like_a_route(TemplateService).activity_log, LLCActivityLogService)


# --- controls: each detector must be able to fail ---------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "class S:\n    async def f(self):\n        if self.activity_log:\n            pass\n",
        "class S:\n    async def f(self):\n        if not self.activity_log:\n            return\n",
        "class S:\n    async def f(self):\n        if done and self.activity_log:\n            pass\n",
        "class S:\n    async def f(self):\n        x = 1 if self._activity_log is None else 2\n",
    ],
)
def test_control_the_skip_detector_flags_each_shape(source):
    assert _skips(ast.parse(source)), source


def test_control_the_skip_detector_passes_an_unconditional_write():
    assert not _skips(ast.parse("class S:\n    async def f(self):\n        await self.activity_log.flush()\n"))


def test_control_the_method_detector_flags_the_two_names_that_were_wrong():
    for name in ("log", "append"):
        assert _unknown_methods(ast.parse(f"async def f(self):\n    await self.activity_log.{name}(1)\n")), name
    assert not _unknown_methods(ast.parse("async def f(self):\n    await self.activity_log.query(1)\n"))


def test_control_the_event_type_detector_flags_a_name_the_enum_lacks():
    assert _unknown_event_types(ast.parse("x = ActivityEventType.NOT_A_REAL_EVENT\n"))
    assert not _unknown_event_types(ast.parse("x = ActivityEventType.TEMPLATE_PUBLISHED\n"))


def test_control_the_assignment_detector_flags_a_class_that_holds_its_own_slot():
    assert _slot_assignments(ast.parse("class S:\n    def __init__(self):\n        self.activity_log = None\n"))


def test_control_a_service_that_skips_the_base_init_is_reported_bare():
    class Skips(LLCServiceBase):
        def __init__(self) -> None:  # never calls super().__init__
            pass

    class Nones(LLCServiceBase):
        def __init__(self) -> None:
            self.activity_log = None

    assert _without_a_log(Skips) and _without_a_log(Nones)
    assert not _without_a_log(type("Plain", (LLCServiceBase,), {}))
