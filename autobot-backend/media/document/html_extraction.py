# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HTML into the canonical :class:`ExtractedDocument`: document text and structure only (#18826).

HTML is the third producer of the canonical model, beside PDF and DOCX in
:mod:`media.document.extraction`. It is an **allowlist**: a crawled page is stored
in AutoBot's own format, and nothing of the source site's presentation survives.

Kept, as :mod:`media.document.sections` structure: ``h1``-``h6`` headings,
``p`` paragraphs, ``ul``/``ol``/``li`` lists with nesting, ``table`` rows and
``th``/``td`` cells, ``pre`` code, ``blockquote`` quotes, ``a`` links (the
absolute target only), and ``br``/``hr`` breaks. ``strong``/``em``/``code`` and
every other inline element contribute their text and nothing else.

Dropped **with** their text: :data:`DROPPED_TAGS` (scripts, styles, JSON-LD,
embeds, form controls) and site chrome -- ``nav``, ``aside``, ``dialog``, a
page-level ``header``/``footer``, any element whose ``role`` is in
:data:`CHROME_ROLES`, and hidden elements -- the ``hidden`` attribute,
``aria-hidden="true"``, and an inline ``style`` that hides the element
(:func:`media.document.inline_style.hidden_by_style`), since text no reader sees is
a prompt-injection path, not document content. Generic containers (``div``, ``span``,
``section``, ``article``, ``main``, ...) are unwrapped to their content. No
attribute survives except a link's target and a code block's ``language-x``
class, which becomes :attr:`Block.code_language` metadata and never text.
``<main>``, else a single ``<article>``, is the content root when the page has one.

Section fields filled here: ``level``, ``heading``, ``heading_path`` (from the
heading stack) and ``blocks``; a table's ``header`` is its first ``thead`` row,
else a leading all-``th`` row. Spans stay ``None`` -- a page has no pages or timeline.

Input is capped at :data:`HTML_EXTRACT_MAX_BYTES` (UTF-8) before parsing: a longer page is
truncated at a character and tag boundary and yields its leading content, never refused.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PreformattedString, Tag

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from media.document.extraction import ExtractedDocument
from media.document.inline_style import hidden_by_style
from media.document.sections import Block, BlockKind, Link, ListItem, Section, render_sections

logger = get_logger(__name__)

#: Version of this extractor's output. Part of the web_fetch cache key (#18826), so a
#: page cached by an earlier extractor -- the markdownify path included -- is never
#: served again. Bump it whenever a change here alters the extracted text.
EXTRACTOR_VERSION = "18826-5"

#: Longest page title kept (from ``og:title`` or ``<title>``), in characters (#18826).
HTML_TITLE_MAX_CHARS = env_int_clamped("AUTOBOT_HTML_TITLE_MAX_CHARS", 300, min_v=40, max_v=4096)
#: Largest HTML input, in UTF-8 bytes, the extractor parses; a longer page is truncated first.
#: Default 10 MiB, clamped to [64 KiB, 256 MiB]. Registered in ``env_registry_rag``.
HTML_EXTRACT_MAX_BYTES = env_int_clamped(
    "AUTOBOT_HTML_EXTRACT_MAX_BYTES", 10 * 1024 * 1024, min_v=64 * 1024, max_v=256 * 1024 * 1024
)

#: Tags whose inner text is never page content: code, CSS, JSON-LD, fallbacks.
INERT_TAGS = ("script", "style", "noscript", "template")

#: Page chrome. ``header``/``footer`` count only at page level (see :func:`_is_chrome`).
CHROME_TAGS = ("nav", "header", "footer", "aside")

#: Every tag removed together with its text before the walk.
DROPPED_TAGS = INERT_TAGS + (
    "head",
    "svg",
    "math",
    "iframe",
    "object",
    "embed",
    "canvas",
    "img",
    "picture",
    "video",
    "audio",
    "map",
    "input",
    "button",
    "select",
    "textarea",
    "option",
    "optgroup",
    "datalist",
    "output",
    "progress",
    "meter",
    "label",
)

#: ARIA landmark roles that mark site chrome rather than document content.
CHROME_ROLES = frozenset({"navigation", "banner", "contentinfo", "complementary", "dialog", "alertdialog"})

