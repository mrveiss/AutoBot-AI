# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Page-provenance guards (#13894).

The KB upload path stored PDF text carrying ``## Page N`` markers, which then went
straight into the embedding. Those markers are *structure*, not meaning: they
compete with the document's own words for similarity, and they are a poor way to
answer "which page did this fact come from" — recovering a page number by parsing
markers back out of retrieved text is fragile the moment a chunker splits between
a marker and its page.

Provenance now travels as character spans in fact metadata, with the stored text
marker-free. These tests pin the invariant that makes that safe: **the offsets
must index the exact string that was stored.**
"""

import io

import pytest

from media.document.extraction import (
    PAGE_SEPARATOR,
    PageSpan,
    PageText,
    chunk_page_map,
    extract_pdf,
    page_for_offset,
    pages_for_span,
    render_pages,
    render_plain,
)


def _pdf(pages: list) -> bytes:
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in pages:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# The invariant everything else rests on
# ---------------------------------------------------------------------------


def test_spans_index_the_exact_text_that_was_rendered():
    """If offsets and text ever disagree, every citation silently points elsewhere."""
    pages = (PageText(1, "alpha content"), PageText(2, "beta content"), PageText(3, "gamma"))
    text, spans = render_plain(pages)

    for span, page in zip(spans, pages):
        assert text[span.start : span.end] == page.text


def test_spans_still_index_correctly_when_pages_are_skipped():
    """Empty pages are dropped from the text; the surviving offsets must still land."""
    pages = (PageText(1, "first"), PageText(2, "   "), PageText(3, "third"))
    text, spans = render_plain(pages)

    assert [span.number for span in spans] == [1, 3], "page 2 carried nothing"
    for span in spans:
        assert text[span.start : span.end].strip()
    assert text[spans[1].start : spans[1].end] == "third"


def test_rendered_text_carries_no_markers():
    text, _spans = render_plain((PageText(1, "body"), PageText(2, "more")))
    assert "## Page" not in text
    # ...whereas the marker renderer still does, for callers that want it.
    assert "## Page 1" in render_pages((PageText(1, "body"),))


def test_plain_and_marker_renderings_cover_the_same_pages():
    """The two renderers must not disagree about which pages exist."""
    pages = (PageText(1, "a"), PageText(2, "  "), PageText(3, "c"))
    _plain, spans = render_plain(pages)
    marked = render_pages(pages)

    for span in spans:
        assert f"## Page {span.number}" in marked
    assert "## Page 2" not in marked


# ---------------------------------------------------------------------------
# Offset -> page resolution
# ---------------------------------------------------------------------------


def test_page_for_offset_resolves_within_each_page():
    text, spans = render_plain((PageText(1, "aaaa"), PageText(2, "bbbb")))

    assert page_for_offset(spans, 0) == 1
    assert page_for_offset(spans, 3) == 1
    assert page_for_offset(spans, text.index("bbbb")) == 2


def test_offset_in_the_separator_belongs_to_no_page():
    """A guess here would fabricate a citation; None lets the caller decide."""
    _text, spans = render_plain((PageText(1, "aa"), PageText(2, "bb")))
    separator_offset = spans[0].end
    assert page_for_offset(spans, separator_offset) is None


def test_offset_past_the_end_is_not_attributed():
    _text, spans = render_plain((PageText(1, "aa"),))
    assert page_for_offset(spans, 999) is None


def test_span_crossing_a_page_break_reports_both_pages():
    """Reporting only the first would mis-cite half the chunk's content."""
    text, spans = render_plain((PageText(1, "first"), PageText(2, "second")))
    assert pages_for_span(spans, 0, len(text)) == (1, 2)


def test_empty_span_reports_nothing():
    _text, spans = render_plain((PageText(1, "x"),))
    assert pages_for_span(spans, 3, 3) == ()
    assert pages_for_span(spans, 5, 2) == ()


# ---------------------------------------------------------------------------
# Chunk mapping
# ---------------------------------------------------------------------------


def test_chunks_map_back_to_their_pages():
    text, spans = render_plain((PageText(1, "alpha"), PageText(2, "beta"), PageText(3, "gamma")))
    chunks = ["alpha", "beta", "gamma"]

    assert chunk_page_map(spans, chunks, text) == ((1,), (2,), (3,))


def test_identical_boilerplate_does_not_collapse_onto_the_first_page():
    """A find() from zero attributes every recurring header to page 1.

    The chunks here are byte-identical, which is the case that actually
    distinguishes a forward-scanning cursor from a naive search — an earlier
    version of this test used *similar* chunks and passed against the bug.
    """
    header = "CONFIDENTIAL"
    text, spans = render_plain((PageText(1, header), PageText(2, header), PageText(3, header)))

    assert chunk_page_map(spans, [header, header, header], text) == ((1,), (2,), (3,))


def test_a_chunk_the_chunker_rewrote_reports_no_page_rather_than_a_wrong_one():
    text, spans = render_plain((PageText(1, "original text"),))
    assert chunk_page_map(spans, ["text the chunker invented"], text) == ((),)


def test_chunk_spanning_a_break_reports_both_pages():
    text, spans = render_plain((PageText(1, "aaa"), PageText(2, "bbb")))
    whole = text  # one chunk covering everything, separator included
    assert chunk_page_map(spans, [whole], text) == ((1, 2),)


# ---------------------------------------------------------------------------
# End to end, through the real extractor and the upload metadata helper
# ---------------------------------------------------------------------------


def test_real_pdf_offsets_resolve_to_the_right_pages():
    extracted = extract_pdf(_pdf(["page one body", "page two body", "page three body"]))
    text, spans = render_plain(extracted.pages)

    for span in spans:
        recovered = text[span.start : span.end]
        assert f"page {['one', 'two', 'three'][span.number - 1]}" in recovered


def test_upload_metadata_offsets_index_the_stored_content():
    """The end-to-end invariant: metadata offsets must match what was stored."""
    from api.knowledge import _extract_file_content, _page_provenance_metadata

    raw = _pdf(["alpha page", "beta page"])
    stored_content, extracted = _extract_file_content("doc.pdf", raw)
    metadata = _page_provenance_metadata(extracted)

    assert metadata["page_count"] == 2
    assert metadata["pages_with_text"] == [1, 2]
    for entry in metadata["page_spans"]:
        recovered = stored_content[entry["start"] : entry["end"]]
        assert recovered.strip(), "a stored span must resolve to real text"
        assert "## Page" not in recovered


def test_stored_upload_content_has_no_page_markers():
    from api.knowledge import _extract_file_content

    stored_content, _extracted = _extract_file_content("doc.pdf", _pdf(["body one", "body two"]))
    assert "## Page" not in stored_content
    assert "body one" in stored_content


def test_unpaginated_formats_get_no_fabricated_page_metadata():
    """A DOCX has no pages; `page: 1` would be an invented citation."""
    from api.knowledge import _page_provenance_metadata
    from media.document.extraction import ExtractedDocument

    assert _page_provenance_metadata(ExtractedDocument(format="docx", text="content")) == {}
    assert _page_provenance_metadata(None) == {}


def test_span_metadata_round_trips():
    span = PageSpan(number=7, start=10, end=25)
    assert span.as_metadata() == {"page": 7, "start": 10, "end": 25}


def test_separator_is_shared_so_offsets_are_reproducible():
    """Offsets are stored; a renderer that changed its separator would break them."""
    text, spans = render_plain((PageText(1, "a"), PageText(2, "b")), separator=PAGE_SEPARATOR)
    assert text == f"a{PAGE_SEPARATOR}b"
    assert spans[1].start == 1 + len(PAGE_SEPARATOR)
