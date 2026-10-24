# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A guard that skips at import no longer ends the declaration sweep (#18808).

See repo_tests/_guard_import.py for the failure. The importer here is a fake, so the
cases are exact and need no real module that skips.
"""

from __future__ import annotations

import pytest
from repo_tests._guard_import import import_guards


def _importer(skips: dict[str, str], broken: set[str], seen: list[str]):
    def load(dotted: str) -> None:
        seen.append(dotted)
        if dotted in skips:
            pytest.skip(skips[dotted], allow_module_level=True)
        if dotted in broken:
            raise ImportError(f"no module named {dotted}")

    return load


def test_a_module_level_skip_does_not_end_the_sweep():
    seen: list[str] = []
    modules = [("a", "m.a"), ("b_skips", "m.b"), ("c", "m.c")]

    failures, skipped = import_guards(
        modules, declares=lambda key: False, importer=_importer({"m.b": "stubbed"}, set(), seen)
    )

    assert seen == ["m.a", "m.b", "m.c"], "every module after the skip must still be imported"
    assert failures == {}
    assert skipped == {"b_skips": "skipped at import: stubbed"}


def test_a_skipping_module_that_declares_is_a_failure_not_a_skip():
    """Its declaration is missing from the registry; that is the silence the sweep exists to name."""
    failures, skipped = import_guards(
        [("guard", "m.guard")], declares=lambda key: True, importer=_importer({"m.guard": "stubbed"}, set(), [])
    )

    assert failures == {"guard": "skipped at import: stubbed"} and skipped == {}


def test_an_import_error_is_recorded_and_the_sweep_continues():
    seen: list[str] = []
    failures, _ = import_guards(
        [("x", "m.x"), ("y", "m.y")], declares=lambda key: True, importer=_importer({}, {"m.x"}, seen)
    )

    assert seen == ["m.x", "m.y"]
    assert failures == {"x": "ImportError: no module named m.x"}
