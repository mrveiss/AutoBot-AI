# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the consolidation-opportunity detector (Issue #6684).

The new analyzer adds two AntiPatternType entries — DUPLICATE_ENUM and
DUPLICATE_CLASS_SHAPE — that catch *missing* inheritance: places where
two declarations should share a parent (or extracted base/Mixin) but
do not.  Sibling to #6661's *broken* inheritance detector.
"""

import importlib.util
import textwrap
from pathlib import Path

import pytest


def _load_detector_module():
    spec = importlib.util.spec_from_file_location(
        "apd_under_test",
        "autobot-backend/code_analysis/src/anti_pattern_detector.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"AntiPatternDetector dep chain unavailable: {exc}")
    # Pre-existing latent NameError on line 273 — see #6733.
    if not hasattr(mod, "config"):
        mod.config = None
    return mod


def _write_module(root: Path, name: str, body: str) -> Path:
    p = root / f"{name}.py"
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


@pytest.fixture
def fixture_root(tmp_path):
    return tmp_path


# ---------------------------------------------------------------------------
# DUPLICATE_ENUM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_enum_string_values_overlap(fixture_root):
    """Two enums with the same string values must be flagged."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "task_status",
        """
        from enum import Enum

        class TaskStatus(Enum):
            PENDING = "pending"
            RUNNING = "running"
            COMPLETED = "completed"
            FAILED = "failed"
        """,
    )
    _write_module(
        fixture_root,
        "step_status",
        """
        from enum import Enum

        class StepStatus(Enum):
            PENDING = "pending"
            RUNNING = "running"
            COMPLETED = "completed"
            FAILED = "failed"
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_enum = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_enum"]
    assert dup_enum, "expected DUPLICATE_ENUM finding for fully-overlapping enums"
    msg = dup_enum[0].description
    assert "TaskStatus" in msg or "StepStatus" in msg


@pytest.mark.asyncio
async def test_duplicate_enum_ignores_non_enum_classes(fixture_root):
    """Non-enum classes with similar attribute names must NOT be flagged."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "config",
        """
        class FirstConfig:
            PENDING = "pending"
            RUNNING = "running"
            COMPLETED = "completed"

        class SecondConfig:
            PENDING = "pending"
            RUNNING = "running"
            COMPLETED = "completed"
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_enum = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_enum"]
    assert not dup_enum, "non-enum classes should not be flagged as DUPLICATE_ENUM"


@pytest.mark.asyncio
async def test_duplicate_enum_skips_inheritance_relation(fixture_root):
    """Enum that extends another enum must NOT be flagged against its parent."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "extended_status",
        """
        from enum import Enum

        class CanonicalStatus(Enum):
            PENDING = "pending"
            RUNNING = "running"
            COMPLETED = "completed"

        class CanonicalStatusExtended(CanonicalStatus):
            CANCELLED = "cancelled"
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_enum = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_enum"]
    # Note: Python actually disallows inheriting from a non-empty enum, but
    # the AST stage doesn't care.  Detector must skip parent/child pairs.
    assert not dup_enum, "parent/child enum pairs should be skipped"


@pytest.mark.asyncio
async def test_duplicate_enum_below_threshold_not_flagged(fixture_root):
    """Two enums with only one shared value must NOT be flagged.

    Jaccard for 1 shared / 7 union = ~0.14 — well below either the
    historical 0.7 or the #6755 round 3 bumped threshold of 0.85.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "small_overlap",
        """
        from enum import Enum

        class ColorEnum(Enum):
            RED = "red"
            GREEN = "green"
            BLUE = "blue"
            ACTIVE = "active"

        class StateEnum(Enum):
            ACTIVE = "active"
            IDLE = "idle"
            STOPPED = "stopped"
            ERRORED = "errored"
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_enum = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_enum"]
    assert not dup_enum, "below-threshold overlap should not be flagged"


# ---------------------------------------------------------------------------
# DUPLICATE_CLASS_SHAPE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_class_shape_unrelated_classes_with_shared_methods(
    fixture_root,
):
    """Two classes with overlapping public method sets and no shared base must be flagged."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "alpha",
        """
        class AlphaClient:
            def connect(self): pass
            def disconnect(self): pass
            def send_message(self): pass
            def receive_message(self): pass
            def list_channels(self): pass
            def get_channel(self): pass
        """,
    )
    _write_module(
        fixture_root,
        "beta",
        """
        class BetaClient:
            def connect(self): pass
            def disconnect(self): pass
            def send_message(self): pass
            def receive_message(self): pass
            def list_channels(self): pass
            def get_channel(self): pass
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    assert dup_shape, "expected DUPLICATE_CLASS_SHAPE for two unrelated similar classes"


@pytest.mark.asyncio
async def test_duplicate_class_shape_skips_shared_base(fixture_root):
    """Subclasses of the same base sharing methods must NOT be flagged."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "integrations",
        """
        class BaseClient:
            pass

        class AlphaClient(BaseClient):
            def connect(self): pass
            def disconnect(self): pass
            def send_message(self): pass
            def receive_message(self): pass
            def list_channels(self): pass
            def get_channel(self): pass

        class BetaClient(BaseClient):
            def connect(self): pass
            def disconnect(self): pass
            def send_message(self): pass
            def receive_message(self): pass
            def list_channels(self): pass
            def get_channel(self): pass
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    assert not dup_shape, "shared base class makes this expected, not anti-pattern"


@pytest.mark.asyncio
async def test_duplicate_class_shape_skips_pydantic_models(fixture_root):
    """Pydantic models naturally share field names — must NOT be flagged."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "models",
        """
        class BaseModel:
            pass

        class UserResponse(BaseModel):
            id: int
            name: str
            email: str
            created_at: str
            updated_at: str
            status: str

        class AdminResponse(BaseModel):
            id: int
            name: str
            email: str
            created_at: str
            updated_at: str
            status: str
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    # Pydantic models are excluded by base-class name; even though these
    # don't have actual methods, they also don't trigger detection by design.
    assert not dup_shape


@pytest.mark.asyncio
async def test_duplicate_class_shape_small_identical_flagged(fixture_root):
    """#6780: small classes with IDENTICAL method sets (Jaccard=1.0) ARE flagged.

    The threshold was lowered from 5 → 2.  The guard for false positives is
    the strict-Jaccard rule: small classes need exact match, not just ≥0.7.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "tiny",
        """
        class TinyA:
            def f(self): pass
            def g(self): pass

        class TinyB:
            def f(self): pass
            def g(self): pass
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    assert dup_shape, "small classes with identical method sets should be flagged (#6780)"


@pytest.mark.asyncio
async def test_duplicate_class_shape_small_partial_overlap_skipped(fixture_root):
    """#6780: small classes with partial method overlap are NOT flagged.

    Below _SHAPE_MIN_METHODS_STRICT (5) the threshold is 1.0 (exact match).
    A class pair sharing 1 of 2 methods (Jaccard=0.33) must NOT produce a
    finding — this guards against FastAPI endpoint false positives.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "partial",
        """
        class EndpointA:
            def list(self): pass
            def create(self): pass

        class EndpointB:
            def list(self): pass
            def delete(self): pass
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    assert not dup_shape, "small classes with partial overlap should NOT be flagged (strict threshold)"


# ---------------------------------------------------------------------------
# #7501: parent-child inheritance + Protocol-impl false positives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_class_shape_skips_parent_child_inheritance(fixture_root):
    """#7501: ``Child(Parent)`` sharing method names is by construction
    (subclass overrides), not a duplicate-class smell.

    Real case: ``InMemoryEventStreamManager(EventStreamManager)`` from
    autobot-backend/events/stream_manager.py was flagged Jaccard 1.00.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "streamlib",
        """
        class EventStreamManager:
            async def publish(self, e): pass
            async def subscribe(self): pass
            async def get_latest(self): pass
            async def get_task_events(self): pass
            async def get_event(self): pass
            async def get_task_artifacts(self): pass
            async def close(self): pass

        class InMemoryEventStreamManager(EventStreamManager):
            async def publish(self, e): pass
            async def subscribe(self): pass
            async def get_latest(self): pass
            async def get_task_events(self): pass
            async def get_event(self): pass
            async def get_task_artifacts(self): pass
            async def close(self): pass
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    assert not dup_shape, "parent-child inheritance pair should NOT be flagged as duplicate"


@pytest.mark.asyncio
async def test_duplicate_class_shape_skips_protocol_impl_pair(fixture_root):
    """#7501: ``Protocol`` + structural impl is the canonical PEP 544
    pattern — must NOT be flagged.

    Real case: ``ITaskStorage`` Protocol vs ``TaskStorage`` impl from
    autobot-backend/memory/protocols.py + storage/task_storage.py.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "memlib",
        """
        from typing import Protocol

        class ITaskStorage(Protocol):
            async def log_task(self): pass
            async def update_task(self): pass
            async def get_task(self): pass
            async def get_task_history(self): pass
            async def get_stats(self): pass

        class TaskStorage:
            async def log_task(self): pass
            async def update_task(self): pass
            async def get_task(self): pass
            async def get_task_history(self): pass
            async def get_stats(self): pass
            async def initialize(self): pass
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    assert not dup_shape, "Protocol + structural impl pair should NOT be flagged as duplicate"


@pytest.mark.asyncio
async def test_duplicate_class_shape_still_flags_unrelated_classes_after_protocol_change(
    fixture_root,
):
    """#7501 regression guard: the parent-child + Protocol exclusions must
    NOT mask genuine unrelated-shape duplicates. Pair the broader detection
    case against the new exclusions to pin the positive path.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "unrelated",
        """
        class FooHandler:
            def parse(self): pass
            def validate(self): pass
            def transform(self): pass
            def emit(self): pass
            def reset(self): pass
            def status(self): pass

        class BarHandler:
            def parse(self): pass
            def validate(self): pass
            def transform(self): pass
            def emit(self): pass
            def reset(self): pass
            def status(self): pass
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    dup_shape = [ap for ap in report.anti_patterns if ap.pattern_type.value == "duplicate_class_shape"]
    assert dup_shape, "unrelated classes with identical shape should still be flagged"


# ---------------------------------------------------------------------------
# COMPOSABLE_OPPORTUNITY (#6748)
# ---------------------------------------------------------------------------

_LOADING_ERROR_VUE = """\
<script setup lang="ts">
import { ref } from 'vue'
const loading = ref(false)
const error = ref<string | null>(null)
</script>
<template><div>test</div></template>
"""

_DIFFERENT_PATTERN_VUE = """\
<script setup lang="ts">
import { ref, computed } from 'vue'
const count = ref(0)
const doubled = computed(() => count.value * 2)
</script>
<template><div>{{ doubled }}</div></template>
"""


def _make_vue_root(root: Path) -> Path:
    comp_dir = root / "autobot-frontend" / "src" / "components"
    comp_dir.mkdir(parents=True)
    return comp_dir


@pytest.mark.asyncio
async def test_composable_opportunity_loading_pattern(tmp_path):
    """6 components with the same loading+error ref boilerplate trigger COMPOSABLE_OPPORTUNITY."""
    apd = _load_detector_module()
    comp_dir = _make_vue_root(tmp_path)
    for i in range(6):
        (comp_dir / f"Widget{i}.vue").write_text(_LOADING_ERROR_VUE, encoding="utf-8")

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_composable_opportunities(str(tmp_path))

    composable = [f for f in findings if f.pattern_type.value == "composable_opportunity"]
    assert composable, "expected COMPOSABLE_OPPORTUNITY for 6 components sharing the same pattern"
    assert composable[0].metrics["component_count"] >= 5
    assert composable[0].entity_name == "useLoadingState"


@pytest.mark.asyncio
async def test_composable_opportunity_below_threshold(tmp_path):
    """4 components (below threshold of 5) must NOT produce a COMPOSABLE_OPPORTUNITY finding."""
    apd = _load_detector_module()
    comp_dir = _make_vue_root(tmp_path)
    for i in range(4):
        (comp_dir / f"Widget{i}.vue").write_text(_LOADING_ERROR_VUE, encoding="utf-8")

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_composable_opportunities(str(tmp_path))

    composable = [f for f in findings if f.pattern_type.value == "composable_opportunity"]
    assert not composable, "4 components should NOT trigger COMPOSABLE_OPPORTUNITY (below threshold of 5)"


@pytest.mark.asyncio
async def test_composable_opportunity_different_patterns_not_clustered(tmp_path):
    """Components with different reactive patterns are not clustered together."""
    apd = _load_detector_module()
    comp_dir = _make_vue_root(tmp_path)
    # 4 loading+error, 4 count+computed — neither group reaches threshold alone
    for i in range(4):
        (comp_dir / f"LoadWidget{i}.vue").write_text(_LOADING_ERROR_VUE, encoding="utf-8")
    for i in range(4):
        (comp_dir / f"CountWidget{i}.vue").write_text(_DIFFERENT_PATTERN_VUE, encoding="utf-8")

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_composable_opportunities(str(tmp_path))

    composable = [f for f in findings if f.pattern_type.value == "composable_opportunity"]
    assert not composable, "two distinct 4-component groups should not each trigger COMPOSABLE_OPPORTUNITY"


@pytest.mark.asyncio
async def test_composable_opportunity_excludes_composables_dir(tmp_path):
    """Files inside a 'composables' directory are excluded from detection."""
    apd = _load_detector_module()
    comp_dir = _make_vue_root(tmp_path)
    composable_dir = comp_dir / "composables"
    composable_dir.mkdir()
    # 6 files in composables/ plus 3 outside — only outside 3 count; below threshold
    for i in range(6):
        (composable_dir / f"use{i}.vue").write_text(_LOADING_ERROR_VUE, encoding="utf-8")
    for i in range(3):
        (comp_dir / f"Widget{i}.vue").write_text(_LOADING_ERROR_VUE, encoding="utf-8")

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_composable_opportunities(str(tmp_path))

    composable = [f for f in findings if f.pattern_type.value == "composable_opportunity"]
    assert not composable, "composables/ dir is excluded; only 3 real components remain — below threshold"


# ---------------------------------------------------------------------------
# #11171: frequency-weighted systemic ranking and systemic_patterns rollup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_frequency_weighted_ranking_outranks_single_high_severity(fixture_root):
    """A lower-severity pattern that appears many times outranks a single
    higher-severity one-off when freq × severity is larger (#11171).

    Scenario:
    - 1 GOD_CLASS (score=100, freq=1) → effective rank = 100
    - 5 LAZY_CLASS  (score=25,  freq=5) → effective rank = 125

    The 5 lazy-class findings must all appear before the god-class finding
    in report.anti_patterns (the stored sorted list).
    """
    apd = _load_detector_module()
    # God-class: one very large class with many methods (>20) and attributes (>15).
    methods = "\n".join(f"    def method_{i}(self): pass" for i in range(25))
    attrs = "\n".join(f"        self.attr_{i} = {i}" for i in range(20))
    god_body = f"""
class BigGodClass:
    def __init__(self):
{attrs}
{methods}
"""
    _write_module(fixture_root, "big_god", god_body)

    # Lazy-class: five tiny classes with only 1 public method and <20 LOC.
    for i in range(5):
        lazy_body = f"""
class TinyLazy{i}:
    def do_it(self): pass
"""
        _write_module(fixture_root, f"lazy_{i}", lazy_body)

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )

    god_indices = [i for i, ap in enumerate(report.anti_patterns) if ap.pattern_type.value == "god_class"]
    lazy_indices = [i for i, ap in enumerate(report.anti_patterns) if ap.pattern_type.value == "lazy_class"]

    assert god_indices, "expected at least one god_class finding"
    assert len(lazy_indices) >= 5, f"expected 5 lazy_class findings, got {len(lazy_indices)}"
    # The last lazy-class index must appear before (lower index = higher rank)
    # OR at the same position group as the god-class.
    # freq×score for lazy = 5×25=125 > 1×100=100 → lazy ranks first.
    assert max(lazy_indices) < min(god_indices), (
        f"lazy_class (freq×sev=125) should outrank god_class (freq×sev=100); "
        f"lazy indices={lazy_indices}, god index={god_indices}"
    )


@pytest.mark.asyncio
async def test_equal_frequency_orders_by_severity(fixture_root):
    """At equal frequency (both freq=1), the higher-severity finding ranks
    first — the secondary severity term in the sort key decides (#11171).
    """
    apd = _load_detector_module()
    # Two classes each appear once: one god-class (HIGH sev expected),
    # one lazy-class (LOW sev).  Both freq=1.
    # god_class effective rank = 1×100 = 100 (CRITICAL or HIGH)
    # lazy_class effective rank = 1×25  = 25
    # god_class must appear first even with freq=1.
    methods = "\n".join(f"    def method_{i}(self): pass" for i in range(22))
    attrs = "\n".join(f"        self.attr_{i} = {i}" for i in range(16))
    _write_module(
        fixture_root,
        "tie_god",
        f"""
class TieGod:
    def __init__(self):
{attrs}
{methods}
""",
    )
    _write_module(
        fixture_root,
        "tie_lazy",
        """
class TieLazy:
    def do_it(self): pass
""",
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )

    god_idx = next((i for i, ap in enumerate(report.anti_patterns) if ap.pattern_type.value == "god_class"), None)
    lazy_idx = next((i for i, ap in enumerate(report.anti_patterns) if ap.pattern_type.value == "lazy_class"), None)

    assert god_idx is not None, "god_class finding expected"
    assert lazy_idx is not None, "lazy_class finding expected"
    assert (
        god_idx < lazy_idx
    ), f"god_class (higher severity) must precede lazy_class; got god={god_idx}, lazy={lazy_idx}"


@pytest.mark.asyncio
async def test_systemic_patterns_rollup_contents(fixture_root):
    """systemic_patterns lists types with count >= 3, sorted by count desc (#11171)."""
    apd = _load_detector_module()
    # Create 4 lazy classes (count=4 >= threshold of 3) and 1 god class (count=1).
    for i in range(4):
        _write_module(
            fixture_root,
            f"sys_lazy_{i}",
            f"""
class SysLazy{i}:
    def do_it(self): pass
""",
        )
    methods = "\n".join(f"    def method_{i}(self): pass" for i in range(22))
    attrs = "\n".join(f"        self.attr_{i} = {i}" for i in range(16))
    _write_module(
        fixture_root,
        "sys_god",
        f"""
class SysGod:
    def __init__(self):
{attrs}
{methods}
""",
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )

    sp = report.systemic_patterns
    # lazy_class should appear in systemic_patterns (count=4 >= 3)
    lazy_entry = next((e for e in sp if e["pattern_type"] == "lazy_class"), None)
    assert lazy_entry is not None, "lazy_class (count=4) must appear in systemic_patterns"
    assert lazy_entry["count"] >= 4
    assert lazy_entry["top_severity_score"] == 25  # LOW score

    # god_class count=1 is below threshold — must NOT be in systemic_patterns
    god_entry = next((e for e in sp if e["pattern_type"] == "god_class"), None)
    assert god_entry is None, "god_class (count=1) must not appear in systemic_patterns (below threshold=3)"

    # systemic_patterns must be sorted by count desc
    counts = [e["count"] for e in sp]
    assert counts == sorted(counts, reverse=True), "systemic_patterns must be sorted by count desc"

    # to_dict() must include systemic_patterns key
    d = report.to_dict()
    assert "systemic_patterns" in d, "to_dict() must include systemic_patterns key"
    assert isinstance(d["systemic_patterns"], list)


@pytest.mark.asyncio
async def test_systemic_patterns_below_threshold_empty(fixture_root):
    """When no pattern_type reaches the threshold, systemic_patterns is empty (#11171)."""
    apd = _load_detector_module()
    # Two lazy classes — count=2 is below threshold=3
    for i in range(2):
        _write_module(
            fixture_root,
            f"below_{i}",
            f"""
class BelowLazy{i}:
    def do_it(self): pass
""",
        )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    assert report.systemic_patterns == [], f"count=2 is below threshold=3; expected [], got {report.systemic_patterns}"
