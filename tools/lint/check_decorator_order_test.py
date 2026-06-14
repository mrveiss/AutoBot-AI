# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/check_decorator_order.py — see #6638, #6787.

Covers detection of:
  * Pattern A — @with_error_handling above @router.* (#6558)
  * Pattern B — adjacent stacked @with_error_handling (#6633)

Plus path filtering, exit codes, the negative case (correct ordering
is not flagged), and the ``--fix`` mode via libcst (#6787).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HOOK_PATH = Path(__file__).parent / "check_decorator_order.py"
_spec = importlib.util.spec_from_file_location("_hook_under_test", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


def _write_api(tmp_path: Path, name: str, content: str) -> tuple[Path, Path]:
    """Write a file under fake autobot-backend/api/, return (file_path, repo_root)."""
    repo_root = tmp_path
    api_dir = repo_root / "autobot-backend" / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    p = api_dir / name
    p.write_text(content, encoding="utf-8")
    return p, repo_root


# ---------------------------------------------------------------------------
# Pattern A — decorator order (@with_error_handling above @router.*)
# ---------------------------------------------------------------------------


def test_detects_with_error_handling_above_router_get(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "bad_order.py",
        """\
@with_error_handling(category="x")
@router.get("/foo")
async def foo():
    return {}
""",
    )
    hits = hook._check_file(path, repo_root)
    assert len(hits) == 1
    line, kind, msg = hits[0]
    assert kind == "order"
    assert "@router.get" in msg


def test_detects_with_error_handling_above_router_post_sync_def(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "bad_sync.py",
        """\
@with_error_handling()
@router.post("/foo")
def foo():
    return {}
""",
    )
    hits = hook._check_file(path, repo_root)
    assert len(hits) == 1
    assert hits[0][1] == "order"


def test_detects_app_decorators_too(tmp_path: Path) -> None:
    """@app.get / @app.post are also FastAPI route registrations."""
    path, repo_root = _write_api(
        tmp_path,
        "app_form.py",
        """\
@with_error_handling()
@app.get("/foo")
async def foo():
    return {}
""",
    )
    hits = hook._check_file(path, repo_root)
    assert len(hits) == 1
    assert hits[0][1] == "order"


# ---------------------------------------------------------------------------
# Pattern B — stacked duplicate @with_error_handling
# ---------------------------------------------------------------------------


def test_detects_stacked_duplicate_with_error_handling(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "stacked.py",
        """\
@router.get("/foo")
@with_error_handling(category="x")
@with_error_handling(category="x")
async def foo():
    return {}
""",
    )
    hits = hook._check_file(path, repo_root)
    kinds = sorted(h[1] for h in hits)
    assert "stacked" in kinds


# ---------------------------------------------------------------------------
# Negative — correct ordering (no violation)
# ---------------------------------------------------------------------------


def test_correct_order_no_violation(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "ok.py",
        """\
@router.get("/foo")
@with_error_handling(category="x")
async def foo():
    return {}
""",
    )
    assert hook._check_file(path, repo_root) == []


def test_no_decorators_no_violation(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "plain.py",
        """\
async def foo():
    return {}
""",
    )
    assert hook._check_file(path, repo_root) == []


def test_only_router_decorator_no_violation(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "router_only.py",
        """\
@router.get("/foo")
async def foo():
    return {}
""",
    )
    assert hook._check_file(path, repo_root) == []


def test_only_with_error_handling_no_violation(tmp_path: Path) -> None:
    """Non-route helper wrapped in @with_error_handling alone is fine."""
    path, repo_root = _write_api(
        tmp_path,
        "helper.py",
        """\
@with_error_handling()
async def helper():
    return {}
""",
    )
    assert hook._check_file(path, repo_root) == []


# ---------------------------------------------------------------------------
# Path filtering — only autobot-backend/api/**/*.py is scanned
# ---------------------------------------------------------------------------


def test_skips_files_outside_api_dir(tmp_path: Path) -> None:
    """Files outside autobot-backend/api/ are not scanned even if they trigger pattern."""
    other = tmp_path / "autobot-backend" / "services"
    other.mkdir(parents=True)
    p = other / "bad.py"
    p.write_text(
        "@with_error_handling()\n@router.get('/foo')\nasync def foo():\n    return {}\n",
        encoding="utf-8",
    )
    assert hook._check_file(p, tmp_path) == []


# ---------------------------------------------------------------------------
# Module-level smoke checks — make sure HOOK_ID and helper names are exported.
# ---------------------------------------------------------------------------


def test_hook_id_constant() -> None:
    assert hook.HOOK_ID == "decorator-order"


def test_decorator_name_helpers() -> None:
    """The internal helpers identify FastAPI route + with_error_handling decorators."""
    import ast as _ast

    tree = _ast.parse("@router.get('/x')\n@with_error_handling()\ndef f(): pass\n")
    fn = tree.body[0]
    decos = fn.decorator_list  # type: ignore[attr-defined]
    assert hook._is_router_decorator(decos[0]) is True
    assert hook._is_with_error_handling(decos[0]) is False
    assert hook._is_router_decorator(decos[1]) is False
    assert hook._is_with_error_handling(decos[1]) is True


# ---------------------------------------------------------------------------
# --fix mode tests (require libcst) — see #6787
# ---------------------------------------------------------------------------

_skip_no_libcst = pytest.mark.skipif(
    not hook._LIBCST_AVAILABLE,
    reason="libcst not installed; install with: pip install libcst",
)


@_skip_no_libcst
def test_fix_pattern_a_corrects_order(tmp_path: Path) -> None:
    """Pattern A (1): single function — decorator order corrected."""
    path, repo_root = _write_api(
        tmp_path,
        "bad_order.py",
        """\
@with_error_handling(category="x")
@router.get("/foo")
async def foo():
    return {}
""",
    )
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 1
    fixed = path.read_text(encoding="utf-8")
    assert fixed.index("@router.get") < fixed.index("@with_error_handling")
    assert hook._check_file(path, repo_root) == []


@_skip_no_libcst
def test_fix_pattern_a_idempotent(tmp_path: Path) -> None:
    """Pattern A (2): second run on already-fixed file produces 0 changes."""
    path, repo_root = _write_api(
        tmp_path,
        "ok.py",
        """\
@router.get("/foo")
@with_error_handling(category="x")
async def foo():
    return {}
""",
    )
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 0


@_skip_no_libcst
def test_fix_pattern_b_removes_duplicate(tmp_path: Path) -> None:
    """Pattern B (3): single function — outer duplicate @with_error_handling removed."""
    path, repo_root = _write_api(
        tmp_path,
        "stacked.py",
        """\
@router.get("/foo")
@with_error_handling(category="x")
@with_error_handling(category="x")
async def foo():
    return {}
""",
    )
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 1
    fixed = path.read_text(encoding="utf-8")
    assert fixed.count("@with_error_handling") == 1
    assert hook._check_file(path, repo_root) == []


@_skip_no_libcst
def test_fix_pattern_b_idempotent(tmp_path: Path) -> None:
    """Pattern B (4): second run on already-fixed file produces 0 changes."""
    path, repo_root = _write_api(
        tmp_path,
        "ok_b.py",
        """\
@router.get("/foo")
@with_error_handling(category="x")
async def foo():
    return {}
""",
    )
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 0


@_skip_no_libcst
def test_fix_pattern_a_and_b_mixed_in_one_pass(tmp_path: Path) -> None:
    """Pattern A + B (5): mixed violations in same file — both fixed in one pass."""
    path, repo_root = _write_api(
        tmp_path,
        "mixed.py",
        """\
@with_error_handling(category="x")
@router.get("/foo")
async def foo():
    return {}


@router.post("/bar")
@with_error_handling(category="y")
@with_error_handling(category="y")
async def bar():
    return {}
""",
    )
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 2
    assert hook._check_file(path, repo_root) == []


@_skip_no_libcst
def test_fix_pattern_a_preserves_docstring(tmp_path: Path) -> None:
    """Pattern A (6): docstring inside function body is preserved after fix."""
    path, repo_root = _write_api(
        tmp_path,
        "docstring.py",
        """\
@with_error_handling(category="x")
@router.get("/foo")
async def foo():
    \"\"\"Return foo resource.\"\"\"
    return {}
""",
    )
    hook._fix_file(path, repo_root)
    fixed = path.read_text(encoding="utf-8")
    assert "Return foo resource." in fixed
    assert hook._check_file(path, repo_root) == []


@_skip_no_libcst
def test_fix_pattern_a_preserves_type_annotations(tmp_path: Path) -> None:
    """Pattern A (7): type annotations are preserved after fix."""
    path, repo_root = _write_api(
        tmp_path,
        "typed.py",
        """\
@with_error_handling(category="x")
@router.get("/foo")
async def foo(item_id: int, q: str = "default") -> dict:
    return {"id": item_id, "q": q}
""",
    )
    hook._fix_file(path, repo_root)
    fixed = path.read_text(encoding="utf-8")
    assert "item_id: int" in fixed
    assert "q: str" in fixed
    assert "-> dict" in fixed
    assert hook._check_file(path, repo_root) == []


@_skip_no_libcst
def test_fix_file_with_zero_violations_unchanged(tmp_path: Path) -> None:
    """File with zero violations (8): content unchanged, 0 fixes returned."""
    content = """\
@router.get("/foo")
@with_error_handling(category="x")
async def foo():
    return {}
"""
    path, repo_root = _write_api(tmp_path, "clean.py", content)
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 0
    assert path.read_text(encoding="utf-8") == content


@_skip_no_libcst
def test_fix_multiple_functions_mixed_violations(tmp_path: Path) -> None:
    """Multiple functions (9): only violating functions are corrected."""
    path, repo_root = _write_api(
        tmp_path,
        "multi.py",
        """\
@router.get("/ok")
@with_error_handling()
async def already_correct():
    return {}


@with_error_handling()
@router.post("/bad")
async def needs_fix():
    return {}
""",
    )
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 1
    fixed = path.read_text(encoding="utf-8")
    assert "@router.get" in fixed
    assert hook._check_file(path, repo_root) == []


@_skip_no_libcst
def test_fix_three_decorators_only_wrong_pair_swapped(tmp_path: Path) -> None:
    """Three decorators (10): only the violating pair (weh, router) is swapped."""
    path, repo_root = _write_api(
        tmp_path,
        "three_decos.py",
        """\
@with_error_handling(category="x")
@router.get("/foo")
@other_decorator
async def foo():
    return {}
""",
    )
    hook._fix_file(path, repo_root)
    fixed = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in fixed.splitlines() if ln.strip().startswith("@")]
    assert lines[0].startswith("@router.get")
    assert lines[1].startswith("@with_error_handling")
    assert "@other_decorator" in fixed
    assert hook._check_file(path, repo_root) == []


@_skip_no_libcst
def test_fix_stacked_with_args_outer_removed_inner_preserved(tmp_path: Path) -> None:
    """Stacked with args (11): outer removed, args on kept (inner) decorator preserved."""
    path, repo_root = _write_api(
        tmp_path,
        "stacked_args.py",
        """\
@router.get("/foo")
@with_error_handling(log=True)
@with_error_handling(category="auth")
async def foo():
    return {}
""",
    )
    fixes = hook._fix_file(path, repo_root)
    assert fixes == 1
    fixed = path.read_text(encoding="utf-8")
    assert fixed.count("@with_error_handling") == 1
    assert 'category="auth"' in fixed
    assert hook._check_file(path, repo_root) == []
