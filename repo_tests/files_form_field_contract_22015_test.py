# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The form fields the file browser sends must be the form fields the routes declare (#22015).

``useFileBrowser`` appended ``files`` to ``POST /api/files/upload`` while the route requires ``file``: a 422
on every upload from the chat's Files panel. Two mocks agreeing with each other cannot see that, so this reads
the route's real signature (FastAPI's own dependant) and the frontend's committed source (a static scan, nothing
is executed) and compares the two. The same is done for the sibling ``rename`` and ``create_directory`` routes
the composable also posts forms to, and for the conversation upload route the chat composable posts to.

Existing guards and why this one is separate: ``frontend_api_contract_ratchet_test.py`` and
``sdk_ts_request_contract_test.py`` pin URLs, verbs, query parameters and JSON body fields. Neither looks at the
multipart FORM fields a ``FormData`` carries, which is exactly where ``file`` vs ``files`` went unseen.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

_FRONTEND = repo_root() / "autobot-frontend" / "src" / "composables"
_FILE_BROWSER = _FRONTEND / "file-browser" / "useFileBrowser.ts"
_CONVERSATION = _FRONTEND / "useConversationFiles.ts"


def _body_field_names(router, suffix: str) -> set[str]:
    route = next(r for r in router.routes if getattr(r, "path", "").endswith(suffix))
    return {p.alias or p.name for p in route.dependant.body_params}


def _required_field_names(router, suffix: str) -> set[str]:
    route = next(r for r in router.routes if getattr(r, "path", "").endswith(suffix))
    return {p.alias or p.name for p in route.dependant.body_params if p.field_info.is_required()}


def _upload_form_fields(source: str) -> set[str]:
    block = re.search(r"UPLOAD_FORM_FIELDS\s*=\s*\{(.*?)\}\s*as const", source, re.S)
    assert block, "UPLOAD_FORM_FIELDS is no longer declared in useFileBrowser.ts"
    return set(re.findall(r""":\s*['"]([^'"]+)['"]""", block.group(1)))


def _section(source: str, marker: str) -> str:
    start = source.index(marker)
    nxt = source.find("// ---- ", start + len(marker))
    return source[start : nxt if nxt != -1 else len(source)]


def _literal_appends(text: str) -> set[str]:
    return set(re.findall(r"""\.append\(\s*['"]([^'"]+)['"]""", text))


def test_upload_form_fields_are_the_route_parameters():
    from api.files import router

    sent = _upload_form_fields(_FILE_BROWSER.read_text(encoding="utf-8"))
    declared = _body_field_names(router, "/upload")
    assert sent == declared, f"frontend sends {sorted(sent)}, POST /upload declares {sorted(declared)}"


def test_upload_sends_every_required_field():
    from api.files import router

    sent = _upload_form_fields(_FILE_BROWSER.read_text(encoding="utf-8"))
    assert _required_field_names(router, "/upload") <= sent


def test_upload_appends_through_the_pinned_field_names():
    section = _section(_FILE_BROWSER.read_text(encoding="utf-8"), "/** Upload one file;")
    for name in ("file", "path", "overwrite"):
        assert f"append(UPLOAD_FORM_FIELDS.{name}," in section, f"{name} is not appended through the pinned constant"
    assert not re.search(r"""append\(\s*['"]files['"]""", section)


@pytest.mark.parametrize(
    ("marker", "suffix"),
    [
        ("// ---- POST /files/rename ----", "/rename"),
        ("// ---- POST /files/create_directory ----", "/create_directory"),
    ],
)
def test_sibling_form_posts_send_exactly_the_declared_fields(marker, suffix):
    from api.files import router

    sent = _literal_appends(_section(_FILE_BROWSER.read_text(encoding="utf-8"), marker))
    assert sent == _body_field_names(router, suffix)


def test_conversation_upload_sends_the_declared_file_field():
    from api.conversation_files import router

    sent = _literal_appends(_section_of_send_upload(_CONVERSATION.read_text(encoding="utf-8")))
    declared = _body_field_names(router, "/upload")
    assert sent and sent <= declared, f"sends {sorted(sent)}, route declares {sorted(declared)}"
    assert "file" in sent


def _section_of_send_upload(source: str) -> str:
    start = source.index("const postEach")
    return source[start : source.index("const uploadFiles", start)]
