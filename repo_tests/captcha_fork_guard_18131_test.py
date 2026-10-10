# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One CAPTCHA vocabulary (#18131).

`services/captcha_solver.py` and `agents/browser/captcha_solver.py` each carried a
`CaptchaType` and a result dataclass. The enums disagreed on which kinds exist, so a kind one
could classify was silently `UNKNOWN` to the other. The kinds, the confidence levels, the result
and the arithmetic evaluator now live once, in `services/captcha_types.py` and
`services/captcha_math.py`.

The detectors read the syntax tree and compare MEMBERS, not names (the discipline of
`severity_enum_fork_guard_18098_test.py`): a second enum that lists `recaptcha` and `hcaptcha`
is a second CAPTCHA-kind enum whatever it is called, and a class with `success` and
`captcha_type` fields is a second result type.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_TYPES = "autobot-backend/services/captcha_types.py"
_MATH = "autobot-backend/services/captcha_math.py"
_KIND_MARKERS = frozenset({"recaptcha", "hcaptcha"})
_MATH_REGEX_NAMES = frozenset({"MATH_EXPR_RE", "_MATH_EXPR_RE"})
#: The union of both former enums; `text_image` is recorded as TEXT, see `CaptchaType._missing_`.
_UNION = {"text", "math", "image_select", "slider", "recaptcha", "hcaptcha", "cloudflare", "unknown"}


def _class_values(node: ast.ClassDef) -> set[str]:
    """String constants assigned in the class body."""
    out: set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            out.add(stmt.value.value)
    return out


def _is_enum(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        if name.endswith("Enum"):
            return True
    return False


def _fields(node: ast.ClassDef) -> set[str]:
    return {s.target.id for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)}


def _defects(source: str) -> list[str]:
    """What in `source` defines a CAPTCHA kind enum, a solve-result type or a math pattern."""
    found: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if _is_enum(node) and _KIND_MARKERS <= _class_values(node):
                found.append(f"kind-enum:{node.name}")
            if {"success", "captcha_type"} <= _fields(node):
                found.append(f"result-type:{node.name}")
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & _MATH_REGEX_NAMES:
                found.append(f"math-pattern:{sorted(names & _MATH_REGEX_NAMES)[0]}")
    return found


_ENUM = 'class K(Enum):\n    A = "recaptcha"\n    B = "hcaptcha"\n    C = "x"\n'
_RESULT = "@dataclass\nclass R:\n    success: bool\n    captcha_type: object\n"


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a second kind enum under another name", _ENUM, ["kind-enum:K"]),
        ("a str-mixin enum", _ENUM.replace("(Enum)", "(str, enum.Enum)"), ["kind-enum:K"]),
        ("a second result type", _RESULT, ["result-type:R"]),
        ("a second math pattern", '_MATH_EXPR_RE = re.compile("x")\n', ["math-pattern:_MATH_EXPR_RE"]),
        ("an unrelated enum", 'class S(Enum):\n    A = "recaptcha"\n', []),
        ("a result without a kind", "class R:\n    success: bool\n    error: str\n", []),
        ("a comment naming them", '# class K(Enum): "recaptcha" "hcaptcha"\nx = 1\n', []),
    ],
)
def test_the_matcher_tells_a_fork_from_a_use(label: str, source: str, expected: list[str]) -> None:
    assert _defects(source) == expected, label


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("autobot-backend/services/captcha_solver.py", True),
        ("autobot-backend/services/captcha_solver_test.py", False),
        ("autobot-backend/tests/test_captcha.py", False),
        ("autobot-backend/services/captcha.md", False),
    ],
)
def test_the_test_path_filter_skips_tests_and_keeps_source(rel: str, expected: bool) -> None:
    assert _is_source_python(rel) is expected


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "captcha-vocabulary-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=2846,
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _defining_files() -> tuple[dict[str, list[str]], int]:
    """File -> defects for every non-test source file, and how many mention CAPTCHA kinds."""
    found: dict[str, list[str]] = {}
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "captcha_type" not in source and "recaptcha" not in source and "MATH_EXPR_RE" not in source:
            continue
        parsed += 1
        if defects := _defects(source):
            found[rel] = defects
    return found, parsed


def test_the_scan_is_not_vacuous() -> None:
    _, parsed = _defining_files()
    assert parsed >= 3, f"parsed {parsed} files mentioning CAPTCHA kinds"


def test_the_vocabulary_is_defined_in_exactly_two_files() -> None:
    found, _ = _defining_files()
    assert sorted(found) == [_MATH, _TYPES], (
        f"#18131: {found} define a CAPTCHA kind enum, a solve-result type or a math pattern. Import "
        f"`CaptchaType`/`CaptchaSolveResult` from services.captcha_types and "
        f"`solve_math_expression` from services.captcha_math; add a member there instead of a copy."
    )


def test_the_one_enum_carries_the_union() -> None:
    tree = ast.parse((repo_root() / _TYPES).read_text(encoding="utf-8"))
    enum = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "CaptchaType")
    assert _class_values(enum) == _UNION
