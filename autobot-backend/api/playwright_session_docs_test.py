# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every Playwright request model that takes `session_id` must say what omitting it does (#15802 AC2).

The middleware added by #15802 warns a caller who omits `session_id`. That
warning is only actionable if the caller can find out what omission means, and
the answer -- "you join the shared default context, along with every other
unscoped caller" -- lived on 1 of 5 models before this file existed.

`PlaywrightScreenshotRequest` is the exception that has to be stated rather than
described: it accepts the field and ignores it, because the embedded service it
drives (`services/playwright_service.py`) has no session concept at all. A
caller who supplies an id there is silently unscoped *and* silent to the
middleware, which warns on omission only -- reassured rather than merely
unaware (#15871).
"""

from __future__ import annotations

from api import schemas_code

#: Measured on the tree that introduced this file: Screenshot, Navigate,
#: Reload, Interact, Session. This is a REACH floor, not a target -- the
#: assertion below is a negative one ("none undocumented"), and a negative
#: assertion over an empty population passes while proving nothing. If a
#: rename or a module move breaks discovery, this fails instead of going quiet.
_MIN_MODELS_TAKING_SESSION_ID = 5


def _models_taking_session_id() -> list[tuple[str, type]]:
    """Every `Playwright*Request` in the schema module that declares the field."""
    found = []
    for name in dir(schemas_code):
        if not (name.startswith("Playwright") and name.endswith("Request")):
            continue
        model = getattr(schemas_code, name)
        if "session_id" in getattr(model, "model_fields", {}):
            found.append((name, model))
    return found


def test_discovery_reaches_every_playwright_request_model() -> None:
    """The precondition for the negative assertion below."""
    found = _models_taking_session_id()
    assert len(found) >= _MIN_MODELS_TAKING_SESSION_ID, (
        f"found only {len(found)} Playwright request models declaring session_id "
        f"({[n for n, _ in found]}); expected at least "
        f"{_MIN_MODELS_TAKING_SESSION_ID}. The sweep broke -- fix it, do not lower "
        "the floor, or the documentation test below asserts nothing."
    )


def test_every_session_id_field_documents_what_omission_does() -> None:
    """#15802 AC2: the behaviour is on the model, not left to be inferred."""
    undocumented = [
        name
        for name, model in _models_taking_session_id()
        if not (model.model_fields["session_id"].description or "").strip()
    ]
    assert not undocumented, (
        "these models accept session_id without saying what omitting it does, so "
        f"the #15802 warning tells a caller nothing actionable: {undocumented}"
    )


def test_the_screenshot_route_declares_that_it_ignores_the_field() -> None:
    """The one model whose honest description is 'this does nothing here'.

    Pinned separately because it is the dangerous case and the easy thing to
    lose: a future change that threads `session_id` through `/screenshot` must
    also correct this text, and a future change that only corrects the text
    without threading it must keep saying 'ignored'. Either way the description
    and the behaviour move together.
    """
    field = schemas_code.PlaywrightScreenshotRequest.model_fields["session_id"]
    description = (field.description or "").lower()
    assert "ignored" in description, (
        "PlaywrightScreenshotRequest.session_id no longer documents that it is "
        "ignored. If /screenshot now routes into a session, say so here and "
        "close #15871; if it still does not, the caller must be told (#15871)."
    )