_ALWAYS_CHROME = frozenset({"nav", "aside", "dialog"})
# A header/footer inside one of these belongs to that content, not to the site (HTML-AAM).
_SCOPING_TAGS = ("article", "main", "section", "aside", "nav")
_HEADINGS = {f"h{level}": level for level in range(1, 7)}
_LIST_TAGS = ("ul", "ol")
#: The one list of link schemes whose targets survive extraction (#18826). Deliberately NOT
#: configurable: a setting could re-admit ``javascript:``/``data:`` targets into KB text.
LINK_SCHEMES = frozenset({"http", "https", "mailto"})
# A code block's ``class="language-x"``; the name is bounded so no free-form attribute text survives.
#: Longest ``language-x`` class name read as a code block's language; a format bound, not a knob.
CODE_LANGUAGE_MAX_CHARS = 32
_CODE_LANGUAGE = re.compile(rf"language-([A-Za-z0-9_+#.-]{{1,{CODE_LANGUAGE_MAX_CHARS}}})")
# Elements that break a line when their text is read inline (inside a quote or a cell).
_LINE_BREAKING = frozenset({"p", "div", "li", "tr", "pre", "blockquote", "dt", "dd"}) | frozenset(_HEADINGS)
_CONTAINERS = frozenset(
    {"html", "body", "main", "article", "section", "div", "form", "fieldset", "figure", "figcaption", "details"}
    | {"summary", "dl", "dt", "dd", "address", "center", "header", "footer", "hgroup", "search", "legend"}
)


def extract_html_title(soup: Any) -> str:
    """Extract the page title from ``og:title`` or ``<title>``, at most :data:`HTML_TITLE_MAX_CHARS`."""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()[:HTML_TITLE_MAX_CHARS]
    tag = soup.find("title")
    return tag.get_text(strip=True)[:HTML_TITLE_MAX_CHARS] if tag else ""


def _is_chrome(tag: Any) -> bool:
    """Whether *tag* is site chrome or hidden, and so dropped with its text."""
    if (tag.get("role") or "").strip().lower() in CHROME_ROLES:
        return True
    if tag.get("hidden") is not None or (tag.get("aria-hidden") or "").strip().lower() == "true":
        return True
    if hidden_by_style(tag.get("style") or ""):
        return True
    if tag.name in _ALWAYS_CHROME:
        return True
    return tag.name in ("header", "footer") and tag.find_parent(_SCOPING_TAGS) is None


def drop_non_content(soup: Any) -> None:
    """Remove, in place, every element that is not document content, text included."""
    for tag in soup(list(DROPPED_TAGS)):
        tag.decompose()
    for tag in soup.find_all(_is_chrome):
        if not tag.decomposed:
            tag.decompose()


def _content_root(soup: Any) -> Any:
    """Prefer ``<main>``, then a sole ``<article>``, then ``<body>``, then the whole tree."""
    main = soup.find("main") or soup.find(attrs={"role": "main"})
    if main is not None:
        return main
    articles = soup.find_all("article")
    if len(articles) == 1:
        return articles[0]
    return soup.body or soup


def _clean(raw: str) -> str:
    """Collapse whitespace runs, keeping the line breaks a ``<br>`` produced."""
    lines = (re.sub(r"[^\S\n]+", " ", line).strip() for line in raw.split("\n"))
    return "\n".join(line for line in lines if line)


def _one_line(raw: str) -> str:
    """Clean text that must stay on a single line: headings, list items, table cells."""
    return _clean(raw).replace("\n", " ")


def _link_target(href: Any, base_url: str) -> str:
    """Resolve *href* to an absolute http(s)/mailto target, or ``""`` to drop it."""
    href = (href or "").strip() if isinstance(href, str) else ""
    if not href or href.startswith("#"):
        return ""
    resolved = urljoin(base_url, href) if base_url else href
    return resolved if urlparse(resolved).scheme.lower() in LINK_SCHEMES else ""


class _Inline:
    """Reads an element's text inline, recording the links it carries."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.links: List[Link] = []

    def text(self, node: Any, skip: Tuple[str, ...] = ()) -> str:
        """Return *node*'s visible text; tags named in *skip* contribute nothing."""
        if isinstance(node, NavigableString):
            return "" if isinstance(node, PreformattedString) else re.sub(r"\s+", " ", str(node))
        if not isinstance(node, Tag) or node.name in skip:
            return ""
        if node.name == "br":
            return "\n"
        inner = "".join(self.text(child, skip) for child in node.children)
        if node.name == "a":
            return self._link(node, inner)
        return f"\n{inner}\n" if node.name in _LINE_BREAKING else inner

    def _link(self, node: Any, inner: str) -> str:
        """Record the link's target and render it after the link text."""
        target = _link_target(node.get("href"), self.base_url)
        if not target:
            return inner
        label = _one_line(inner)
        self.links.append(Link(text=label, target=target))
        return inner if label == target else f"{inner} ({target})"


