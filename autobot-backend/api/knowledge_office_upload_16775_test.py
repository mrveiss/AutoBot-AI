# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The KB upload form accepts the office formats the backend already parses (#16775).

``DocumentParser`` has carried these parsers all along; only the upload allowlist left
them out, so a user could not upload a file the backend could read by another path.

Dispatch goes through the verified format (#16773), not the filename, so widening the
allowlist does not reintroduce the extension-trust this same surface just removed.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.knowledge_office_upload import OFFICE_EXTENSIONS, extract_office_upload, verified_upload_extension


def _ooxml_bytes(part: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(part, "<xml/>")
    return buffer.getvalue()


_XLSX = _ooxml_bytes("xl/workbook.xml")


def test_the_allowlist_gained_the_formats_the_parsers_already_read():
    from api.knowledge import ALLOWED_EXTENSIONS

    assert OFFICE_EXTENSIONS <= ALLOWED_EXTENSIONS
    assert {".xlsx", ".pptx", ".odt", ".ods", ".odp"} <= ALLOWED_EXTENSIONS


def test_the_legacy_binary_formats_stay_out():
    """.doc/.ppt are OLE2; python-docx and python-pptx read only the OOXML ones.

    Advertising them would accept a valid file and then call it corrupt — #16786, which
    needs an owner call on whether to add a real OLE2 reader or stop advertising it.
    """
    from api.knowledge import ALLOWED_EXTENSIONS

    assert ".doc" not in ALLOWED_EXTENSIONS
    assert ".ppt" not in ALLOWED_EXTENSIONS


def test_a_renamed_upload_dispatches_on_its_content():
    assert verified_upload_extension("notes.txt", _XLSX) == ".xlsx"


def test_an_honest_upload_keeps_its_own_extension():
    assert verified_upload_extension("budget.xlsx", _XLSX) == ".xlsx"


def test_a_non_archive_upload_keeps_its_name():
    assert verified_upload_extension("notes.txt", b"plain words") == ".txt"


def test_an_office_upload_is_routed_to_the_parser():
    from api.knowledge import _extract_file_content

    with patch("api.knowledge.extract_office_upload", return_value="sheet text") as office:
        content, extracted = _extract_file_content("budget.xlsx", _XLSX)

    assert (content, extracted) == ("sheet text", None)
    assert office.call_args.args[2] == ".xlsx"


def test_a_mislabeled_office_upload_reaches_the_right_parser():
    """The failure the allowlist widening must not reintroduce: trusting the name."""
    from api.knowledge import _extract_file_content

    with patch("api.knowledge.extract_office_upload", return_value="sheet text") as office:
        content, _ = _extract_file_content("notes.txt", _XLSX)

    assert content == "sheet text"
    assert office.call_args.args[2] == ".xlsx"


def test_a_plain_text_upload_is_untouched():
    from api.knowledge import _extract_file_content

    assert _extract_file_content("notes.txt", b"hello there") == ("hello there", None)


def test_extract_office_upload_returns_the_parsed_text():
    parsed = ("Sheet1\nrevenue\t42", {"extraction_success": True, "format": ".xlsx"})

    with patch("utils.document_parser.parse_document_text", return_value=parsed) as parse:
        text = extract_office_upload("budget.xlsx", _XLSX, ".xlsx")

    assert text == "Sheet1\nrevenue\t42"
    assert parse.call_args.args[0].suffix == ".xlsx", "the temp file carries the verified suffix"


def test_an_unparseable_office_upload_is_a_400():
    failed = ("", {"extraction_success": False, "extraction_error": "not a workbook"})

    with patch("utils.document_parser.parse_document_text", return_value=failed):
        with pytest.raises(HTTPException) as raised:
            extract_office_upload("budget.xlsx", _XLSX, ".xlsx")

    assert raised.value.status_code == 400
    assert "not a workbook" in raised.value.detail
