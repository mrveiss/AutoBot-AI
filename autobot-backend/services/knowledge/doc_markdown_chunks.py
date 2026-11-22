# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Markdown parsing and chunking for the doc indexer, split out of doc_indexer.py (#20886)."""

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from autobot_shared.doc_chunking import chunk_large_content as _chunk_large_content
from autobot_shared.doc_chunking import chunk_plain_text
from autobot_shared.doc_chunking import create_chunk as _create_chunk
from autobot_shared.doc_chunking import estimate_tokens as _estimate_tokens
from autobot_shared.doc_chunking import process_h2_sections as _process_h2_sections
from autobot_shared.frontmatter import split_frontmatter
from autobot_shared.logging_manager import get_logger
from autobot_shared.slug import sanitize_token

logger = get_logger(__name__)

# ============================================================================
# MARKDOWN PARSING (extracted from CLI tool)
# ============================================================================


def _extract_title(content: str) -> str:
    """Extract title from first H1 header or first line."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:100]
    return "Untitled Document"


def _infer_doc_type(file_path: str) -> str:
    """Infer document type from file path."""
    path_lower = file_path.lower()
    type_keywords = [
        (["api"], "api"),
        (["architecture"], "architecture"),
        (["developer", "setup"], "developer"),
        (["security"], "security"),
        (["troubleshoot"], "troubleshooting"),
        (["deploy", "docker"], "deployment"),
        (["test"], "testing"),
        (["feature"], "feature"),
        (["workflow"], "workflow"),
        (["agent"], "agent_system"),
        (["claude.md"], "project_rules"),
        (["user-guide", "install"], "user_guide"),
    ]
    for keywords, doc_type in type_keywords:
        if any(kw in path_lower for kw in keywords):
            return doc_type
    return "documentation"


def _infer_category(file_path: str) -> str:
    """Infer category from file path."""
    parts = Path(file_path).parts
    try:
        docs_idx = parts.index("docs")
        if len(parts) > docs_idx + 1:
            return parts[docs_idx + 1]
    except ValueError:
        pass
    if file_path.endswith("CLAUDE.md"):
        return "project_rules"
    return "general"


def _extract_tags(content: str, file_path: str) -> List[str]:
    """Extract relevant tags from content and path."""
    tags = set()
    for part in Path(file_path).parts:
        if part not in [
            ".",
            "..",
            "docs",
            "home",
            "kali",
            "Desktop",
            "AutoBot",
            "opt",
            "autobot",
        ]:
            if len(tag := sanitize_token(part, allowed="a-zA-Z0-9_-", replacement="", case="lower")) > 2:
                tags.add(tag)

    keywords = [
        "api",
        "deployment",
        "docker",
        "kubernetes",
        "redis",
        "chromadb",
        "websocket",
        "authentication",
        "security",
        "multimodal",
        "llm",
        "agent",
        "workflow",
        "terminal",
        "frontend",
        "backend",
        "npm",
        "vue",
        "fastapi",
        "python",
        "typescript",
        "install",
        "setup",
    ]
    content_lower = content.lower()
    for keyword in keywords:
        if keyword in content_lower:
            tags.add(keyword)

    return list(tags)[:15]


def _parse_frontmatter(content: str) -> Tuple[str, List[str], List[str]]:
    """Strip Obsidian YAML frontmatter and return (body, tags, aliases).

    Recognises a leading ``---`` block. Returns the content after the closing
    ``---`` together with any ``tags`` and ``aliases`` values found inside it.
    If no frontmatter is present the original content is returned unchanged
    with empty tag and alias lists.

    #18093: an EIGHTH fence variant, invisible to the regex-by-concept guard because it
    used no regex -- `startswith("---")` plus `find("\n---", 3)` -- and it leaked `\r`
    on CRLF and accepted `---yaml` as a fence. Key scanning below is unchanged.
    """
    fm_block, body = split_frontmatter(content)
    if fm_block is None:
        return content, [], []
    body = body.lstrip("\n")  # preserved: blank lines after the fence are not body

    fm_tags: List[str] = []
    fm_aliases: List[str] = []

    # Parse simple YAML list values for 'tags' and 'aliases' keys.
    current_key: str | None = None
    for line in fm_block.splitlines():
        key_match = re.match(r"^(\w+)\s*:", line)
        if key_match:
            current_key = key_match.group(1)
            inline = line[key_match.end() :].strip()
            if inline and current_key in ("tags", "aliases"):
                target = fm_tags if current_key == "tags" else fm_aliases
                target.append(inline.lstrip("- ").strip())
        elif line.strip().startswith("-") and current_key in ("tags", "aliases"):
            target = fm_tags if current_key == "tags" else fm_aliases
            target.append(line.strip().lstrip("- ").strip())

    return body, fm_tags, fm_aliases


def _chunk_markdown(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Chunk markdown content by H2/H3 sections preserving semantic boundaries."""
    chunks: List[Dict[str, Any]] = []
    doc_title = _extract_title(content)
    doc_type = _infer_doc_type(file_path)
    category = _infer_category(file_path)

    h2_splits = re.split(r"^(##\s+.+)$", content, flags=re.MULTILINE)

    # Intro content before first H2
    intro = h2_splits[0].strip() if h2_splits else ""
    if intro and _estimate_tokens(intro) > 50:
        chunks.extend(
            _create_chunk(piece, "Introduction", None, file_path, doc_type, category, doc_title)
            for piece in chunk_plain_text(intro)
        )

    _process_h2_sections(h2_splits, file_path, doc_type, category, doc_title, chunks)

    # Fallback: no headers found
    if not chunks and content.strip():
        _chunk_large_content(
            content,
            "Content",
            None,
            file_path,
            doc_type,
            category,
            doc_title,
            chunks,
        )

    return chunks
