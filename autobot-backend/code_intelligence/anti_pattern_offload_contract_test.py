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

**Why ``api/code_intelligence_offload_wiring_test.py`` did not catch it, and why
this is a second file rather than more cases in that one.** That module covers a
different failure mode (#12866: the offload conversion leaving the local scanner
un-run while the response summarises *through* it), and it works by patching
``run_isolated``. A patched ``run_isolated`` never executes the real
``getattr(cls(**init_kwargs), method_name)``, so no amount of added cases there
can reveal that the class named lacks the method -- the dispatch under test is
the mock. It is also marked ``pytestmark = pytest.mark.asyncio`` at module
level, which does not fit the synchronous checks below.

These checks are deliberately **static** (``ast`` over source files, no imports):
``code_intelligence``'s package ``__init__`` is stubbed in ``conftest.py`` for
annotation-compatibility reasons, so an import-based test here would assert
against a ``MagicMock`` and pass regardless.
"""

import ast
import pathlib

import pytest

#: Repository root, derived from this file rather than the process working
#: directory, so the checks run from either the root or ``autobot-backend``.
_REPO = pathlib.Path(__file__).resolve().parents[2]

CANONICAL = "autobot-backend/code_analysis/src/anti_pattern_detector.py"
SUITE = "autobot-backend/code_intelligence/anti_pattern_detection/analyzer.py"
PACKAGE_DIR = "autobot-backend/code_intelligence/anti_pattern_detection"
CALLER = "autobot-backend/api/code_intelligence.py"

#: The classes this guard owns. A ``run_isolated`` call naming anything else is
#: another scanner's business and is skipped.
_CLASS_SOURCE = {
    "AntiPatternDetector": CANONICAL,
    "AntiPatternSuiteAnalyzer": SUITE,
}

#: Both anti-pattern offload sites in CALLER. Pinned rather than merely non-zero
#: so that a call site silently disappearing fails too; update it deliberately
#: when a site is genuinely added or removed.
_EXPECTED_OFFLOAD_CALLS = 2


def _parse(rel_path: str) -> ast.Module:
    return ast.parse((_REPO / rel_path).read_text(encoding="utf-8"))


def _find_class(rel_path: str, name: str) -> ast.ClassDef:
    for node in ast.walk(_parse(rel_path)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    pytest.fail(f"{name} is not defined in {rel_path}")


def _methods(rel_path: str, name: str) -> set[str]:
    cls = _find_class(rel_path, name)
    return {m.name for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _init_kwargs(rel_path: str, name: str) -> set[str]:
    """Parameter names ``name.__init__`` accepts; ``{"**"}`` when it takes ``**kwargs``."""
    for member in _find_class(rel_path, name).body:
        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == "__init__":
            spec = member.args
            if spec.kwarg is not None:
                return {"**"}
            named = (*spec.posonlyargs, *spec.args, *spec.kwonlyargs)
            return {a.arg for a in named if a.arg != "self"}
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
    for path in sorted((_REPO / PACKAGE_DIR).rglob("*.py")):
        rel = path.relative_to(_REPO).as_posix()
        for node in _parse(rel).body:
            if isinstance(node, ast.ClassDef) and node.name == "AntiPatternDetector":
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "AntiPatternDetector is defined inside the anti_pattern_detection package again: "
        f"{offenders}. The canonical one is {CANONICAL} (GH#6757)."
    )


def _offload_calls(rel_path: str):
    """Yield (class_name, method_name, ctor_keys, lineno) per ``run_isolated`` call."""
    for node in ast.walk(_parse(rel_path)):
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


def _assert_call_matches_class(rel_path, cls_name, method, keys, lineno):
    source = _CLASS_SOURCE[cls_name]
    assert method in _methods(source, cls_name), (
        f"{rel_path}:{lineno} offloads {cls_name}.{method}(), which {source} does not define. "
        "analyze_directory lives on AntiPatternSuiteAnalyzer, not the canonical detector."
    )
    accepted = _init_kwargs(source, cls_name)
    if accepted == {"**"}:
        return
    unknown = keys - accepted
    assert not unknown, (
        f"{rel_path}:{lineno} constructs {cls_name} with {sorted(unknown)}, which its "
        f"__init__ does not accept (it takes {sorted(accepted)})."
    )


def test_offloaded_anti_pattern_calls_match_their_class():
    """run_isolated dispatches getattr(cls(**kwargs), method) -- both must exist."""
    checked = 0
    for cls_name, method, keys, lineno in _offload_calls(CALLER):
        if cls_name not in _CLASS_SOURCE:
            continue
        checked += 1
        _assert_call_matches_class(CALLER, cls_name, method, keys, lineno)
    assert checked == _EXPECTED_OFFLOAD_CALLS, (
        f"Expected {_EXPECTED_OFFLOAD_CALLS} anti-pattern run_isolated calls in {CALLER}, "
        f"checked {checked}. A site was added, removed, or reshaped so this guard stopped "
        "matching it -- it must not pass by finding nothing."
    )
