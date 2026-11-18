# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Link ingest stores a page's document text through the one HTML extractor (#18826)."""

from media.link.pipeline import LinkPipeline
from web_fetch.profile import IngestProfile, extract_page

_URL = "https://test.com/page"
_CHROME_PAGE = (
    '<html><head><meta property="og:title" content="OG Title">'
    '<script type="application/ld+json">{"@context": "https://schema.org", "name": "LD-MARK"}</script>'
    "<style>.CSS-MARK{}</style></head><body><header>HEAD-MARK</header><nav><a href='/menu'>NAV-MARK</a></nav>"
    '<main><h1>Guide</h1><p class="CLASS-MARK">Read the <a href="/docs">docs</a>.</p>'
    "<ul><li>first</li><li>second</li></ul><script>SCRIPT-MARK()</script></main>"
    "<aside>ASIDE-MARK</aside><footer><a href='/legal'>FOOT-MARK</a></footer>"
    '<div role="contentinfo">ROLE-MARK</div></body></html>'
)


def test_link_page_stores_document_only_text():
    result = LinkPipeline()._parse_html(_CHROME_PAGE, _URL, "text/html", {})
    assert result["content"] == "Guide\n\nRead the docs (https://test.com/docs).\n\n- first\n- second"
    assert "MARK" not in result["content"] and "schema.org" not in result["content"]


def test_link_metadata_and_content_links_are_kept_chrome_links_are_not():
    result = LinkPipeline()._parse_html(_CHROME_PAGE, _URL, "text/html", {})
    assert result["title"] == "OG Title" and result["open_graph"] == {"title": "OG Title"}
    assert [link["url"] for link in result["links"]] == ["https://test.com/docs"]


def test_stored_content_is_exactly_the_document_profile_text():
    result = LinkPipeline()._parse_html(_CHROME_PAGE, _URL, "text/html", {})
    assert result["content"] == extract_page(_CHROME_PAGE, IngestProfile.DOCUMENT, base_url=_URL).text
