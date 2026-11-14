# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No LLC response is built from exception text (#21579).

An exception's message can hold a driver message, a path or another company's data. A route may show an
exception's `public_detail` or the fixed text `llc.api._common.http_refusal` chooses; nothing else. The scanner
is `repo_tests/_company_os_exception_text_scan.py`; known sites are in
`repo_tests/_company_os_exception_text_baseline.py` and may only shrink (docs/developer/RATCHET_BASELINES.md).
"""

from __future__ import annotations

import pytest
from repo_tests._company_os_exception_text_baseline import COMPANY_OS_EXCEPTION_TEXT_SITES
from repo_tests._company_os_exception_text_scan import scan_source, scan_tree
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_file_present, base_table, raised_known_entries

_BASELINE = "repo_tests/_company_os_exception_text_baseline.py"
_TABLE = "COMPANY_OS_EXCEPTION_TEXT_SITES"
_FIX = "Answer through `http_refusal(...)` or the exception's `public_detail` (#21579)."


def _wrap(call: str, params: str = "") -> str:
    return f"def h({params}):\n    try:\n        run()\n    except ValueError as exc:\n        raise {call}\n"


def _param(call: str) -> str:
    return f"def helper(exc):\n    return {call}\n"


_FIRES = [
    ("str_of_exc", _wrap("HTTPException(400, detail=str(exc))")),
    ("fstring_of_exc", _wrap('HTTPException(400, detail=f"bad: {exc}")')),
    ("repr_of_exc", _wrap("HTTPException(400, detail=repr(exc))")),
    ("exc_args", _wrap("HTTPException(400, detail=exc.args[0])")),
    ("exc_message", _wrap("HTTPException(400, detail=exc.message)")),
    ("exc_other_attribute", _wrap("HTTPException(400, detail=exc.reason)")),
    ("dict_value", _wrap('JSONResponse({"detail": str(exc)}, 400)')),
    ("list_value", _wrap('Response(content=["x", f"{exc}"])')),
    (
        "tainted_local",
        "def h():\n    try:\n        run()\n    except ValueError as exc:\n        msg = str(exc)\n        raise HTTPException(400, detail=msg)\n",
    ),
    (
        "tainted_local_chain",
        "def h():\n    try:\n        run()\n    except ValueError as exc:\n        a = f'x {exc}'\n        b: str = a\n        raise HTTPException(400, detail=b)\n",
    ),
    ("param_str", _param("HTTPException(400, detail=str(exc))")),
    ("param_fstring", _param('HTTPException(400, detail=f"bad {exc}")')),
    ("param_args", _param("HTTPException(400, detail=exc.args[0])")),
]
_QUIET = [
    ("http_refusal", _wrap('http_refusal(400, exc, scope="x.y")')),
    ("http_refusal_detail", _wrap('HTTPException(400, detail=http_refusal(400, exc, scope="x").detail)')),
    ("public_detail", _wrap("HTTPException(400, detail=exc.public_detail)")),
    ("errors_attribute", _wrap('HTTPException(422, detail={"errors": exc.errors})')),
    ("ids_not_bound_by_except", _wrap('HTTPException(404, detail=f"item {item_id} not found")', "item_id")),
    (
        "from_exc_chain",
        "def h():\n    try:\n        run()\n    except ValueError as exc:\n        raise HTTPException(400, 'x') from exc\n",
    ),
    (
        "public_local",
        "def h():\n    try:\n        run()\n    except ValueError as exc:\n        msg = exc.public_detail\n        raise HTTPException(400, detail=msg)\n",
    ),
    (
        "isinstance_local",
        "def h():\n    try:\n        run()\n    except ValueError as exc:\n        msg = isinstance(exc, KeyError)\n        raise HTTPException(400, detail=msg)\n",
    ),
    ("isinstance_test", _wrap("HTTPException(413 if isinstance(exc, KeyError) else 400, detail='x')")),
    ("param_passed_through", _param("HTTPException(400, detail=exc)")),
    ("param_public_detail", _param("HTTPException(400, detail=exc.public_detail)")),
    ("inside_http_refusal", "def http_refusal(exc):\n    return HTTPException(400, detail=str(exc))\n"),
]


@pytest.mark.parametrize(("source"), [s for _, s in _FIRES], ids=[i for i, _ in _FIRES])
def test_the_scanner_fires_on_exception_text(source: str) -> None:
    assert scan_source(source, "x.py")


@pytest.mark.parametrize(("source"), [s for _, s in _QUIET], ids=[i for i, _ in _QUIET])
def test_the_scanner_is_quiet_on_a_public_answer(source: str) -> None:
    assert scan_source(source, "x.py") == []


def test_a_site_is_named_by_path_function_and_occurrence() -> None:
    source = "class C:\n    def m(self):\n        try:\n            f()\n        except E as e:\n            raise HTTPException(400, str(e))\n            raise HTTPException(400, str(e))\n"
    assert scan_source(source, "a/b.py") == ["a/b.py::C.m#1", "a/b.py::C.m#2"]


@pytest.fixture(scope="module")
def measured() -> dict[str, int]:
    return scan_tree(repo_root())


def test_the_scan_reads_the_llc_tree(measured: dict[str, int]) -> None:
    assert (repo_root() / "autobot-backend" / "llc" / "api" / "_common.py").is_file(), "llc has moved; update the scan"
    assert all(k.startswith("autobot-backend/llc/") for k in measured)


def test_the_tree_matches_its_baseline(measured: dict[str, int]) -> None:
    assert measured == COMPANY_OS_EXCEPTION_TEXT_SITES, (
        f"measured {sorted(measured)}, pinned {sorted(COMPANY_OS_EXCEPTION_TEXT_SITES)}. Equality, so a new site "
        f"fails and a converted one is deleted from the baseline rather than left as headroom. {_FIX}"
    )


def test_no_site_was_added_against_the_base() -> None:
    root = repo_root()
    if not base_file_present(root, (_BASELINE,)):
        return  # the baseline is new at this head: it starts at its first measurement (#21573)
    base = base_table(root, (_BASELINE,), _TABLE, absent_as_empty=True)
    added = sorted(set(COMPANY_OS_EXCEPTION_TEXT_SITES) - set(base))
    assert not added, f"sites added against the base: {added}. {_FIX}"
    assert not raised_known_entries(COMPANY_OS_EXCEPTION_TEXT_SITES, base)