def _paragraph(node: Any, base_url: str) -> Optional[Block]:
    reader = _Inline(base_url)
    text = _clean(reader.text(node))
    return Block(kind=BlockKind.PARAGRAPH, text=text, links=tuple(reader.links)) if text else None


def _quote(node: Any, base_url: str) -> Optional[Block]:
    reader = _Inline(base_url)
    text = _clean(reader.text(node))
    return Block(kind=BlockKind.QUOTE, text=text, links=tuple(reader.links)) if text else None


def _code_language(pre: Any) -> Optional[str]:
    """The ``language-x`` class on a ``pre`` or its direct ``code`` child, else ``None``."""
    tags = [tag for tag in (pre, pre.find("code", recursive=False)) if tag is not None]
    for tag in tags:
        for name in tag.get("class") or []:
            match = _CODE_LANGUAGE.fullmatch(name)
            if match:
                return match.group(1).lower()
    return None


def _code(node: Any, base_url: str) -> Optional[Block]:
    text = node.get_text().strip("\n")
    return Block(kind=BlockKind.CODE, text=text, code_language=_code_language(node)) if text.strip() else None


def _list_items(node: Any, depth: int, reader: _Inline) -> List[ListItem]:
    """Items of the list *node*, each followed by its nested lists one level deeper."""
    items: List[ListItem] = []
    for li in node.find_all("li"):
        if li.find_parent(_LIST_TAGS) is not node:
            continue
        text = _one_line(reader.text(li, skip=_LIST_TAGS))
        if text:
            items.append(ListItem(text=text, depth=depth, ordered=node.name == "ol"))
        for sub in li.find_all(_LIST_TAGS):
            if sub.find_parent(_LIST_TAGS) is node:
                items.extend(_list_items(sub, depth + 1, reader))
    return items


def _list(node: Any, base_url: str) -> Optional[Block]:
    reader = _Inline(base_url)
    items = tuple(_list_items(node, 0, reader))
    return Block(kind=BlockKind.LIST, items=items, links=tuple(reader.links)) if items else None


def _header_index(trs: List[Any]) -> Optional[int]:
    """Index of the header row: the first ``thead`` row, else a leading row of only ``th`` cells."""
    for index, tr in enumerate(trs):
        if tr.find_parent(("thead", "tbody", "tfoot", "table")).name == "thead":
            return index
    cells = trs[0].find_all(["th", "td"], recursive=False) if trs else []
    return 0 if cells and all(cell.name == "th" for cell in cells) else None


def _table(node: Any, base_url: str) -> Optional[Block]:
    """A table's header row and body rows; rows with no non-blank cell are dropped."""
    reader = _Inline(base_url)
    trs, rows = [], []
    for tr in node.find_all("tr"):
        if tr.find_parent("table") is not node:
            continue
        cells = tuple(_one_line(reader.text(cell)) for cell in tr.find_all(["th", "td"], recursive=False))
        if any(cells):
            trs.append(tr)
            rows.append(cells)
    if not rows:
        return None
    index = _header_index(trs)
    header = rows.pop(index) if index is not None else ()
    return Block(kind=BlockKind.TABLE, header=header, rows=tuple(rows), links=tuple(reader.links))


_BLOCK_READERS: Dict[str, Callable[[Any, str], Optional[Block]]] = {
    "p": _paragraph,
    "blockquote": _quote,
    "pre": _code,
    "ul": _list,
    "ol": _list,
    "table": _table,
}


#: Tags that make an enclosing element a container to walk rather than inline text to read.
_STRUCTURAL = tuple(_HEADINGS) + tuple(_BLOCK_READERS) + ("hr",) + tuple(_CONTAINERS)


