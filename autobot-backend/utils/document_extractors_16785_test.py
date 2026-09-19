# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for DocumentExtractor's .csv/.json/.html support (#16785).

Before this fix, DocumentExtractor.extract_from_file() raised "Unsupported
file type" for these three formats while api.knowledge's GUI upload path
(_extract_file_content) ingested them -- same file, two divergent outcomes
depending on which route it arrived through. Every test here drives both
routes on identical bytes and asserts they agree, since that agreement is
the whole point of the fix (not just "no longer raises").
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.knowledge import _extract_file_content
from utils.document_extractors import DocumentExtractor


@pytest.mark.asyncio
async def test_csv_no_longer_raises_and_matches_upload_path(tmp_path: Path):
    content = b"name,age\nAda,36\nGrace,85\n"
    file_path = tmp_path / "data.csv"
    file_path.write_bytes(content)

    extractor_text = await DocumentExtractor.extract_from_file(file_path)
    upload_text, extracted = _extract_file_content("data.csv", content)

    assert extracted is None
    assert extractor_text == upload_text == content.decode("utf-8")


@pytest.mark.asyncio
async def test_json_reserialised_with_indent_matches_upload_path(tmp_path: Path):
    content = b'{"b": 2, "a": [1, 2, 3]}'
    file_path = tmp_path / "data.json"
    file_path.write_bytes(content)

    extractor_text = await DocumentExtractor.extract_from_json(file_path)
    upload_text, extracted = _extract_file_content("data.json", content)

    assert extracted is None
    assert extractor_text == upload_text
    assert extractor_text == '{\n  "b": 2,\n  "a": [\n    1,\n    2,\n    3\n  ]\n}'


@pytest.mark.asyncio
async def test_invalid_json_falls_back_to_raw_text_matching_upload_path(tmp_path: Path):
    content = b"{not valid json"
    file_path = tmp_path / "broken.json"
    file_path.write_bytes(content)

    extractor_text = await DocumentExtractor.extract_from_json(file_path)
    upload_text, _ = _extract_file_content("broken.json", content)

    assert extractor_text == upload_text == "{not valid json"


@pytest.mark.asyncio
async def test_html_sanitised_via_the_shared_sanitiser_matches_upload_path(tmp_path: Path):
    content = b"<html><head><title>T</title></head><body><script>alert(1)</script><p>Hello</p></body></html>"
    file_path = tmp_path / "page.html"
    file_path.write_bytes(content)

    extractor_text = await DocumentExtractor.extract_from_html(file_path)
    upload_text, extracted = _extract_file_content("page.html", content)

    assert extracted is None
    assert extractor_text == upload_text
    # #16785: the shared sanitiser strips script content -- a local
    # reimplementation that merely stripped tags would leave "alert(1)" in.
    assert "alert(1)" not in extractor_text
    assert "Hello" in extractor_text


@pytest.mark.asyncio
async def test_extract_from_file_dispatches_all_three_new_formats(tmp_path: Path):
    csv_path = tmp_path / "d.csv"
    csv_path.write_bytes(b"a,b\n1,2\n")
    json_path = tmp_path / "d.json"
    json_path.write_bytes(b'{"x": 1}')
    html_path = tmp_path / "d.html"
    html_path.write_bytes(b"<p>hi</p>")

    assert await DocumentExtractor.extract_from_file(csv_path) == "a,b\n1,2\n"
    assert await DocumentExtractor.extract_from_file(json_path) == '{\n  "x": 1\n}'
    assert "hi" in await DocumentExtractor.extract_from_file(html_path)


def test_get_supported_extensions_reports_the_three_new_formats():
    extensions = DocumentExtractor.get_supported_extensions()
    assert ".csv" in extensions
    assert ".json" in extensions
    assert ".html" in extensions


def test_is_supported_format_reports_the_three_new_formats():
    assert DocumentExtractor.is_supported_format("report.csv")
    assert DocumentExtractor.is_supported_format("data.json")
    assert DocumentExtractor.is_supported_format("page.html")
