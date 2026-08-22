# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PDF table extraction guards (#14232).

#13895 made table support *honest*: a PDF result carried ``tables_attempted:
false``, so a consumer could tell "this document has no tables" from "we never
looked". This is the other half — actually looking.

The split mirrors #13896: contract tests run everywhere and pin the degradation
behaviour, while extraction tests skip where pdfplumber is absent rather than
passing vacuously. A gate that is always closed is indistinguishable from a
passing suite, which is how #13885 survived months — so there is also a guard
asserting the CI runner actually has the library.
"""

import io
import os

import pytest

from media.document.extraction import extract_pdf

try:
    import pdfplumber as _pdfplumber
except ImportError:  # pragma: no cover - the point of the guard below
    _pdfplumber = None

_HAS_PDFPLUMBER = _pdfplumber is not None
needs_pdfplumber = pytest.mark.skipif(not _HAS_PDFPLUMBER, reason="pdfplumber is not installed")


def _pdf_with_table(rows: list) -> bytes:
    """A PDF carrying a real ruled table, drawn as a reportlab Table flowable."""
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    table = Table(rows)
    # Ruled grid: pdfplumber's default strategy finds tables by their lines, so
    # an unruled layout would be a fixture that tests nothing.
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    doc.build([table])
    return buffer.getvalue()


def _pdf_prose_only(text: str) -> bytes:
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.drawString(72, 700, " Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# The distinction #13895 introduced must survive
# ---------------------------------------------------------------------------


@needs_pdfplumber
def test_a_pdf_with_no_tables_reports_that_it_looked():
    """`([], True)` is the answer that was impossible before #13895 + this."""
    extracted = extract_pdf(_pdf_prose_only("just prose here"))

    assert extracted.tables == ()
    assert extracted.tables_attempted is True, "an empty result must be distinguishable from an unattempted one"


def test_a_missing_library_reports_that_it_did_not_look(monkeypatch):
    """Degrade, never raise: a readable text layer must not be lost to a missing wheel."""
    import builtins

    real_import = builtins.__import__

    def _no_pdfplumber(name, *args, **kwargs):
        if name == "pdfplumber":
            raise ImportError("simulated: pdfplumber absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_pdfplumber)

    extracted = extract_pdf(_pdf_prose_only("prose survives"))

    assert extracted.tables == ()
    assert extracted.tables_attempted is False
    assert "prose survives" in extracted.text, "text extraction must be unaffected"


def test_a_failing_detector_reports_not_attempted_rather_than_raising():
    """Table detection tripping must not fail an otherwise-good extraction.

    Asserted on the helper directly: it is the unit that owns the decision, and
    driving it through extract_pdf would need a PDF that parses for pypdf and
    breaks pdfplumber, which is a fixture that tests the fixture.
    """
    from media.document.extraction import _pdf_tables

    assert _pdf_tables(b"definitely not a pdf") == ((), False)


@needs_pdfplumber
def test_text_extraction_is_unaffected_by_table_detection():
    """The text layer is the primary product; tables are additive."""
    extracted = extract_pdf(_pdf_prose_only("prose survives"))
    assert "prose survives" in extracted.text


# ---------------------------------------------------------------------------
# Real extraction
# ---------------------------------------------------------------------------


@needs_pdfplumber
def test_a_ruled_table_is_extracted():
    rows = [["Item", "Qty"], ["Widget", "7"], ["Gadget", "12"]]
    extracted = extract_pdf(_pdf_with_table(rows))

    assert extracted.tables_attempted is True
    assert extracted.tables, "a ruled table must be found"

    flat = [cell for table in extracted.tables for row in table for cell in row]
    assert "Widget" in flat
    assert "12" in flat


@needs_pdfplumber
def test_table_shape_matches_the_docx_shape():
    """One parser for both formats, not a branch on where the table came from."""
    extracted = extract_pdf(_pdf_with_table([["a", "b"], ["c", "d"]]))
    table = extracted.tables[0]

    assert isinstance(table, list)
    assert all(isinstance(row, list) for row in table)
    assert all(isinstance(cell, str) for row in table for cell in row)


@needs_pdfplumber
def test_empty_cells_become_empty_strings_not_none():
    """pdfplumber yields None where python-docx yields ''; consumers see one shape."""
    extracted = extract_pdf(_pdf_with_table([["h1", "h2"], ["only", ""]]))
    cells = [cell for table in extracted.tables for row in table for cell in row]

    assert all(cell is not None for cell in cells)
    assert all(isinstance(cell, str) for cell in cells)


# ---------------------------------------------------------------------------
# The skip must not become permanent
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("CI"), reason="asserts the CI runner's provisioning, not a developer's")
def test_ci_actually_has_pdfplumber():
    """Everything above is skipif-gated; an always-closed gate reads as a pass.

    pytesseract was declared in autobot-backend/requirements.txt by #13885 and
    never reached a CI runner, because CI installs requirements-ci/* instead.
    This fails loudly if pdfplumber goes the same way.
    """
    assert _HAS_PDFPLUMBER, (
        "pdfplumber missing on the CI runner, so the table-extraction tests are skipping. "
        "It must be declared in requirements-ci/document.txt as well as autobot-backend/requirements.txt."
    )
