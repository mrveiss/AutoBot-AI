# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for tools/lint/check_response_models.py — see #5924.

Covers detection, safe predicates, and exit codes for the hook that
prevents response_model=DataResponse on endpoints that would produce
HTTP 500 ValidationError at runtime (#5913).

Extended in #6143: import-order checks — schema name must be imported
before the decorator line that references it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_HOOK_PATH = Path(__file__).parent / "check_response_models.py"
_spec = importlib.util.spec_from_file_location("_hook_under_test", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

# Reusable import preamble — added to all test snippets that use checked schemas
# so that import-order checks do not fire (only shape checks are tested).
_DR = "from schemas import DataResponse\n"
_SMR = "from schemas import SuccessMessageResponse\n"
_SDR = "from schemas import SuccessDataResponse\n"


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
        _DR + """
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
    # Shape violation: detail is None
    assert violations[0][2] is None


def test_detects_plain_dict_return_no_success(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.post("/submit", response_model=DataResponse)
def submit():
    return {"result": 42, "count": 1}
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][2] is None  # shape violation


def test_detects_multiple_violations_in_one_file(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
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
        _DR + """
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
        _DR + """
@router.get("/ok", response_model=DataResponse)
async def get_ok():
    return create_success_response(data={"key": "value"})
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_with_success_key_in_literal(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.post("/manual", response_model=DataResponse)
def manual():
    return {"success": True, "data": None}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_with_jsonresponse(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
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
        _DR + """
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
    """Non-checked schema names are not validated at all (no import-order check)."""
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
        _DR + """
@router.get("/attr", response_model=DataResponse)
async def get_attr():
    return helpers.create_success_response(data={})
""",
    )
    assert hook._check_file(f, tmp_path) == []


# ---------------------------------------------------------------------------
# SuccessMessageResponse / SuccessDataResponse — extended coverage (#5925)
# ---------------------------------------------------------------------------


def test_detects_success_message_response_missing_required_keys(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _SMR + """
@router.post("/msg", response_model=SuccessMessageResponse)
async def post_msg():
    return {"success": True}  # missing 'message'
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][1] == "post_msg"


def test_safe_success_message_response_with_both_keys(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _SMR + """
@router.post("/msg", response_model=SuccessMessageResponse)
async def post_msg():
    return {"success": True, "message": "done"}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_detects_success_data_response_missing_message(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _SDR + """
@router.post("/data", response_model=SuccessDataResponse)
async def post_data():
    return {"success": True, "data": {}}  # missing 'message'
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1


def test_safe_success_data_response_with_required_keys(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _SDR + """
@router.post("/data", response_model=SuccessDataResponse)
async def post_data():
    return {"success": True, "message": "ok", "data": None}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_success_message_response_with_bypass(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _SMR + """
@router.get("/stream", response_model=SuccessMessageResponse)
async def stream():
    return StreamingResponse(iter([b"x"]))
""",
    )
    assert hook._check_file(f, tmp_path) == []


# ---------------------------------------------------------------------------
# Exit-code integration
# ---------------------------------------------------------------------------


def test_main_returns_0_for_clean_file(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.get("/clean", response_model=DataResponse)
async def clean():
    return create_success_response()
""",
    )
    assert hook.main(["hook", str(f)]) == 0


def test_main_returns_1_for_violation(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
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


# ---------------------------------------------------------------------------
# Variable-assignment pattern (#5926) — single-assignment tracking
# ---------------------------------------------------------------------------


def test_safe_variable_assigned_dict_with_success(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.get("/var", response_model=DataResponse)
async def get_var():
    result = {"success": True, "data": []}
    return result
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_detects_variable_assigned_dict_missing_success(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.get("/var", response_model=DataResponse)
async def get_var():
    result = {"data": [], "count": 0}
    return result
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][1] == "get_var"


def test_safe_success_message_response_variable_assignment(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _SMR + """
@router.post("/msg", response_model=SuccessMessageResponse)
async def post_msg():
    response = {"success": True, "message": "done"}
    return response
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_detects_success_message_response_variable_missing_message(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _SMR + """
@router.post("/msg", response_model=SuccessMessageResponse)
async def post_msg():
    response = {"success": True}
    return response
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Attribute-access bypass (#5965) — responses.JSONResponse / module.StreamingResponse
# ---------------------------------------------------------------------------


def test_safe_with_jsonresponse_via_attribute(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.get("/raw", response_model=DataResponse)
async def raw():
    return responses.JSONResponse(content={"key": "val"})
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_with_streamingresponse_via_attribute(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.get("/stream", response_model=DataResponse)
async def stream():
    return some_module.StreamingResponse(iter([b"data"]))
""",
    )
    assert hook._check_file(f, tmp_path) == []


# ---------------------------------------------------------------------------
# Nested-function scope isolation (#5964) — inner dict must not bleed out
# ---------------------------------------------------------------------------


def test_detects_violation_when_only_nested_function_has_success_dict(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        _DR + """
@router.get("/bad", response_model=DataResponse)
async def bad_endpoint():
    async def _build():
        result = {"success": True, "data": []}
        return result
    return {"items": [], "count": 0}
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][1] == "bad_endpoint"


# ---------------------------------------------------------------------------
# Import-order checks (#6143) — schema must be imported before its decorator
# ---------------------------------------------------------------------------


def test_safe_import_before_decorator(tmp_path: Path) -> None:
    """Import appears before decorator — no import-order violation."""
    f = _write(
        tmp_path,
        """
from schemas import DataResponse

@router.get("/ok", response_model=DataResponse)
async def get_ok():
    return {"success": True}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_detects_import_after_decorator(tmp_path: Path) -> None:
    """Import appears after decorator line — import-order violation."""
    f = _write(
        tmp_path,
        """
@router.get("/bad", response_model=DataResponse)
async def get_bad():
    return {"success": True}

from schemas import DataResponse
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][1] == "get_bad"
    # Third element is the detail message, not None (import-order violation)
    detail = violations[0][2]
    assert detail is not None
    assert "DataResponse" in detail
    assert "import" in detail.lower()


def test_detects_missing_import_for_checked_schema(tmp_path: Path) -> None:
    """Schema name never imported at all — missing-import violation."""
    f = _write(
        tmp_path,
        """
@router.get("/bad", response_model=DataResponse)
async def get_bad():
    return {"success": True}
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][1] == "get_bad"
    detail = violations[0][2]
    assert detail is not None
    assert "DataResponse" in detail
    assert "import" in detail.lower()


def test_safe_import_via_alias_before_decorator(tmp_path: Path) -> None:
    """Schema imported with alias — the alias name is what matters for the decorator."""
    f = _write(
        tmp_path,
        """
from schemas import DataResponse as DataResponse

@router.get("/ok", response_model=DataResponse)
async def get_ok():
    return {"success": True}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_safe_success_message_response_import_before_decorator(tmp_path: Path) -> None:
    """SuccessMessageResponse imported before decorator — no import-order violation."""
    f = _write(
        tmp_path,
        """
from schemas import SuccessMessageResponse

@router.post("/msg", response_model=SuccessMessageResponse)
async def post_msg():
    return {"success": True, "message": "done"}
""",
    )
    assert hook._check_file(f, tmp_path) == []


def test_detects_import_after_decorator_with_line_numbers_in_message(tmp_path: Path) -> None:
    """Error message includes both the import line and the decorator line."""
    f = _write(
        tmp_path,
        """
@router.get("/bad", response_model=DataResponse)
async def get_bad():
    return {"success": True}

from schemas import DataResponse
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    detail = violations[0][2]
    assert detail is not None
    # Both line numbers should appear in the message
    assert "2" in detail  # decorator line
    assert "6" in detail  # import line


def test_return_shape_violation_has_none_detail(tmp_path: Path) -> None:
    """Return-shape violations carry None as the detail (not an import-order message)."""
    f = _write(
        tmp_path,
        _DR + """
@router.get("/bad", response_model=DataResponse)
async def get_bad():
    return {"data": "bar"}
""",
    )
    violations = hook._check_file(f, tmp_path)
    assert len(violations) == 1
    assert violations[0][1] == "get_bad"
    # Shape violation: detail is None
    assert violations[0][2] is None


def test_import_order_violation_reported_in_main(tmp_path: Path) -> None:
    """main() reports import-order violations with exit code 1."""
    f = _write(
        tmp_path,
        """
@router.get("/bad", response_model=DataResponse)
async def get_bad():
    return {"success": True}

from schemas import DataResponse
""",
    )
    assert hook.main(["hook", str(f)]) == 1
