# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An omitted bool Form field keeps its declared default on /upload (#18060).

fastapi 0.162 changed how an omitted bool form field is parsed, so every bool
``Form`` parameter must state its default explicitly. ``overwrite`` is the one
on the file-upload route; a client that does not send it (the common case)
must get ``False`` and not a 422 for a missing required field.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.files import router


def _upload_route():
    return next(r for r in router.routes if getattr(r, "path", "").endswith("/upload"))


def test_overwrite_is_an_optional_form_field_defaulting_to_false():
    params = {p.name: p for p in _upload_route().dependant.body_params}
    assert "overwrite" in params
    assert params["overwrite"].field_info.is_required() is False
    assert params["overwrite"].field_info.default is False


def test_omitting_overwrite_does_not_fail_form_validation():
    """A 422, if any, may name only fields that are really missing -- never ``overwrite``."""
    app = FastAPI()
    app.include_router(router, prefix="/files")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/files" + _upload_route().path,
        files={"file": ("a.py", b"x = 1\n")},
        data={"path": ""},
    )
    missing = []
    if response.status_code == 422:
        missing = [e["loc"][-1] for e in response.json().get("detail", []) if e.get("type") == "missing"]
    assert "overwrite" not in missing