class _SectionBuilder:
    """Accumulates blocks under the current heading; loose inline text becomes a paragraph."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.sections: List[Section] = []
        self.level, self.heading = 0, ""
        # Open headings as (level, text), outermost first; the current section's path.
        self.stack: List[Tuple[int, str]] = []
        self.blocks: List[Block] = []
        self.inline = _Inline(base_url)
        self.pending: List[str] = []

    def flush(self) -> None:
        """Turn pending loose inline text into a paragraph block."""
        text = _clean("".join(self.pending))
        if text:
            self.blocks.append(Block(kind=BlockKind.PARAGRAPH, text=text, links=tuple(self.inline.links)))
        self.pending, self.inline = [], _Inline(self.base_url)

    def add(self, block: Optional[Block]) -> None:
        self.flush()
        if block is not None:
            self.blocks.append(block)

    def open_section(self, level: int, heading: str) -> None:
        """Start a section; headings at this level or deeper close, so skipped levels leave no gap."""
        self.flush()
        self._close()
        self.level, self.heading = level, heading
        self.stack = [entry for entry in self.stack if entry[0] < level]
        if heading:
            self.stack.append((level, heading))

    def _close(self) -> None:
        if self.heading or self.blocks:
            path = tuple(text for _, text in self.stack)
            section = Section(level=self.level, heading=self.heading, blocks=tuple(self.blocks), heading_path=path)
            self.sections.append(section)
        self.blocks = []

    def finish(self) -> Tuple[Section, ...]:
        self.flush()
        self._close()
        return tuple(self.sections)


def _walk(node: Any, builder: _SectionBuilder) -> None:
    """Visit *node*'s children, routing each to a heading, a block or loose text."""
    for child in node.children:
        name = child.name if isinstance(child, Tag) else None
        if name in _HEADINGS:
            builder.open_section(_HEADINGS[name], _one_line(_Inline(builder.base_url).text(child)))
        elif name in _BLOCK_READERS:
            builder.add(_BLOCK_READERS[name](child, builder.base_url))
        elif name == "hr":
            builder.flush()
        elif name in _CONTAINERS or (name is not None and child.find(_STRUCTURAL) is not None):
            # A generic container -- or an inline element such as <span> wrapping blocks -- is unwrapped.
            builder.flush()
            _walk(child, builder)
            builder.flush()
        else:
            builder.pending.append(builder.inline.text(child))


def _sections_of(root: Any, base_url: str) -> Tuple[Section, ...]:
    """Build the section tree, degrading to one flat paragraph for pathologically deep markup."""
    builder = _SectionBuilder(base_url)
    try:
        _walk(root, builder)
    except RecursionError:
        logger.warning("HTML nesting too deep for structural extraction; keeping its text only (#18826)")
        text = _clean(root.get_text("\n"))
        return (Section(level=0, heading="", blocks=(Block(kind=BlockKind.PARAGRAPH, text=text),)),) if text else ()
    return builder.finish()


def _capped(html: str, max_bytes: int) -> str:
    """*html* cut to at most *max_bytes* UTF-8 bytes, at a character and tag boundary.

    ``errors="ignore"`` drops a character the byte cut split, and a tag the cut left
    open (a ``<`` after the last ``>``) is dropped, so the parser never reads half a
    tag as text. Text after the last complete tag is kept.
    """
    if len(html) * 4 <= max_bytes:
        return html
    encoded = html.encode("utf-8")
    if len(encoded) <= max_bytes:
        return html
    head = encoded[:max_bytes].decode("utf-8", errors="ignore")
    open_tag = head.rfind("<")
    head = head[:open_tag] if open_tag > head.rfind(">") else head
    logger.warning(
        "HTML input of %d bytes exceeds AUTOBOT_HTML_EXTRACT_MAX_BYTES=%d; extracting its first %d bytes (#18826)",
        len(encoded),
        max_bytes,
        len(head.encode("utf-8")),
    )
    return head


def extract_html(html: str, base_url: str = "") -> ExtractedDocument:
    """Extract an HTML page's document text and structure into ``ExtractedDocument`` (format ``html``).

    *base_url* resolves relative link targets; without it only absolute targets survive.
    Input over :data:`HTML_EXTRACT_MAX_BYTES` is truncated before it is parsed.
    """
    soup = BeautifulSoup(_capped(html or "", HTML_EXTRACT_MAX_BYTES), "html.parser")
    title = extract_html_title(soup)
    drop_non_content(soup)
    sections = _sections_of(_content_root(soup), base_url)
    return ExtractedDocument(format="html", text=render_sections(sections), info={"title": title}, sections=sections)
