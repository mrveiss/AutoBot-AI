# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Open Knowledge Format (OKF) v0.1 Export/Import Adapter

Issue #10617: Adds a lossless round-trip adapter between the AutoBot Knowledge
Base and OKF bundles — directories of Markdown "concept" files with YAML
frontmatter.

OKF v0.1 spec
-------------
* One file per KB fact/concept: ``<slug>.md``
* YAML frontmatter block delimited by ``---`` fences (required)
* Required frontmatter field: ``type`` (maps to KB metadata ``type`` or
  ``source_type``; defaults to ``"concept"`` when absent in KB metadata)
* Optional frontmatter fields: ``id``, ``title``, ``category``, ``tags``,
  ``created_at``, ``updated_at``, and any other KB metadata keys
* Body: the raw fact ``content`` string
* Cross-links: ``[[target-slug]]`` in the body are rewritten to standard
  Markdown links ``[target-slug](target-slug.md)`` on export and resolved back
  to fact IDs on import

Round-trip guarantee
--------------------
``export_to_okf`` -> ``import_from_okf`` -> ``export_to_okf`` produces a
byte-identical bundle (same file names, same content, same ordering) for any
KB state — enabling git-versionable snapshots of the knowledge base.

Slugging rules
--------------
* Title (from metadata ``title`` key) -> lowercase, alphanumeric + hyphens
* Fallback: fact_id shortened to 8 chars when no title present
* Duplicates get a numeric suffix: ``concept``, ``concept-2``, ``concept-3``
* Slug alphabet: ``[a-z0-9-]``; max 80 chars before suffix

Usage (standalone — no live KB required)
-----------------------------------------
::

    from knowledge.adapters.okf_adapter import OKFAdapter

    adapter = OKFAdapter(kb=None)  # or a real KnowledgeBase instance
    result = await adapter.export_to_okf(facts, "/tmp/my-okf-bundle")
    facts  = await adapter.import_from_okf("/tmp/my-okf-bundle")

Usage (via KB service method)
------------------------------
::

    from knowledge import get_knowledge_base
    from knowledge.adapters.okf_adapter import export_to_okf, import_from_okf

    kb   = await get_knowledge_base()
    info = await export_to_okf(kb, "/tmp/bundle")
    info = await import_from_okf(kb, "/tmp/bundle")
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: YAML frontmatter fence marker.
_FENCE = "---"

#: Default ``type`` value injected when KB metadata has no ``type`` field.
_DEFAULT_TYPE = "concept"

#: Maximum slug length before a disambiguation suffix is appended.
_SLUG_MAX_LEN = 80

#: Wiki-link pattern: ``[[some-slug]]`` — used inside fact content.
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)]]")

#: Markdown link pattern written by export: ``[slug](slug.md)``.
_MDLINK_RE = re.compile(r"\[([^\]]+)]\(([^\)]+)\.md\)")

#: Metadata keys that live in frontmatter (not buried inside ``metadata:``).
_FRONTMATTER_KEYS = frozenset(
    {
        "id",
        "type",
        "title",
        "category",
        "tags",
        "created_at",
        "updated_at",
        "source_type",
        "verification_status",
        "quality_score",
        "collection",
        "embedding_model",
    }
)

