# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two anti-pattern classes are different capabilities, and call sites must match.

#12771. GH#6757 made ``code_analysis.src.anti_pattern_detector.AntiPatternDetector``
the canonical SSOT and repointed the ``code_intelligence.anti_pattern_detector``
facade at it. The package's own class -- a directory walk composing the four
category detectors, now ``AntiPatternSuiteAnalyzer`` -- kept the same name, so
which class a caller got depended on whether they imported the package or the
facade.

Two ``api/code_intelligence.py`` endpoints asked the facade-resolved canonical
detector for ``analyze_directory``, which it does not have, and one of them also
passed an ``exclude_dirs`` constructor argument it does not accept. Both raised
before reaching any analysis.

These checks are deliberately **static** (``ast`` over source files, no imports):
``code_intelligence``'s package ``__init__`` is stubbed in ``conftest.py`` for
annotation-compatibility reasons, so an import-based test here would assert
against a MagicMock and pass regardless.
"""

import ast
import pathlib

import pytest

CANONICAL = "autobot-backend/code_analysis/src/anti_pattern_detector.py"
SUITE = "autobot-backend/code_intelligence/anti_pattern_detection/analyzer.py"
PACKAGE_DIR = "autobot-backend/code_intelligence/anti_pattern_detection"
CALLER = "autobot-backend/api/code_intelligence.py"

_CLASS_SOURCE = {
    "AntiPatternDetector": CANONICAL,
    "AntiPatternSuiteAnalyzer": SUITE,
}


def _parse(path: str) -> ast.Module:
    source = pathlib.Path(path).read_text(encoding="utf-8")
    return ast.parse(source)


def _find_class(path: str, name: str) -> ast.ClassDef:
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    pytest.fail(f"{name} is not defined in {path}")


def _methods(path: str, name: str) -> set[str]:
    cls = _find_class(path, name)
    return {m.name for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _init_kwargs(path: str, name: str) -> set[str]:
    """Parameter names accepted by ``name``'s ``__init__``, ``self`` excluded."""
    cls = _find_class(path, name)
    for member in cls.body:
        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == "__init__":
            spec = member.args
            named = [a.arg for a in (*spec.posonlyargs, *spec.args, *spec.kwonlyargs)]
            if spec.kwarg is not None:
                return {"**"}  # accepts anything
            return {a for a in named if a != "self"}
    return set()


def test_analyze_directory_belongs_to_the_suite_analyzer_only():
    """The method whose absence broke two endpoints stays where it actually lives."""
    assert "analyze_directory" in _methods(SUITE, "AntiPatternSuiteAnalyzer")
    assert "analyze_directory" not in _methods(CANONICAL, "AntiPatternDetector"), (
        "The canonical detector gained analyze_directory. If that is deliberate, the two "
        "classes have converged and this fork should be consolidated rather than renamed."
    )


def test_the_canonical_name_is_not_redefined_in_the_package():
    """The fork stays retired: one name, one class."""
    offenders = []
    for path in sorted(pathlib.Path(PACKAGE_DIR).rglob("*.py")):
        for node in _parse(path.as_posix()).body:
            if isinstance(node, ast.ClassDef) and node.name == "AntiPatternDetector":
                offenders.append(f"{path.as_posix()}:{node.lineno}")
    assert not offenders, (
        "AntiPatternDetector is defined inside the anti_pattern_detection package again: "
        f"{offenders}. The canonical one is {CANONICAL} (GH#6757)."
    )


def _offload_calls(path: str):
    """Yield (class_name, method_name, kwarg_keys) for each run_isolated(...) call."""
    for node in ast.walk(_parse(path)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "run_isolated"):
            continue
        if len(node.args) < 3:
            continue
        cls_arg, init_arg, method_arg = node.args[0], node.args[1], node.args[2]
        cls_name = getattr(cls_arg, "id", None)
        method = method_arg.value if isinstance(method_arg, ast.Constant) else None
        if cls_name is None or not isinstance(method, str):
            continue
        keys = set()
        if isinstance(init_arg, ast.Dict):
            keys = {k.value for k in init_arg.keys if isinstance(k, ast.Constant)}
        yield cls_name, method, keys, node.lineno


@pytest.mark.parametrize("path", [CALLER])
def test_offloaded_anti_pattern_calls_match_their_class(path):
    """run_isolated dispatches getattr(cls(**kwargs), method) -- both must exist."""
    checked = 0
    for cls_name, method, keys, lineno in _offload_calls(path):
        source = _CLASS_SOURCE.get(cls_name)
        if source is None:
            continue  # a class this guard does not own
        checked += 1
        available = _methods(source, cls_name)
        assert method in available, (
            f"{path}:{lineno} offloads {cls_name}.{method}(), which {source} does not define. "
            f"analyze_directory lives on AntiPatternSuiteAnalyzer, not the canonical detector."
        )
        accepted = _init_kwargs(source, cls_name)
        if accepted != {"**"}:
            unknown = keys - accepted
            assert not unknown, (
                f"{path}:{lineno} constructs {cls_name} with {sorted(unknown)}, which its "
                f"__init__ does not accept (it takes {sorted(accepted)})."
            )
    assert checked, (
        f"No anti-pattern run_isolated call was checked in {path}. Either the call sites moved "
        "or this guard stopped matching them -- it must not pass by finding nothing."
    )
