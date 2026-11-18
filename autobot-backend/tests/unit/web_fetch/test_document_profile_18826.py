# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``document`` profile keeps a page's text and structure, nothing of its presentation (#18826).

The fixture is an excerpt of an AutoBot report (``tests/fixtures/kb_ingest_18826/document.md``):
a heading hierarchy, right-aligned tables, nested bullet lists, bold, a code block and a
relative link. ``page.html`` is that markdown rendered to HTML and wrapped in heavy site
chrome; every chrome string carries ``MARKER``. Expectations are derived from the
markdown, so the test asserts the extractor reproduces the source document.
"""

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from media.document.extraction import ExtractedDocument
from media.document.sections import BlockKind
from web_fetch.profile import (
    IngestProfile,
    ProfileNotImplementedError,
    extract_page,
    require_implemented,
    resolve_profile,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "kb_ingest_18826"
_PAGE_URL = "https://docs.example.org/reports/bugs-root-causes.html"
_TITLE = "AutoBot-AI: open bug & tech-debt issues, root-cause map"


def _source_md() -> str:
    return (_FIXTURES / "document.md").read_text(encoding="utf-8")


def _page_html() -> str:
    return (_FIXTURES / "page.html").read_text(encoding="utf-8")


def _plain(markdown: str) -> str:
    """Markdown inline text with emphasis and code markers removed."""
    return re.sub(r"\s+", " ", markdown.replace("**", "").replace("`", "")).strip()


def _md_tables(markdown: str):
    """Each markdown table as a tuple of rows of plain cell text, separator rows skipped."""
    tables, current = [], []
    for line in markdown.splitlines() + [""]:
        if line.startswith("|"):
            if not re.fullmatch(r"[|:\- ]+", line):
                current.append(tuple(_plain(cell) for cell in line.strip().strip("|").split("|")))
        elif current:
            tables.append(tuple(current))
            current = []
    return tables


def _md_list_items(markdown: str):
    """``(depth, text)`` for every bullet; four spaces of indent is one level."""
    items = []
    for line in markdown.splitlines():
        match = re.match(r"^( *)- (.*)$", line)
        if match:
            items.append((len(match.group(1)) // 4, _plain(match.group(2))))
    return items


@pytest.fixture(scope="module")
def document() -> ExtractedDocument:
    return extract_page(_page_html(), IngestProfile.DOCUMENT, base_url=_PAGE_URL)


def _blocks(document, kind):
    return [block for section in document.sections for block in section.blocks if block.kind is kind]


class TestCanonicalModel:
    def test_output_is_an_extracted_document_of_format_html(self, document) -> None:
        assert isinstance(document, ExtractedDocument)
        assert document.format == "html"
        assert document.info["title"] == _TITLE
        assert document.has_usable_content

    def test_heading_levels_and_texts_match_the_source_in_order(self, document) -> None:
        expected = [(1, _TITLE)] + [
            (len(m.group(1)), m.group(2)) for m in re.finditer(r"^(#{1,6}) (.+)$", _source_md(), re.MULTILINE)
        ]
        assert [(s.level, s.heading) for s in document.sections if s.heading] == expected

    def test_heading_path_is_the_ancestor_chain_ending_in_the_own_heading(self, document) -> None:
        summary = "1. Executive summary"
        assert [s.heading_path for s in document.sections if s.heading] == [
            (_TITLE,),
            (_TITLE, "0. Data collection and exact counts"),
            (_TITLE, summary),
            (_TITLE, summary, "1.1 Top 10 root causes, ranked by issues likely closed ÷ effort"),
        ]
        assert all(s.span is None for s in document.sections)

    def test_tables_keep_every_row_and_cell_with_the_header_split_from_the_body(self, document) -> None:
        expected = _md_tables(_source_md())
        tables = _blocks(document, BlockKind.TABLE)
        assert len(expected) == len(tables) == 2
        assert [block.header for block in tables] == [table[0] for table in expected]
        assert tables[0].header == ("Label", "Open issues")
        assert [block.rows for block in tables] == [table[1:] for table in expected]
        assert "Label | Open issues\nbug | 578" in document.text
        assert "Union (distinct issues analysed) | 937" in document.text

    def test_list_items_keep_text_and_nesting(self, document) -> None:
        items = [(item.depth, item.text) for block in _blocks(document, BlockKind.LIST) for item in block.items]
        assert items == _md_list_items(_source_md())
        assert any(depth == 1 for depth, _ in items)

    def test_code_block_is_kept_verbatim(self, document) -> None:
        code = _blocks(document, BlockKind.CODE)
        assert [block.text for block in code] == [
            "GET /repos/mrveiss/AutoBot-AI/issues?labels=<label>&state=open&per_page=100&page=N"
        ]
        assert [block.code_language for block in code] == ["text"]
        assert "language" not in document.text

    def test_links_keep_their_absolute_target(self, document) -> None:
        links = [link for section in document.sections for block in section.blocks for link in block.links]
        target = "https://docs.example.org/reports/dedup-defork-report.md"
        assert [(link.text, link.target) for link in links] == [("dedup-defork-report.md", target)]
        assert f"dedup-defork-report.md ({target})" in document.text

    def test_bold_survives_as_plain_text(self, document) -> None:
        assert "937 open issues were classified." in document.text
        assert "**" not in document.text and "<strong>" not in document.text


def _all_strings(document) -> str:
    """Everything the extraction carries: rendered text plus every section field."""
    return document.text + "\n" + repr(document.sections)


class TestNothingForeignSurvives:
    def test_no_chrome_script_style_or_json_ld_text(self, document) -> None:
        carried = _all_strings(document)
        assert sorted(set(re.findall(r"[A-Z_-]*MARKER", carried))) == []
        for foreign in ("schema.org", "@context", "font-family", "we use cookies", "copyright"):
            assert foreign not in carried

    def test_no_attribute_value_survives_except_link_targets(self, document) -> None:
        soup = BeautifulSoup(_page_html(), "html.parser")
        values = {
            value if isinstance(value, str) else " ".join(value)
            for tag in soup.find_all(True)
            for name, value in tag.attrs.items()
            if name != "href"
        }
        source = _source_md()
        distinctive = sorted(v for v in values if v and v not in source)
        assert "text-align: right;" in distinctive and "language-text" in distinctive
        leaked = [value for value in distinctive if value in _all_strings(document)]
        assert leaked == []

    def test_no_markup_reaches_the_text(self, document) -> None:
        """Only tag-like text the document itself contains survives (its code shows ``<label>``)."""
        tags = re.compile(r"</?([a-z][a-z0-9]*)[\s>/]")
        assert set(tags.findall(document.text)) == set(tags.findall(_source_md())) == {"label"}


class TestStructuralRules:
    def test_page_level_header_and_footer_drop_but_an_article_header_stays(self) -> None:
        html = (
            "<body><header>SITE-HEAD</header><article><header><h1>Kept title</h1></header>"
            "<p>Body.</p><footer>Article footnote.</footer></article><footer>SITE-FOOT</footer></body>"
        )
        document = extract_page(html, IngestProfile.DOCUMENT)
        assert document.sections[0].heading == "Kept title"
        assert "Article footnote." in document.text
        assert "SITE-" not in document.text

    def test_body_is_the_root_when_there_is_no_main_or_single_article(self) -> None:
        html = "<body><nav>MENU</nav><article><p>One.</p></article><article><p>Two.</p></article></body>"
        assert extract_page(html, IngestProfile.DOCUMENT).text == "One.\n\nTwo."

    def test_unsafe_and_fragment_links_keep_text_but_no_target(self) -> None:
        html = '<p><a href="javascript:alert(1)">run</a> <a href="#top">top</a> <a href="/x">rel</a></p>'
        document = extract_page(html, IngestProfile.DOCUMENT)
        assert document.text == "run top rel"
        assert document.sections[0].blocks[0].links == ()

    def test_pathologically_deep_markup_keeps_its_text(self) -> None:
        html = "<div>" * 3000 + "deep text" + "</div>" * 3000
        assert extract_page(html, IngestProfile.DOCUMENT).text == "deep text"


class TestProfileSeam:
    def test_document_is_the_default_everywhere(self) -> None:
        import inspect

        from knowledge.connectors.web_crawler import WebCrawlerConnector
        from web_fetch.fetcher import WebFetcher

        for function in (WebFetcher.fetch, WebFetcher.__init__, WebCrawlerConnector.crawl):
            assert inspect.signature(function).parameters["profile"].default is IngestProfile.DOCUMENT
        assert WebFetcher().profile is IngestProfile.DOCUMENT

    def test_extract_page_requires_a_profile_argument(self) -> None:
        with pytest.raises(TypeError):
            extract_page("<p>x</p>")  # type: ignore[call-arg]

    @pytest.mark.parametrize("value", ["", "Document", "markdown", "raw", None])
    def test_unknown_profile_is_rejected_never_treated_as_document(self, value) -> None:
        with pytest.raises(ValueError, match="unknown ingest profile"):
            resolve_profile(value)
        with pytest.raises(ValueError):
            extract_page("<p>x</p>", value)

    @pytest.mark.parametrize("value", ["media", "page_copy", IngestProfile.MEDIA, IngestProfile.PAGE_COPY])
    def test_listed_but_unimplemented_profiles_refuse(self, value) -> None:
        with pytest.raises(ProfileNotImplementedError, match="not implemented"):
            require_implemented(value)

    def test_fetcher_refuses_an_unimplemented_profile_before_any_fetch(self) -> None:
        from web_fetch.fetcher import WebFetcher

        with pytest.raises(ProfileNotImplementedError):
            WebFetcher(profile=IngestProfile.MEDIA)
        with pytest.raises(ValueError):
            WebFetcher(profile="bogus")

    def test_connector_refuses_an_unknown_profile_at_construction(self) -> None:
        from knowledge.connectors.models import ConnectorConfig
        from knowledge.connectors.web_crawler import WebCrawlerConnector

        config = ConnectorConfig(
            connector_id="c", connector_type="web_crawler", name="c", config={"urls": [], "profile": "bogus"}
        )
        with pytest.raises(ValueError, match="unknown ingest profile"):
            WebCrawlerConnector(config)
