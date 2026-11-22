# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every HTML ingest entry point goes through the one extractor, with an explicit profile (#18826).

AST checks over the named entry-point files, not a tree scan: each must route page text
through ``web_fetch.profile.extract_page`` (directly, or via ``WebFetcher.page_text`` and the
Content-Type dispatch in ``web_fetch.content_types.page_from_body``) and
must not convert HTML itself. The contrast pair proves the detector sees a planted fork.
"""

import ast
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[3]

#: HTML-to-text conversions an ingest entry point must not perform on its own.
_FORBIDDEN_CALLS = frozenset({"markdownify", "md", "extract_markdown", "BeautifulSoup", "get_text"})

#: entry-point file -> (function, call it must make, keyword it must pass or None)
_ENTRY_POINTS = {
    "web_fetch/fetcher.py": ("page_text", "page_from_body", None),
    "web_fetch/content_types.py": ("page_from_body", "extract_page", None),
    "knowledge/connectors/web_crawler.py": ("_fetch_page_with_html", "page_text", None),
    "api/knowledge_crawl.py": ("crawl_url_endpoint", "crawl", "profile"),
    "api/knowledge_scrape.py": ("scrape_url", "fetch", "profile"),
    "chat_workflow/tool_handler.py": ("_exec_extract_content", "extract_page", None),
    "media/link/pipeline.py": ("_extract_document", "extract_page", None),
}


def _call_name(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _html_conversions(tree: ast.AST) -> list:
    """Names of forbidden HTML conversions called, or markdownify imports, anywhere in *tree*."""
    found = [_call_name(node) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    found = [name for name in found if name in _FORBIDDEN_CALLS]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if alias.name == "markdownify"]
        elif isinstance(node, ast.ImportFrom) and node.module == "markdownify":
            found.append("markdownify")
    return found


def _function(tree: ast.AST, name: str) -> ast.AST:
    matches = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(matches) == 1, f"expected one {name}(), found {len(matches)}"
    return matches[0]


def _calls(function: ast.AST, name: str) -> list:
    return [n for n in ast.walk(function) if isinstance(n, ast.Call) and _call_name(n) == name]


def _parse(relative: str) -> ast.AST:
    return ast.parse((_BACKEND / relative).read_text(encoding="utf-8"))


@pytest.mark.parametrize("relative", sorted(_ENTRY_POINTS))
def test_entry_point_routes_through_the_one_extractor(relative):
    function_name, required_call, required_keyword = _ENTRY_POINTS[relative]
    function = _function(_parse(relative), function_name)
    assert _html_conversions(function) == []
    calls = _calls(function, required_call)
    assert calls, f"{relative}:{function_name} no longer calls {required_call}()"
    if required_keyword:
        assert all(required_keyword in {kw.arg for kw in call.keywords} for call in calls)


@pytest.mark.parametrize(
    "relative", ["web_fetch/fetcher.py", "knowledge/connectors/web_crawler.py", "chat_workflow/tool_handler.py"]
)
def test_no_entry_point_module_imports_a_second_converter(relative):
    tree = _parse(relative)
    assert [c for c in _html_conversions(tree) if c in ("markdownify", "extract_markdown")] == []


def test_the_markdownify_conversion_is_gone_from_web_fetch():
    import web_fetch.extractors as extractors

    assert not hasattr(extractors, "extract_markdown")
    assert not hasattr(extractors, "_html_to_markdown_via_markdownify")
    assert _html_conversions(_function(_parse("web_fetch/profile.py"), "extract_page")) == []


def test_contrast_detector_flags_a_planted_fork():
    planted = ast.parse(
        "import markdownify\n"
        "def f(html):\n"
        "    soup = BeautifulSoup(html, 'html.parser')\n"
        "    return markdownify.markdownify(html), soup.get_text(), extract_markdown(html)\n"
    )
    assert sorted(_html_conversions(planted)) == sorted(
        ["markdownify", "markdownify", "BeautifulSoup", "get_text", "extract_markdown"]
    )
    clean = ast.parse("def f(html):\n    return extract_page(html, IngestProfile.DOCUMENT).text\n")
    assert _html_conversions(clean) == []
