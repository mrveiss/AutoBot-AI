# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The HTML producer fills the cross-source section contract: heading path, table header, code language (#18826)."""

from media.document.html_extraction import extract_html
from media.document.sections import BlockKind


def _tables(document):
    return [block for section in document.sections for block in section.blocks if block.kind is BlockKind.TABLE]


def test_heading_path_follows_nesting_and_closes_deeper_headings():
    html = "<h1>A</h1><p>a</p><h2>B</h2><p>b</p><h3>C</h3><p>c</p><h2>D</h2><p>d</p><h1>E</h1><p>e</p>"
    paths = [s.heading_path for s in extract_html(html).sections]
    assert paths == [("A",), ("A", "B"), ("A", "B", "C"), ("A", "D"), ("E",)]


def test_heading_path_with_a_skipped_level_holds_only_the_headings_present():
    html = "<h1>Top</h1><h3>Deep</h3><p>x</p><h2>Mid</h2><p>y</p><h3>Under mid</h3><p>z</p>"
    sections = extract_html(html).sections
    assert [(s.level, s.heading_path) for s in sections] == [
        (1, ("Top",)),
        (3, ("Top", "Deep")),
        (2, ("Top", "Mid")),
        (3, ("Top", "Mid", "Under mid")),
    ]


def test_content_before_the_first_heading_has_an_empty_path_and_no_span():
    sections = extract_html("<p>Preamble.</p><h2>First</h2><p>Body.</p>").sections
    assert [(s.level, s.heading, s.heading_path) for s in sections] == [(0, "", ()), (2, "First", ("First",))]
    assert all(s.span is None and all(b.span is None for b in s.blocks) for s in sections)


def test_thead_row_becomes_the_header_and_tbody_rows_the_body():
    html = (
        "<table><thead><tr><th>Label</th><th>Count</th></tr></thead>"
        "<tbody><tr><td>bug</td><td>578</td></tr><tr><td>cleanup</td><td>9</td></tr></tbody></table>"
    )
    document = extract_html(html)
    (table,) = _tables(document)
    assert table.header == ("Label", "Count")
    assert table.rows == (("bug", "578"), ("cleanup", "9"))
    assert document.text == "Label | Count\nbug | 578\ncleanup | 9"


def test_a_leading_all_th_row_becomes_the_header_without_a_thead():
    html = "<table><tr><th>Name</th><th>Role</th></tr><tr><td>Ann</td><td>owner</td></tr></table>"
    document = extract_html(html)
    (table,) = _tables(document)
    assert table.header == ("Name", "Role")
    assert table.rows == (("Ann", "owner"),)
    assert document.text == "Name | Role\nAnn | owner"


def test_a_table_without_header_cells_keeps_every_row_in_the_body():
    html = "<table><tr><th>Row</th><td>1</td></tr><tr><td>a</td><td>b</td></tr></table>"
    (table,) = _tables(extract_html(html))
    assert table.header == ()
    assert table.rows == (("Row", "1"), ("a", "b"))


def test_code_language_is_read_from_the_class_and_kept_out_of_the_text():
    html = '<pre><code class="hljs language-Python">print(1)</code></pre><pre class="language-sh">ls</pre><pre>x</pre>'
    document = extract_html(html)
    code = [b for s in document.sections for b in s.blocks if b.kind is BlockKind.CODE]
    assert [(b.text, b.code_language) for b in code] == [("print(1)", "python"), ("ls", "sh"), ("x", None)]
    assert "language" not in document.text and "hljs" not in document.text
