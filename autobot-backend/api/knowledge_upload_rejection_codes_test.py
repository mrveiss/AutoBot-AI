# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every upload rejection emits a stable ``detail_code`` (#17577)."""

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from knowledge.upload_rejections import UploadRejection, UploadRejectionCode, upload_rejection_handler

_API = Path(__file__).parent
_UPLOAD_PATH = {
    "knowledge.py": {
        "_validate_file_upload",
        "require_safe_kb_name",
        "_extract_pdf_document",
        "_extract_docx_document",
        "_extract_file_content",
        "upload_file_to_knowledge",
    },
    "../knowledge/kb_ingest_result.py": {"ingest_in_kb"},
    "../knowledge/upload_rejections.py": {"no_text_rejection", "extract_within_deadline"},
    "knowledge_office_upload.py": {"extract_office_upload", "verified_upload_extension"},
}


def _raises():
    for filename, names in _UPLOAD_PATH.items():
        tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
        found = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name in names:
                found.add(fn.name)
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and getattr(node.func, "id", "") in (
                        "HTTPException",
                        "UploadRejection",
                    ):
                        yield filename, fn.name, node
        assert found == names, "upload-path function renamed; update the contract: %s" % (names - found)


def test_no_upload_path_raise_is_a_bare_http_exception():
    bare = [(f, n) for f, n, call in _raises() if getattr(call.func, "id", "") == "HTTPException"]
    assert not bare, "rejection without a detail_code: %s" % bare


def test_every_upload_rejection_names_a_member_of_the_enum_and_each_member_is_used():
    used = set()
    for _f, _n, call in _raises():
        if getattr(call.func, "id", "") != "UploadRejection":
            continue
        first = call.args[0]
        assert isinstance(first, ast.Attribute) and first.value.id == "UploadRejectionCode"
        used.add(UploadRejectionCode[first.attr])
    assert used == set(UploadRejectionCode), "unused codes: %s" % (set(UploadRejectionCode) - used)


def test_codes_are_stable_unique_identifiers():
    values = [c.value for c in UploadRejectionCode]
    assert len(values) == len(set(values)) and all(v.startswith("upload.") for v in values)


def test_response_carries_code_params_and_the_legacy_english_detail():
    app = FastAPI()
    app.add_exception_handler(UploadRejection, upload_rejection_handler)

    @app.get("/x")
    def _x():
        raise UploadRejection(UploadRejectionCode.TOO_LARGE, "File too large. Maximum size is 10MB", max_mb=10)

    @app.get("/plain")
    def _plain():
        raise HTTPException(status_code=400, detail="nope")

    client = TestClient(app)
    resp = client.get("/x")
    assert resp.status_code == 400
    assert resp.json() == {
        "detail": "File too large. Maximum size is 10MB",
        "detail_code": "upload.too_large",
        "detail_params": {"max_mb": 10},
    }
    assert client.get("/plain").json() == {"detail": "nope"}


def test_validation_sites_emit_their_codes():
    from api.knowledge import MAX_FILE_SIZE_BYTES, _validate_file_upload

    with pytest.raises(UploadRejection) as big:
        _validate_file_upload("a.txt", MAX_FILE_SIZE_BYTES + 1)
    assert big.value.detail_code == "upload.too_large" and big.value.detail_params == {"max_mb": 10}
    with pytest.raises(UploadRejection) as typ:
        _validate_file_upload("a.exe", 1)
    assert typ.value.detail_code == "upload.unsupported_type" and ".txt" in typ.value.detail_params["allowed"]