#: Keys that should never be round-tripped via frontmatter (internal/runtime).
_SKIP_KEYS = frozenset(
    {
        "fact_id",  # stored as ``id`` in frontmatter
        "timestamp",  # stored as ``created_at``
        "source_type",  # unified with ``type`` in OKF frontmatter
        "content_fingerprint",
        "embedding",
        "provenance_chain",
        "source_connector_id",
        "verification_method",
        "verified_by",
        "verified_at",
        "source_session_id",
    }
)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert *text* to an OKF-safe slug.

    Rules: lowercase Unicode -> ASCII transliteration -> keep ``[a-z0-9]`` and
    spaces -> replace spaces/hyphens with single hyphens -> strip leading/trailing
    hyphens -> truncate to ``_SLUG_MAX_LEN``.

    Args:
        text: Source text (title or fact_id).

    Returns:
        Slug string matching ``[a-z0-9][a-z0-9-]*``.
    """
    # Normalise Unicode and transliterate to ASCII
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    # Replace any non-alphanumeric character with a hyphen
    slugged = re.sub(r"[^a-z0-9]+", "-", lowered)
    slugged = slugged.strip("-")
    return slugged[:_SLUG_MAX_LEN] or "concept"


def _unique_slug(base_slug: str, taken: set, *, counter_start: int = 2) -> str:
    """Return *base_slug* or a disambiguated variant not present in *taken*.

    Args:
        base_slug: Preferred slug.
        taken: Set of already-assigned slugs (mutated by caller after return).
        counter_start: First numeric suffix to try.

    Returns:
        Unique slug string.
    """
    if base_slug not in taken:
        return base_slug
    counter = counter_start
    while True:
        candidate = "%s-%d" % (base_slug, counter)
        if candidate not in taken:
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# OKF file serialisation helpers
# ---------------------------------------------------------------------------


def _build_frontmatter(fact: Dict[str, Any], slug: str) -> Dict[str, Any]:
    """Assemble the YAML frontmatter dict for a single fact.

    The ``type`` key is guaranteed to be present (OKF required field).

    Args:
        fact: KB fact dict with keys ``fact_id``, ``content``, ``metadata``,
              ``timestamp`` (optional).
        slug: The slug assigned to this fact (used as the concept identifier).

    Returns:
        Ordered dict for yaml.dump (type is always first).
    """
    meta = fact.get("metadata") or {}

    fm: Dict[str, Any] = {}

    # Required OKF field — must be first for human readability
    raw_type = meta.get("type") or meta.get("source_type") or _DEFAULT_TYPE
    fm["type"] = str(raw_type)

    # Stable identity
    fm["id"] = fact.get("fact_id", slug)

    # Optional well-known fields — preserve originals when present
    if meta.get("title"):
        fm["title"] = str(meta["title"])
    if meta.get("category"):
        fm["category"] = str(meta["category"])
    if meta.get("tags"):
        tags = meta["tags"]
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        fm["tags"] = sorted(str(t) for t in tags) if tags else []
    if meta.get("collection"):
        fm["collection"] = str(meta["collection"])

    # Timestamps
    created = fact.get("timestamp") or meta.get("created_at") or meta.get("timestamp")
    if created:
        fm["created_at"] = str(created)
    if meta.get("updated_at"):
        fm["updated_at"] = str(meta["updated_at"])

    # Provenance
    if meta.get("verification_status"):
        fm["verification_status"] = str(meta["verification_status"])
    if meta.get("quality_score") is not None and meta["quality_score"] != 0.0:
        fm["quality_score"] = float(meta["quality_score"])
    if meta.get("embedding_model"):
        fm["embedding_model"] = str(meta["embedding_model"])

    # Remaining metadata keys that are not in _SKIP_KEYS and not already emitted
    emitted = set(fm.keys()) | {"type", "id"}
    for key, value in sorted(meta.items()):
        if key in _SKIP_KEYS:
            continue
        if key in emitted:
            continue
        # Serialise dicts/lists as YAML-native structures
        fm[key] = value

    return fm


def _render_okf_file(frontmatter: Dict[str, Any], body: str) -> str:
    """Render a complete OKF ``.md`` file as a string.

    Args:
        frontmatter: Dict to serialise as YAML between ``---`` fences.
        body: Raw concept content (may contain markdown links).

    Returns:
        Complete file content string ending with a newline.
    """
    yaml_block = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return "%s\n%s%s\n\n%s\n" % (_FENCE, yaml_block, _FENCE, body.rstrip())


def _rewrite_wikilinks_to_md(content: str, slug_map: Dict[str, str]) -> str:
    """Replace ``[[target-slug]]`` cross-links with Markdown links on export.

    Args:
        content: Raw fact content possibly containing wiki-links.
        slug_map: Mapping of fact_id -> slug for resolving link targets.

    Returns:
        Content with wiki-links rewritten to ``[slug](slug.md)`` format.
    """

    def _replace(match: re.Match) -> str:
        target = match.group(1).strip()
        # target may be a fact_id or already a slug
        resolved = slug_map.get(target, target)
        return "[%s](%s.md)" % (resolved, resolved)

    return _WIKILINK_RE.sub(_replace, content)


def _rewrite_md_links_to_ids(content: str, slug_to_id: Dict[str, str]) -> str:
    """Replace ``[slug](slug.md)`` links back to ``[[fact_id]]`` on import.

    Args:
        content: OKF file body possibly containing Markdown links.
        slug_to_id: Mapping of slug -> fact_id for resolving link targets.

    Returns:
        Content with Markdown links rewritten to ``[[fact_id]]`` format.
    """

    def _replace(match: re.Match) -> str:
        slug = match.group(2).strip()  # group 2 is the href without .md
        fact_id = slug_to_id.get(slug, slug)
        return "[[%s]]" % fact_id

    return _MDLINK_RE.sub(_replace, content)


# ---------------------------------------------------------------------------
# OKF file parsing helpers
# ---------------------------------------------------------------------------


def _parse_okf_file(path: Path) -> Tuple[Dict[str, Any], str]:
    """Parse an OKF ``.md`` file into frontmatter dict and body string.

    Args:
        path: Path to the ``.md`` file.

    Returns:
        ``(frontmatter, body)`` tuple.

    Raises:
        ValueError: If the file lacks a valid frontmatter block or the
                    required ``type`` field is absent.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.split("\n")

    if not lines or lines[0].rstrip() != _FENCE:
        raise ValueError("OKF file %s does not start with '---' frontmatter fence" % path)

    end_fence = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == _FENCE:
            end_fence = i
            break

    if end_fence is None:
        raise ValueError("OKF file %s has no closing '---' frontmatter fence" % path)

    yaml_text = "\n".join(lines[1:end_fence])
    frontmatter = yaml.safe_load(yaml_text) or {}

    if "type" not in frontmatter:
        raise ValueError("OKF file %s is missing required 'type' frontmatter field" % path)

    # Body starts after the blank line that follows the closing fence
    body_lines = lines[end_fence + 1 :]
    # Strip one leading blank line if present (written by _render_okf_file)
    if body_lines and not body_lines[0].strip():
        body_lines = body_lines[1:]
    body = "\n".join(body_lines).rstrip()

    return frontmatter, body


