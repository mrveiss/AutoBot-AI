# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for tools/lint/check_response_models.py — see #5924.

Covers detection, safe predicates, and exit codes for the hook that
prevents response_model=DataResponse on endpoints that would produce
HTTP 500 ValidationError at runtime (#5913).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_HOOK_PATH = Path(__file__).parent / "check_response_models.py"
_spec = importlib.util.spec_from_file_location("_hook_under_test", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "case.py"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Positive cases — should FAIL (exit 1)
# ---------------------------------------------------------------------------


def test_detects_missing_success_in_return_dict(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
from fastapi import APIRouter
router = APIRouter()

@router.get("/foo", response_model=DataResponse)
async def get_foo():
    return {"data": "bar"}
""",
    )
    repo = tmp_path
    violations = hook._check_file(f, repo)
    assert len(violations) == 1
    assert violations[0][1] == "get_foo"


def test_detects_plain_dict_return_no_success(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.post("/submit", response_model=DataResponse)
def submit():
    return {"result": 42, "count": 1}
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1


def test_detects_multiple_violations_in_one_file(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/a", response_model=DataResponse)
async def get_a():
    return {"items": []}

@router.get("/b", response_model=DataResponse)
async def get_b():
    return {"count": 0}
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 2
    assert {v[1] for v in violations} == {"get_a", "get_b"}


def test_detects_async_def_route(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.delete("/item", response_model=DataResponse)
async def delete_item():
    return {"removed": True}
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][1] == "delete_item"


# ---------------------------------------------------------------------------
# Negative cases — should PASS (no violations)
# ---------------------------------------------------------------------------


def test_safe_with_create_success_response(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/ok", response_model=DataResponse)
async def get_ok():
    return create_success_response(data={"key": "value"})
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_with_success_key_in_literal(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.post("/manual", response_model=DataResponse)
def manual():
    return {"success": True, "data": None}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_with_jsonresponse(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
from fastapi.responses import JSONResponse

@router.get("/raw", response_model=DataResponse)
async def raw():
    return JSONResponse(content={"key": "val"})
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_with_streamingresponse(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/stream", response_model=DataResponse)
async def stream():
    return StreamingResponse(iter([b"data"]))
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_response_model_none(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/none", response_model=None)
async def get_none():
    return {"items": []}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_no_response_model_annotation(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/unannotated")
async def get_unannotated():
    return {"items": []}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_custom_schema(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/typed", response_model=MySchema)
async def get_typed():
    return {"items": []}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_create_success_response_via_attribute(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/attr", response_model=DataResponse)
async def get_attr():
    return helpers.create_success_response(data={})
""",
    )
    assert hook._check_file(f, tmp_path) == []


# ---------------------------------------------------------------------------
# Exit-code integration
# ---------------------------------------------------------------------------


def test_main_returns_0_for_clean_file(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/clean", response_model=DataResponse)
async def clean():
    return create_success_response()
""",
    )
    assert hook.main(["hook", str(f)]) == 0


def test_main_returns_1_for_violation(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/bad", response_model=DataResponse)
async def bad():
    return {"no_success": True}
""",
    )
    assert hook.main(["hook", str(f)]) == 1


def test_main_returns_0_for_file_with_no_dataresponse(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
@router.get("/clean", response_model=None)
async def clean():
    return {"items": []}
""",
    )
    assert hook.main(["hook", str(f)]) == 0
