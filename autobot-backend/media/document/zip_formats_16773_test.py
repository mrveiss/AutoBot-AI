# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ZIP-based office and ODF formats are told apart by content (#16773).

Every fixture here is built with ``zipfile`` rather than committed as a binary, so what
each assertion depends on -- the member names, and the ODF ``mimetype`` member coming
first -- is visible in the test itself.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from media.document.extraction import detect_format
from media.document.zip_formats import ODF_MIMETYPES, OOXML_PARTS, sniff_zip_format


def _ooxml(path: Path, part: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(part, "<xml/>")
    return path


def _odf(path: Path, mimetype: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", mimetype)  # ODF puts this first
        archive.writestr("content.xml", "<xml/>")
    return path


@pytest.mark.parametrize("part,expected", sorted(OOXML_PARTS.items()))
def test_each_ooxml_type_is_identified_by_its_own_part(tmp_path, part, expected):
    assert sniff_zip_format(_ooxml(tmp_path / "file.bin", part)) == expected


@pytest.mark.parametrize("mimetype,expected", sorted(ODF_MIMETYPES.items()))
def test_each_odf_type_is_identified_by_its_mimetype_member(tmp_path, mimetype, expected):
    assert sniff_zip_format(_odf(tmp_path / "file.bin", mimetype)) == expected


def test_the_name_is_never_consulted(tmp_path):
    """The point of the issue: a renamed file is still what its content says."""
    renamed = _ooxml(tmp_path / "quarterly.odt", "xl/workbook.xml")

    assert sniff_zip_format(renamed) == "xlsx"


def test_bytes_and_paths_agree(tmp_path):
    path = _odf(tmp_path / "deck.bin", "application/vnd.oasis.opendocument.presentation")

    assert sniff_zip_format(path.read_bytes()) == "odp"


@pytest.mark.parametrize(
    "name,payload",
    [
        ("not-a-zip", b"just some text"),
        ("empty", b""),
        ("truncated-zip", b"PK\x03\x04 and then nothing useful"),
    ],
)
def test_unverifiable_input_returns_none_rather_than_raising(name, payload):
    """None means "cannot tell" for every cause alike; the caller falls back to the name."""
    assert sniff_zip_format(payload) is None


def test_a_plain_zip_is_not_an_office_document(tmp_path):
    path = tmp_path / "archive.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("notes.txt", "hello")

    assert sniff_zip_format(path) is None


def test_an_oversized_mimetype_member_is_not_trusted(tmp_path):
    """A crafted archive does not get to hand us an arbitrarily large "mimetype"."""
    path = _odf(tmp_path / "hostile.bin", "application/vnd.oasis.opendocument.text" + "x" * 5000)

    assert sniff_zip_format(path) is None


def test_detect_format_reports_the_verified_format_over_the_mime_type(tmp_path):
    raw = _ooxml(tmp_path / "sheet.bin", "xl/workbook.xml").read_bytes()

    assert detect_format(raw, "text/plain") == "xlsx"


def test_detect_format_still_recognises_a_truncated_docx(tmp_path):
    """The central directory has not arrived yet, so the marker sniff still carries it."""
    raw = b"PK\x03\x04" + b"\x00" * 8 + b"word/document.xml" + b"\x00" * 64

    assert sniff_zip_format(raw) is None
    assert detect_format(raw) == "docx"
