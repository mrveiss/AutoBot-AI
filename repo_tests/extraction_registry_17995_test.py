# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One guard for every registered extraction: no second definition or inline copy (#17995).

An extraction migrates N-1 call sites and the Nth survives, then misses every later fix
(#17982: the survivor kept substituting AutoBot's own tree after the canonical copy learned
to raise). The registry in ``extraction_registry.py`` names each concept and its canonical
site; this test fails when any other non-test module in the swept roots matches the
concept's detector.

Contrast pair per detector: a copy the detector must flag and a lookalike it must not,
so "no offenders" cannot mean "the detector matches nothing".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.extraction_registry import (
    GUARDED,
    GUARDED_ELSEWHERE,
    REGISTRY,
    inlines_egress_decision,
    inlines_source_root,
    inlines_wav_duration,
)

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, *_ROOTS) if _is_source_python(rel)]
    except EmptyEnumeration:
        return []


REACH = declare(
    "extraction-registry-sweep",
    discover=_source_population,
    # Mid-window, from REACH.window() = (2696, 2996, 2846) at the pin.
    floor=2846,
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


def _offenders() -> list[str]:
    root = repo_root()
    found: list[str] = []
    for rel in REACH.examined(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for entry in (e for e in REGISTRY if e.status == GUARDED):
            allowed = {entry.canonical, *(p for p, _ in entry.allowed)}
            if rel not in allowed and entry.detector(tree):
                found.append(f"{rel}: carries its own copy of '{entry.concept}' (canonical: {entry.canonical})")
    return found


def test_no_module_outside_the_canonical_site_carries_a_registered_concept() -> None:
    offenders = _offenders()
    assert not offenders, (
        f"{len(offenders)} private copy/copies of an extracted concept:\n  "
        + "\n  ".join(offenders)
        + "\n\nCall the canonical symbol instead (#17995)."
    )


def test_every_entry_is_well_formed_and_its_canonical_symbol_exists() -> None:
    root = repo_root()
    for e in REGISTRY:
        assert e.status in {GUARDED, GUARDED_ELSEWHERE, "deferred", "waiting"}, e.concept
        if e.status == GUARDED:
            assert e.detector is not None, f"{e.concept}: GUARDED needs a detector"
            leaf = e.symbol.rsplit(".", 1)[-1]
            names = {
                n.name
                for n in ast.walk(ast.parse((root / e.canonical).read_text(encoding="utf-8")))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            }
            assert leaf in names, f"{e.canonical} does not define {leaf}; the registry names a symbol that is gone"
        elif e.status == GUARDED_ELSEWHERE:
            assert (root / e.guard).is_file(), f"{e.concept}: named guard {e.guard} does not exist"
        else:
            assert e.reason, f"{e.concept}: a {e.status} entry must say why"
        for path, why in e.allowed:
            assert why and (root / path).is_file(), f"{e.concept}: allowance {path} needs a reason and must exist"


def test_the_registry_lists_the_six_instances_of_the_issue() -> None:
    cited = {i for e in REGISTRY for i in e.issues}
    assert {"#17982", "#17994", "#13615", "#13841", "#14901", "#17941"} <= cited


_SOURCE_ROOT_COPY = (
    "async def r(sid):\n    s = await get_source(sid)\n    if s and s.clone_path:\n        return Path(s.clone_path)\n"
)
_SOURCE_ROOT_LOOKALIKE = "async def r(sid):\n    s = await get_source(sid)\n    return s.clone_path\n"


@pytest.mark.parametrize(
    ("detector", "source", "expected"),
    [
        (inlines_source_root, _SOURCE_ROOT_COPY, True),
        (inlines_source_root, _SOURCE_ROOT_LOOKALIKE, False),
        (inlines_source_root, "def r(p):\n    return Path(p.clone_path)\n", False),
        (inlines_wav_duration, "def d(w):\n    return w.getnframes() / float(w.getframerate())\n", True),
        (inlines_wav_duration, "def d(w):\n    return w.readframes(w.getnframes())\n", False),
        (inlines_egress_decision, "async def s():\n    v = await egress_governor.evaluate(platform='x')\n", True),
        (inlines_egress_decision, "def s():\n    return {'error': 'egress_denied'}\n", True),
        (inlines_egress_decision, "async def s():\n    v = await egress_governor.gate(platform='x')\n", False),
    ],
)
def test_detector_contrast_pair(detector, source: str, expected: bool) -> None:
    assert detector(ast.parse(source)) is expected