def _frontmatter_to_metadata(frontmatter: Dict[str, Any], fact_id: str) -> Dict[str, Any]:
    """Reconstruct KB metadata from OKF frontmatter.

    Args:
        frontmatter: Parsed YAML frontmatter dict.
        fact_id: The canonical fact_id (from ``id`` field or derived from slug).

    Returns:
        KB-compatible metadata dict.
    """
    meta: Dict[str, Any] = {}

    meta["fact_id"] = fact_id

    # Required OKF field
    raw_type = frontmatter.get("type", _DEFAULT_TYPE)
    meta["type"] = str(raw_type)
    # Preserve source_type for KB provenance
    meta["source_type"] = str(raw_type)

    # Map well-known fields back
    for key in (
        "title",
        "category",
        "collection",
        "verification_status",
        "quality_score",
        "embedding_model",
    ):
        if key in frontmatter:
            meta[key] = frontmatter[key]

    if "tags" in frontmatter:
        tags = frontmatter["tags"]
        if isinstance(tags, list):
            meta["tags"] = tags
        elif isinstance(tags, str):
            meta["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    if "created_at" in frontmatter:
        meta["created_at"] = str(frontmatter["created_at"])
        meta["timestamp"] = str(frontmatter["created_at"])
    if "updated_at" in frontmatter:
        meta["updated_at"] = str(frontmatter["updated_at"])

    # Pass through any extra keys not already handled
    handled = frozenset(
        {
            "type",
            "id",
            "title",
            "category",
            "tags",
            "collection",
            "created_at",
            "updated_at",
            "verification_status",
            "quality_score",
            "embedding_model",
        }
    )
    for key, value in frontmatter.items():
        if key not in handled and key not in meta:
            meta[key] = value

    return meta


# ---------------------------------------------------------------------------
# Main adapter class
# ---------------------------------------------------------------------------


class OKFAdapter:
    """Lossless OKF v0.1 export/import adapter for the AutoBot Knowledge Base.

    Can operate standalone (``kb=None``) against a pre-loaded list of fact
    dicts, or against a live ``KnowledgeBase`` instance for full round-trips.

    Deterministic output
    --------------------
    Facts are sorted by ``fact_id`` before export so that the resulting file
    set is stable across runs and git-versionable.
    """

    def __init__(self, kb: Optional[Any] = None) -> None:
        """Initialise the adapter.

        Args:
            kb: Optional live ``KnowledgeBase`` instance.  Required only for
                the ``export_from_kb`` and ``import_into_kb`` convenience
                helpers; ``export_to_okf`` and ``import_from_okf`` accept
                caller-supplied fact dicts directly.
        """
        self._kb = kb

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _assign_slugs(self, facts: List[Dict[str, Any]]) -> Dict[str, str]:
        """Build a stable fact_id -> slug mapping for all facts.

        Facts are sorted by ``fact_id`` before slug assignment to ensure
        deterministic output.

        Args:
            facts: List of KB fact dicts.

        Returns:
            Mapping of ``fact_id -> slug``.
        """
        slug_map: Dict[str, str] = {}
        taken: set = set()
        for fact in sorted(facts, key=lambda f: f.get("fact_id", "")):
            fact_id = fact.get("fact_id", "")
            meta = fact.get("metadata") or {}
            title = meta.get("title") or fact_id[:8]
            base = _slugify(title)
            slug = _unique_slug(base, taken)
            taken.add(slug)
            slug_map[fact_id] = slug
        return slug_map

    async def export_to_okf(
        self,
        facts: List[Dict[str, Any]],
        output_dir: str,
    ) -> Dict[str, Any]:
        """Serialise a list of KB facts to an OKF bundle directory.

        Each fact becomes one ``<slug>.md`` file containing YAML frontmatter
        (with required ``type`` field) and the fact ``content`` as the body.
        Wiki-link cross-references (``[[fact_id]]``) in content are rewritten
        to Markdown links (``[slug](slug.md)``).

        Args:
            facts: List of KB fact dicts (from ``kb.get_all_facts()`` or
                   similar).  Each dict must contain at minimum ``fact_id``
                   and ``content``.
            output_dir: Directory path to write ``*.md`` files into.  Created
                        if it does not exist.

        Returns:
            Dict with keys ``status``, ``exported_count``, ``output_dir``,
            ``files``.
        """
        try:
            out_path = Path(output_dir)
            await asyncio.to_thread(out_path.mkdir, parents=True, exist_ok=True)

            slug_map = self._assign_slugs(facts)

            files_written: List[str] = []
            # Process in deterministic order (sort by fact_id)
            for fact in sorted(facts, key=lambda f: f.get("fact_id", "")):
                fact_id = fact.get("fact_id", "")
                slug = slug_map.get(fact_id, _slugify(fact_id[:8]))

                content = fact.get("content", "")
                body = _rewrite_wikilinks_to_md(content, slug_map)

                frontmatter = _build_frontmatter(fact, slug)
                file_content = _render_okf_file(frontmatter, body)

                file_path = out_path / ("%s.md" % slug)
                await asyncio.to_thread(file_path.write_text, file_content, encoding="utf-8")
                files_written.append(str(file_path))
                logger.debug("OKF export: wrote %s (fact_id=%s)", file_path.name, fact_id)

            logger.info("OKF export complete: %d facts -> %s", len(files_written), out_path)
            return {
                "status": "success",
                "exported_count": len(files_written),
                "output_dir": str(out_path),
                "files": sorted(files_written),
            }

        except Exception as exc:
            logger.error("OKF export failed: %s", exc)
            return {"status": "error", "message": "OKF export failed: %s" % exc}

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    async def import_from_okf(self, bundle_dir: str) -> Dict[str, Any]:
        """Parse an OKF bundle directory back into a list of KB fact dicts.

        All ``*.md`` files are parsed in alphabetical (slug) order.  Markdown
        cross-links (``[slug](slug.md)``) are resolved back to ``[[fact_id]]``
        wiki-links using the ``id`` field in each file's frontmatter.

        Args:
            bundle_dir: Path to the OKF bundle directory (must exist).

        Returns:
            Dict with keys ``status``, ``imported_count``, ``facts``,
            ``errors`` (list of per-file error strings).

        Notes:
            The returned facts are **not** automatically stored in the KB.
            Pass them to ``kb.store_fact()`` or use ``import_into_kb()``.
        """
        bundle_path = Path(bundle_dir)
        if not await asyncio.to_thread(bundle_path.is_dir):
            return {
                "status": "error",
                "message": "Bundle directory not found: %s" % bundle_dir,
            }

        md_files = sorted(await asyncio.to_thread(lambda: list(bundle_path.glob("*.md"))))

        # First pass: collect slug -> fact_id mapping for cross-link resolution
        slug_to_id: Dict[str, str] = {}
        raw_parsed: List[Tuple[str, Dict[str, Any], str]] = []
        errors: List[str] = []

        for md_file in md_files:
            try:
                frontmatter, body = await asyncio.to_thread(_parse_okf_file, md_file)
                slug = md_file.stem
                fact_id = str(frontmatter.get("id") or slug)
                slug_to_id[slug] = fact_id
                raw_parsed.append((slug, frontmatter, body))
            except Exception as exc:
                errors.append("%s: %s" % (md_file.name, exc))
                logger.warning("OKF import: skipped %s — %s", md_file.name, exc)

        # Second pass: resolve cross-links and build fact dicts
        facts: List[Dict[str, Any]] = []
        for slug, frontmatter, body in raw_parsed:
            fact_id = slug_to_id[slug]
            content = _rewrite_md_links_to_ids(body, slug_to_id)
            metadata = _frontmatter_to_metadata(frontmatter, fact_id)
            facts.append(
                {
                    "fact_id": fact_id,
                    "content": content,
                    "metadata": metadata,
                    "timestamp": metadata.get("created_at", ""),
                }
            )

        logger.info(
            "OKF import complete: %d facts parsed, %d errors",
            len(facts),
            len(errors),
        )
        result: Dict[str, Any] = {
            "status": "success" if not errors else "partial",
            "imported_count": len(facts),
            "facts": facts,
        }
        if errors:
            result["errors"] = errors
        return result

    # ------------------------------------------------------------------
    # KB service integration helpers
    # ------------------------------------------------------------------

    async def export_from_kb(
        self,
        output_dir: str,
        *,
        collection: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Export facts from a live KB to an OKF bundle.

        Requires ``self._kb`` to be a fully initialised ``KnowledgeBase``
        instance.

        Args:
            output_dir: Target directory for ``.md`` files.
            collection: Optional collection filter (passed to ``get_all_facts``).
            limit: Maximum number of facts to export.
            offset: Fact scan offset.

        Returns:
            Same dict shape as ``export_to_okf``.
        """
        if self._kb is None:
            return {"status": "error", "message": "No KnowledgeBase instance provided"}

        facts = await self._kb.get_all_facts(limit=limit, offset=offset, collection=collection)
        return await self.export_to_okf(facts, output_dir)

    async def import_into_kb(
        self,
        bundle_dir: str,
        *,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Import an OKF bundle into a live KB.

        Requires ``self._kb`` to be a fully initialised ``KnowledgeBase``
        instance.  Each parsed fact is stored via ``kb.store_fact()``.  When a
        fact already exists (duplicate detection in ``store_fact``) the result is
        counted as ``skipped`` unless *overwrite* is True (in which case
        ``update_fact`` is called instead).

        Args:
            bundle_dir: Path to the OKF bundle directory.
            overwrite: If True, update existing facts with ``update_fact()``
                       rather than skipping duplicates.

        Returns:
            Dict with ``status``, ``stored_count``, ``skipped_count``,
            ``error_count``, ``errors``.
        """
        if self._kb is None:
            return {"status": "error", "message": "No KnowledgeBase instance provided"}

        parse_result = await self.import_from_okf(bundle_dir)
        if parse_result.get("status") == "error":
            return parse_result

        facts = parse_result.get("facts", [])
        errors: List[str] = list(parse_result.get("errors", []))
        stored = 0
        skipped = 0
        error_count = 0

        for fact in facts:
            fact_id = fact["fact_id"]
            content = fact["content"]
            metadata = fact["metadata"]
            try:
                result = await self._kb.store_fact(content, metadata, fact_id)
                status = result.get("status")
                if status == "success":
                    stored += 1
                elif status == "duplicate":
                    if overwrite:
                        upd = await self._kb.update_fact(fact_id, content=content, metadata=metadata)
                        if upd.get("status") == "success":
                            stored += 1
                        else:
                            error_count += 1
                            errors.append("update %s: %s" % (fact_id, upd.get("message")))
                    else:
                        skipped += 1
                else:
                    error_count += 1
                    errors.append("store %s: %s" % (fact_id, result.get("message")))
            except Exception as exc:
                error_count += 1
                errors.append("store %s: %s" % (fact_id, exc))
                logger.error("OKF import_into_kb: failed to store fact %s: %s", fact_id, exc)

        logger.info(
            "OKF import_into_kb: stored=%d skipped=%d errors=%d",
            stored,
            skipped,
            error_count,
        )
        result_dict: Dict[str, Any] = {
            "status": "success" if error_count == 0 else "partial",
            "stored_count": stored,
            "skipped_count": skipped,
            "error_count": error_count,
        }
        if errors:
            result_dict["errors"] = errors
        return result_dict


# ---------------------------------------------------------------------------
# Module-level convenience functions (KB service API surface)
# ---------------------------------------------------------------------------


async def export_to_okf(
    kb: Any,
    output_dir: str,
    *,
    collection: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Dict[str, Any]:
    """Export KB facts to an OKF bundle directory.

    Convenience wrapper around ``OKFAdapter.export_from_kb``.

    Args:
        kb: Initialised ``KnowledgeBase`` instance.
        output_dir: Target directory path (created if absent).
        collection: Optional collection filter.
        limit: Maximum facts to export (None = all).
        offset: Scan offset.

    Returns:
        Dict with export result metadata.
    """
    adapter = OKFAdapter(kb=kb)
    return await adapter.export_from_kb(output_dir, collection=collection, limit=limit, offset=offset)


async def import_from_okf(
    kb: Any,
    bundle_dir: str,
    *,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Import an OKF bundle into the KB.

    Convenience wrapper around ``OKFAdapter.import_into_kb``.

    Args:
        kb: Initialised ``KnowledgeBase`` instance.
        bundle_dir: Path to the OKF bundle directory.
        overwrite: If True, update existing facts instead of skipping
                   duplicates.

    Returns:
        Dict with import result metadata.
    """
    adapter = OKFAdapter(kb=kb)
    return await adapter.import_into_kb(bundle_dir, overwrite=overwrite)
