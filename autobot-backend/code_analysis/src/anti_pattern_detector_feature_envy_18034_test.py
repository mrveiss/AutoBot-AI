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
import importlib.util
import sys
from pathlib import Path

import pytest

# Loaded under a UNIQUE module name rather than `sys.path.insert` + a bare
# `import anti_pattern_detector`. That bare name is also used by
# `code_intelligence/anti_pattern_detector_test.py`, so claiming it here left
# the key in `sys.modules` for the rest of the session and the leak guard
# attributed it to that other file — a failure in a test this one never
# touches. The spec-based load registers `_feature_envy_subject_18034` instead,
# which nothing else imports.
_SPEC = importlib.util.spec_from_file_location(
    "_feature_envy_subject_18034", Path(__file__).parent / "anti_pattern_detector.py"
)
assert _SPEC and _SPEC.loader, "the detector module must be loadable from this directory"
_detector_module = importlib.util.module_from_spec(_SPEC)
# Registered only for the duration of exec_module -- dataclass and annotation
# machinery resolves `sys.modules[__name__]` while the module body runs -- then
# removed. Leaving it would be a module-scope sys.modules write with no
# restoration, which `sys_modules_module_scope_restoration_test` rejects, and
# rightly: the first version of this import claimed the BARE name and broke a
# different test. The module object stays alive through the reference below, so
# nothing here needs the registry afterwards.
sys.modules[_SPEC.name] = _detector_module
try:
    _SPEC.loader.exec_module(_detector_module)
finally:
    sys.modules.pop(_SPEC.name, None)

AntiPatternDetector = _detector_module.AntiPatternDetector
ClassInfo = _detector_module.ClassInfo


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


# ---------------------------------------------------------------------------
# Binding forms the first version of `_locally_bound` missed (CodeRabbit)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,id_",
    [
        pytest.param(
            "class Holder:\n"
            "    def use(self, Widget, /):\n"
            "        return (Widget.a, Widget.b, Widget.c, Widget.d)\n",
            "positional-only parameter",
        ),
        pytest.param(
            "class Holder:\n"
            "    def use(self):\n"
            "        Widget: object = make()\n"
            "        return (Widget.a, Widget.b, Widget.c, Widget.d)\n",
            "annotated assignment",
        ),
    ],
)
def test_a_locally_bound_name_is_never_an_envied_class(source: str, id_: str) -> None:
    """Both forms bind `Widget`, so it is a variable and not a class to move to.

    `posonlyargs` and `ast.AnnAssign` were both absent from the first version,
    so a method binding a name this way and reading it three times produced a
    false finding naming a real class it never touched.
    """
    info, method = _class_info("Holder", source)
    widget, _ = _class_info("Widget", "class Widget:\n    def x(self):\n        pass\n")
    detector = _detector_with({"m.Holder": info, "m.Widget": widget})
    assert detector._analyze_feature_envy(method, info) is None, f"{id_} should bind the name"


def test_a_subscript_index_is_a_read_not_a_binding() -> None:
    """The false-NEGATIVE direction, which matters as much as the other.

    `items[Widget] = value` only READS `Widget`. The first version walked the
    whole target with `ast.walk`, saw the Name, and marked it bound — which
    suppressed genuine findings elsewhere in the same method.
    """
    source = (
        "class Holder:\n"
        "    def use(self, items):\n"
        "        items[Widget] = 1\n"
        "        return (Widget.a, Widget.b, Widget.c, Widget.d)\n"
    )
    info, method = _class_info("Holder", source)
    widget, _ = _class_info("Widget", "class Widget:\n    def x(self):\n        pass\n")
    detector = _detector_with({"m.Holder": info, "m.Widget": widget})
    result = detector._analyze_feature_envy(method, info)
    assert result is not None, "a subscript index must not suppress a real finding"
    assert result[0] == "Widget"


def test_destructuring_binds_every_element() -> None:
    """Tuple and starred targets bind; the helper must recurse into them."""
    bound = _bound_names_for("(Widget, *rest), last = pair, tail")
    assert {"Widget", "rest", "last"} <= bound


def _bound_names_for(statement: str) -> set:
    """Parse one assignment and return what the detector thinks it binds."""
    assign = ast.parse(statement).body[0]
    names: set = set()
    for target in assign.targets:
        names |= _detector_module._bound_names(target)
    return names


def test_a_static_method_does_not_envy_its_own_class() -> None:
    """No `self` or `cls` to compare against, so the class name must count as own.

    Without this a `@staticmethod` reading `CurrentClass.a/.b/.c` was reported
    as envying the very class it is defined in (CodeRabbit).
    """
    source = (
        "class CurrentClass:\n"
        "    @staticmethod\n"
        "    def use():\n"
        "        return (CurrentClass.a, CurrentClass.b, CurrentClass.c, CurrentClass.d)\n"
    )
    info, method = _class_info("CurrentClass", source)
    detector = _detector_with({"m.CurrentClass": info})
    assert detector._analyze_feature_envy(method, info) is None
