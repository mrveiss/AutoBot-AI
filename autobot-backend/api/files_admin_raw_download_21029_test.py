# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21029: the SLM admin file browser's raw route returns the file's exact bytes.

``/files/read`` decodes with ``errors="replace"``, so any byte that is not valid UTF-8
becomes U+FFFD. ``/files/raw`` must hand the bytes back untouched.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_MODULE = Path(__file__).resolve().parent / "files_admin_raw.py"

PAYLOAD = bytes([0xFF, 0xD8, 0x00, 0x80, 0x89, 0x50, 0x4E, 0x47])


@pytest.fixture(scope="module")
def files_mod():
    """Load the route module with ``api.files`` replaced by a stub exposing the validator.

    The real ``api.files`` drags in the whole schema/auth import chain; only
    ``_validate_admin_path`` is used here, and each test replaces it.
    """
    auth = types.ModuleType("auth_middleware")
    auth.check_admin_permission = lambda: None  # type: ignore[attr-defined]
    saved_auth = sys.modules.get("auth_middleware")
    sys.modules["auth_middleware"] = auth
    stub = types.ModuleType("api.files")
    stub._validate_admin_path = lambda p: Path(p)  # type: ignore[attr-defined]
    saved = sys.modules.get("api.files")
    sys.modules["api.files"] = stub
    try:
        spec = importlib.util.spec_from_file_location("_files_admin_raw_test", _MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved_auth is None:
            sys.modules.pop("auth_middleware", None)
        else:
            sys.modules["auth_middleware"] = saved_auth
        if saved is None:
            sys.modules.pop("api.files", None)
        else:
            sys.modules["api.files"] = saved


@pytest.fixture
def served(files_mod, tmp_path, monkeypatch):
    target = tmp_path / "blob.bin"
    target.write_bytes(PAYLOAD)
    monkeypatch.setattr(files_mod, "_validate_admin_path", lambda p: tmp_path / p)
    return files_mod


def _body(response) -> bytes:
    async def collect():
        chunks = []

        async def send(message):
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        async def receive():
            return {"type": "http.request"}

        await response({"type": "http", "method": "GET", "headers": []}, receive, send)
        return b"".join(chunks)

    return asyncio.run(collect())


def test_control_read_route_corrupts_the_payload(served):
    """Planted control: the text route is lossy for this payload, so the test can see it."""
    text = PAYLOAD.decode("utf-8", errors="replace")
    assert text.encode("utf-8") != PAYLOAD


def test_raw_route_returns_exact_bytes(served):
    response = asyncio.run(served.admin_download_file("blob.bin"))
    assert _body(response) == PAYLOAD
    assert response.media_type == "application/octet-stream"
    assert "blob.bin" in response.headers["content-disposition"]


def test_raw_route_404_for_missing_file(served):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(served.admin_download_file("missing.bin"))
    assert exc.value.status_code == 404
