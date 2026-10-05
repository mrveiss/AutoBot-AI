# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Feature envy must name a real class, or say nothing (#18034, #372).

The rule counted ANY name with an attribute access as an "envied class" and
excluded only the literal `self`. A sample of ten live findings was 10/10 false
positives: `cls` three times, the `np` module once, and five local variables.
The emitted advice was *"Consider moving method 'is_active' to class 'cls'"* --
not low-value, impossible to follow.

`cls` was wrong by construction. Inside a `@classmethod`, `cls.` is how you
touch your own class, so every well-written classmethod with three such
accesses was a finding and always would be.

These cases are the real ones from the owner's report, by file and symbol.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from anti_pattern_detector import AntiPatternDetector, ClassInfo  # noqa: E402


def _detector_with(classes: dict[str, ClassInfo]) -> AntiPatternDetector:
    detector = AntiPatternDetector.__new__(AntiPatternDetector)
    detector.classes = classes
    return detector


def _class_info(name: str, source: str) -> tuple[ClassInfo, ast.FunctionDef]:
    tree = ast.parse(source)
    cls_node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method = next(n for n in cls_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    info = ClassInfo(
        name=name,
        file_path=f"{name.lower()}.py",
        line_number=1,
        methods=[method],
        attributes=set(),
        base_classes=[],
        method_calls={},
        external_references=set(),
        lines_of_code=len(source.splitlines()),
        complexity=1,
    )
    return info, method


# Each case is a real finding from the live index, reduced to its shape.
_REAL_FALSE_POSITIVES = [
    pytest.param(
        "TaskStatus",
        "class TaskStatus:\n"
        "    @classmethod\n"
        "    def is_active(cls):\n"
        "        return cls.a or cls.b or cls.c or cls.d\n",
        id="cls in a classmethod (status_enums.py:59 — wrong by construction)",
    ),
    pytest.param(
        "NetworkConstants",
        "class NetworkConstants:\n"
        "    @classmethod\n"
        "    def get_host_configs(cls):\n"
        "        return [cls.a, cls.b, cls.c, cls.d, cls.e]\n",
        id="cls, 14 refs (network_constants.py:161)",
    ),
    pytest.param(
        "TestRAGQueryBenchmarks",
        "class TestRAGQueryBenchmarks:\n"
        "    def bench(self):\n"
        "        return np.dot(np.array(np.zeros(3)), np.ones(np.int64(2)))\n",
        id="np, a module (rag_benchmarks.py:76)",
    ),
    pytest.param(
        "PluginLoader",
        "class PluginLoader:\n"
        "    def load_plugin(self, path):\n"
        "        manifest = read(path)\n"
        "        return (manifest.a, manifest.b, manifest.c, manifest.d)\n",
        id="manifest, a local variable (plugin_sdk/loader.py:164)",
    ),
    pytest.param(
        "CircuitBreakerManager",
        "class CircuitBreakerManager:\n"
        "    def get_status(self):\n"
        "        for cb in self.all:\n"
        "            print(cb.a, cb.b, cb.c, cb.d)\n",
        id="cb, a loop variable (circuit_breaker.py:482)",
    ),
    pytest.param(
        "SlackNotificationIntegration",
        "class SlackNotificationIntegration:\n"
        "    def post_task_completion(self, params):\n"
        "        return (params.a, params.b, params.c, params.d)\n",
        id="params, a parameter (slack_integration.py:164)",
    ),
]


@pytest.mark.parametrize("cls_name,source", _REAL_FALSE_POSITIVES)
def test_an_unresolvable_name_produces_no_finding(cls_name: str, source: str) -> None:
    """Every one of these was reported as an envied CLASS before #18034."""
    info, method = _class_info(cls_name, source)
    detector = _detector_with({f"m.{cls_name}": info})

    assert detector._analyze_feature_envy(method, info) is None, (
        "reported a finding whose 'envied class' does not resolve to any class — "
        "the suggestion would name something that does not exist"
    )


def test_a_real_class_is_still_reported() -> None:
    """The guard must not silence the detector entirely.

    Without this, deleting the rule's body would pass every test above. The
    one plausible true positive in the owner's sample was `VisibilityLevel`,
    an enum that really is a class, so that is the shape asserted here.
    """
    source = (
        "class KnowledgeOwnership:\n"
        "    def share_fact(self, fact):\n"
        "        return (VisibilityLevel.a, VisibilityLevel.b, VisibilityLevel.c, VisibilityLevel.d)\n"
    )
    info, method = _class_info("KnowledgeOwnership", source)
    visibility, _ = _class_info("VisibilityLevel", "class VisibilityLevel:\n    def x(self):\n        pass\n")
    detector = _detector_with({"m.KnowledgeOwnership": info, "m.VisibilityLevel": visibility})

    result = detector._analyze_feature_envy(method, info)
    assert result is not None, "a genuine foreign-class reference must still be reported"
    envied, _self_refs, external_refs = result
    assert envied == "VisibilityLevel"
    assert external_refs >= 3


def test_locally_bound_collects_params_assignments_and_loop_targets() -> None:
    """The exclusion set itself, since it is what makes the cases above pass."""
    method = ast.parse(
        "def f(self, param, *args, **kwargs):\n"
        "    assigned = 1\n"
        "    for item in things:\n"
        "        pass\n"
        "    with open('x') as handle:\n"
        "        pass\n"
    ).body[0]
    bound = AntiPatternDetector._locally_bound(method)
    assert {"param", "args", "kwargs", "assigned", "item", "handle"} <= bound
    assert "things" not in bound, "a name only READ must not be treated as locally bound"
