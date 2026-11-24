# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A 4xx never says "Internal server error" (#21943).

A not-found that tells the caller "server error" sends them to an on-call page instead of a typo. #21579 and #21587
replaced exception text with one generic string and stamped it on 4xx raises too. A refusal answers from
`autobot_shared.http_refusal` (`fixed_refusal` / `http_refusal`), whose `REFUSAL_TEXT` is the one status to message
table; a route that has a specific fixed message keeps it. A 5xx may still say "Internal server error".

The scan is AST, not grep: it catches a raise spread over several lines, `status.HTTP_4xx_...` and positional
arguments, and any call (a response builder, a raise helper) given a 4xx status and the generic string together.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.http_refusal import REFUSAL_TEXT
from tools.lint import _parse_cache as parse_cache

_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_GENERIC = "internal server error"
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
_STATUS_NAME = re.compile(r"HTTP_(\d{3})_")
_RAISE_HELPER = re.compile(
    r"raise_(bad_request|invalid_input|unauthorized|forbidden|not_found|conflict|unprocessable\w*)"
)
_RAISE_HELPER_CODE = {
    "bad_request": 400,
    "invalid_input": 400,
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "conflict": 409,
}


def _modules(root: Path) -> list[Path]:
    found: list[Path] = []
    for top in _ROOTS:
        base = root / top
        if base.is_dir():
            found += [p for p in sorted(base.rglob("*.py")) if not _TEST.search(p.relative_to(root).as_posix())]
    return found


#: Measured 3775 non-test modules in the three roots (2026-11-21); growth 300 puts the pin mid-window (3775 - 150).
REACH = declare(
    "client-error-detail-sweep-21943",
    discover=_modules,
    floor=3625,
    growth=300,
    roots=_ROOTS,
    what="non-test backend, SLM and shared modules scanned for a 4xx answered 'Internal server error'",
)
#: 4xx calls seen on the live tree (2242 measured by the reach-floor check, 2026-11-22); growth 300 puts the pin
#: mid-window (2242 - 150). Declared below, so a detector that stopped matching fails as a reach error, not a clean pass.
_STATUS_SEEN_FLOOR = 2092


def _status_of(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    name = getattr(node, "attr", getattr(node, "id", ""))
    match = _STATUS_NAME.match(name) if isinstance(name, str) else None
    return int(match.group(1)) if match else None


def _call_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _call_status(call: ast.Call) -> int | None:
    """The status a call carries: `status_code=` / `status=`, else the first positional that reads as one."""
    for kw in call.keywords:
        if kw.arg in {"status_code", "status"}:
            return _status_of(kw.value)
    helper = _RAISE_HELPER.fullmatch(_call_name(call))
    if helper:
        return _RAISE_HELPER_CODE.get(helper.group(1), 422)
    # A positional status on any call: HTTPException(404, ...), error_response("...", 422).
    return next((st for st in (_status_of(a) for a in call.args) if st is not None), None)


def _says_generic(call: ast.Call) -> bool:
    """A string constant in the call's arguments starts with 'Internal server error' (any case, any suffix)."""
    parts = [*call.args, *(kw.value for kw in call.keywords)]
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip().lower().startswith(_GENERIC)
        for part in parts
        for n in ast.walk(part)
    )


def client_error_sites(source: str, rel: str) -> tuple[list[str], list[str]]:
    """`(offending sites, every 4xx call seen as "rel:line")` in *source*."""
    bad: list[str] = []
    seen: list[str] = []
    for node in ast.walk(parse_cache.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        code = _call_status(node)
        if code is None or not 400 <= code < 500:
            continue
        seen.append(f"{rel}:{node.lineno}")
        if _says_generic(node):
            bad.append(f"{rel}:{node.lineno}: {code} answered 'Internal server error'")
    return bad, seen


def _scan(root: Path) -> tuple[list[str], list[str]]:
    """Every offending site and every 4xx call seen across the scanned modules."""
    bad: list[str] = []
    seen: list[str] = []
    for path in _modules(root):
        found, calls = client_error_sites(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix())
        bad += found
        seen += calls
    return bad, seen


def _status_calls(root: Path) -> list[str]:
    """Every 4xx call the detector recognised, as "rel:line"; empty on an empty tree."""
    return _scan(root)[1]


STATUS_REACH = declare(
    "client-error-4xx-calls-21943",
    discover=_status_calls,
    floor=_STATUS_SEEN_FLOOR,
    growth=300,
    what="4xx status calls the client-error detector recognised in the scanned modules",
)


def _wrap(call: str) -> str:
    return f"def h():\n    try:\n        run()\n    except KeyError:\n        raise {call}\n"


_FIRES = [
    ("single_line", _wrap('HTTPException(status_code=404, detail="Internal server error")')),
    ("positional", _wrap('HTTPException(404, "Internal server error")')),
    ("status_name", _wrap('HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Internal server error")')),
    (
        "multi_line",
        _wrap(
            'HTTPException(\n            status_code=status.HTTP_404_NOT_FOUND,\n            detail="Internal server error",\n        )'
        ),
    ),
    ("lowercase", _wrap('HTTPException(400, detail="internal server error")')),
    ("response_builder", "def h():\n    return error_response('Internal server error', status_code=422)\n"),
    ("raise_helper", _wrap('raise_not_found("Internal server error")')),
    ("json_body", "def h():\n    return JSONResponse({'detail': 'Internal server error'}, status_code=403)\n"),
    ("prefixed_text", _wrap('HTTPException(404, detail="Internal server error: lookup failed")')),
    ("builder_positional_status", "def h():\n    return error_response('Internal server error', 422)\n"),
    ("invalid_input_helper", _wrap('raise_invalid_input("request", "Internal server error")')),
]
_QUIET = [
    ("five_hundred", _wrap('HTTPException(status_code=500, detail="Internal server error")')),
    ("five_hundred_name", _wrap('HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")')),
    ("specific_message", _wrap('HTTPException(status_code=404, detail="Company not found")')),
    ("fixed_refusal", _wrap("fixed_refusal(status.HTTP_404_NOT_FOUND)")),
    ("prose_in_longer_text", _wrap('HTTPException(404, "Not an Internal server error")')),
]


@pytest.mark.parametrize(("name", "source"), _FIRES, ids=[n for n, _ in _FIRES])
def test_the_scan_catches_a_planted_client_error_saying_server_error(name: str, source: str) -> None:
    bad, seen = client_error_sites(source, "planted.py")
    assert (len(bad), len(seen)) == (1, 1), f"{name}: the detector missed a planted bad site"


@pytest.mark.parametrize(("name", "source"), _QUIET, ids=[n for n, _ in _QUIET])
def test_the_scan_leaves_a_correct_answer_alone(name: str, source: str) -> None:
    assert client_error_sites(source, "ok.py")[0] == [], name


def test_the_one_refusal_table_never_calls_a_client_error_a_server_error() -> None:
    assert [(c, t) for c, t in REFUSAL_TEXT.items() if t.strip().lower() == _GENERIC] == []
    assert {400, 401, 403, 404, 409, 422, 429} <= set(REFUSAL_TEXT)


def test_no_4xx_says_internal_server_error_on_the_live_tree() -> None:
    root = repo_root()
    REACH.completed(REACH.examined(root))
    bad, seen = _scan(root)
    STATUS_REACH.completed(seen)  # a detector that no longer matches fails here, not as a clean pass
    assert not bad, "answer a refusal with `autobot_shared.http_refusal.fixed_refusal(status)` (#21943): " + "; ".join(
        bad
    )
