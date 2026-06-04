# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
