# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one KB uploader (#19339): payload, rendering, failures -- with the real egress check."""

import importlib.util
import pathlib
import sys
from unittest.mock import MagicMock, patch

_MODULE_PATH = pathlib.Path(__file__).with_name("kb_api_upload.py")


def _load_module():
    """Import kb_api_upload by path -- its directory is not a package (as create_kb_index_test does)."""
    spec = importlib.util.spec_from_file_location("kb_api_upload", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["kb_api_upload"] = module
    spec.loader.exec_module(module)
    return module


kb_api_upload = _load_module()


def _ok():
    return MagicMock(status_code=200, text="")


def test_a_doc_is_posted_to_add_text_with_its_title_and_the_egress_check_passes(tmp_path) -> None:
    doc = tmp_path / "docs" / "a.md"
    doc.parent.mkdir()
    doc.write_text("hello", encoding="utf-8")
    with patch.object(kb_api_upload.requests, "post", return_value=_ok()) as post:
        result = kb_api_upload.upload_doc(str(doc), str(tmp_path), "Project Docs")
    assert result.success, result.error
    url = post.call_args.args[0]
    assert url == f"{kb_api_upload.API_URL}/api/knowledge_base/add_text"
    assert post.call_args.kwargs["allow_redirects"] is False
    assert post.call_args.kwargs["json"] == {
        "text": "hello",
        "title": "Project Docs: docs/a.md",
        "source": "project-documentation",
    }


def test_render_shapes_the_stored_text(tmp_path) -> None:
    doc = tmp_path / "b.md"
    doc.write_text("body", encoding="utf-8")
    with patch.object(kb_api_upload.requests, "post", return_value=_ok()) as post:
        kb_api_upload.upload_doc(str(doc), str(tmp_path), "Documentation", render=lambda r, p, c: f"FILE: {r}\n{c}")
    assert post.call_args.kwargs["json"]["text"] == "FILE: b.md\nbody"


def test_an_empty_file_and_a_server_error_are_failures_not_exceptions(tmp_path) -> None:
    empty = tmp_path / "e.md"
    empty.write_text("  \n", encoding="utf-8")
    assert kb_api_upload.upload_doc(str(empty), str(tmp_path), "x").error == "Empty file"
    full = tmp_path / "f.md"
    full.write_text("x", encoding="utf-8")
    with patch.object(kb_api_upload.requests, "post", return_value=MagicMock(status_code=500, text="boom")):
        assert kb_api_upload.upload_doc(str(full), str(tmp_path), "x").error == "boom"


def test_a_batch_returns_one_result_per_file(tmp_path) -> None:
    files = []
    for name in ("1.md", "2.md", "3.md"):
        (tmp_path / name).write_text(name, encoding="utf-8")
        files.append(str(tmp_path / name))
    with patch.object(kb_api_upload.requests, "post", return_value=_ok()):
        results = kb_api_upload.upload_docs(files, str(tmp_path), "x", max_workers=2)
    assert sorted(r.rel_path for r in results) == ["1.md", "2.md", "3.md"] and all(r.success for r in results)
