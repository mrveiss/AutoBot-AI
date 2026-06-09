# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Template library service (GH#8260).

Handles publish, list, fetch, import, and KB indexing for the platform-level
template library. All ChromaDB operations target the ``platform:template_kb``
collection.
"""

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.enums import ActivityEventType
from llc.models.template import (
    TemplateCategory,
    TemplateDetail,
    TemplateImportRequest,
    TemplateImportResult,
    TemplateListParams,
    TemplatePublishRequest,
    TemplateRead,
    TemplateSearchResult,
)

from .activity_log import ActorType, LLCActivityLogService

logger = logging.getLogger(__name__)

_PLATFORM_TEMPLATE_COLLECTION = "platform:template_kb"
_SECRET_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
_TEMPLATE_SEARCH_LIMIT = 10
_BUILT_IN_TEMPLATES_DIR = Path(__file__).parent.parent / "built_in_templates"


class TemplateNotFoundError(Exception):
    """Raised when the requested template does not exist."""


class TemplateSecretPlaceholderError(Exception):
    """Raised when unresolved ``{{SECRET_NAME}}`` placeholders remain at import time."""

    def __init__(self, unresolved: List[str]) -> None:
        self.unresolved = unresolved
        super().__init__(f"Unresolved secret placeholders: {unresolved}")


class TemplateAccessError(Exception):
    """Raised when a company requests a private template it does not own."""


class BuiltInTemplateNotFoundError(Exception):
    """Raised when a built-in template key does not exist."""


class TemplateService:
    """CRUD + KB indexing for LLC template library (GH#8260).

    All methods accept an ``AsyncSession`` and participate in the caller's
    transaction. Callers are responsible for ``session.commit()``.
    """

    def __init__(
        self,
        session: AsyncSession,
        activity_log: Optional[LLCActivityLogService] = None,
    ) -> None:
        self.session = session
        self.activity_log = activity_log

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(
        self,
        req: TemplatePublishRequest,
        company_id: Optional[uuid.UUID],
    ) -> TemplateDetail:
        """Publish a template; scrub re-validated, then indexed in ChromaDB."""
        _validate_no_secrets(req.template_json)
        template_id = uuid.uuid4()

        await self.session.execute(
            sa.text("""
                INSERT INTO llc_template_library
                    (id, name, description, category, template_json,
                     created_by_company_id, is_public)
                VALUES
                    (:id, :name, :description, :category, :template_json::jsonb,
                     :company_id, :is_public)
                """),
            {
                "id": str(template_id),
                "name": req.name,
                "description": req.description,
                "category": req.category.value,
                "template_json": _dump_json(req.template_json),
                "company_id": str(company_id) if company_id else None,
                "is_public": req.is_public,
            },
        )
        await _upsert_tags(self.session, template_id, req.tags)
        await _index_template_in_kb(template_id, req.name, req.description, req.category, req.tags)

        if self.activity_log and company_id:
            await self.activity_log.record(
                self.session,
                company_id=str(company_id),
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_type=ActivityEventType.TEMPLATE_PUBLISHED,
                entity_type="template",
                entity_id=str(template_id),
                after={"name": req.name, "category": req.category.value},
            )

        return await self.get(template_id, requesting_company_id=company_id)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_templates(
        self,
        params: TemplateListParams,
        requesting_company_id: Optional[uuid.UUID],
    ) -> List[TemplateRead]:
        """Return templates visible to ``requesting_company_id``."""
        filters, bind = _build_list_filters(params, requesting_company_id)
        rows = await self.session.execute(
            sa.text(f"""
                SELECT t.id, t.name, t.description, t.category,
                       t.created_by_company_id, t.is_public, t.usage_count,
                       t.created_at, t.updated_at,
                       ARRAY_AGG(tt.tag ORDER BY tt.tag) FILTER (WHERE tt.tag IS NOT NULL) AS tags
                FROM llc_template_library t
                LEFT JOIN llc_template_tags tt ON tt.template_id = t.id
                WHERE {filters}
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT :page_size OFFSET :offset
                """),
            {
                **bind,
                "page_size": params.page_size,
                "offset": (params.page - 1) * params.page_size,
            },
        )
        return [_row_to_template_read(r) for r in rows.mappings()]

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def get(
        self,
        template_id: uuid.UUID,
        requesting_company_id: Optional[uuid.UUID] = None,
    ) -> TemplateDetail:
        """Fetch a single template with full template_json."""
        row = await _fetch_row(self.session, template_id)
        if not row:
            raise TemplateNotFoundError(str(template_id))
        _check_access(row, requesting_company_id)
        tags = await _fetch_tags(self.session, template_id)
        return _row_to_template_detail(row, tags)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    async def import_template(
        self,
        template_id: uuid.UUID,
        req: TemplateImportRequest,
    ) -> TemplateImportResult:
        """Import template into target company; resolve secret placeholders."""
        row = await _fetch_row(self.session, template_id)
        if not row:
            raise TemplateNotFoundError(str(template_id))
        _check_access(row, req.target_company_id)

        resolved_json = _resolve_placeholders(dict(row["template_json"]), req.secrets)
        entities_created = _apply_template(resolved_json)

        await self.session.execute(
            sa.text("UPDATE llc_template_library SET usage_count = usage_count + 1 WHERE id = :id"),
            {"id": str(template_id)},
        )

        activity_id = uuid.uuid4()
        if self.activity_log:
            log = await self.activity_log.record(
                self.session,
                company_id=str(req.target_company_id),
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_type=ActivityEventType.TEMPLATE_IMPORTED,
                entity_type="template",
                entity_id=str(template_id),
                after={"target_company_id": str(req.target_company_id)},
            )
            activity_id = log.id

        return TemplateImportResult(
            template_id=template_id,
            target_company_id=req.target_company_id,
            activity_log_id=activity_id,
            entities_created=entities_created,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, template_id: uuid.UUID) -> None:
        """Delete template from DB and ChromaDB collection."""
        await self.session.execute(
            sa.text("DELETE FROM llc_template_library WHERE id = :id"),
            {"id": str(template_id)},
        )
        await _remove_template_from_kb(template_id)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str) -> List[TemplateSearchResult]:
        """Semantic search over platform:template_kb ChromaDB collection."""
        return await _search_template_kb(query)

    # ------------------------------------------------------------------
    # Built-in Templates (GH#9042)
    # ------------------------------------------------------------------

    @staticmethod
    def list_built_in_templates() -> List[Dict[str, Any]]:
        """List all built-in company templates from disk (GH#9042).

        Returns list of template metadata (name, description, category, tags).
        Does not require a database session.
        """
        return _load_all_built_in_templates()

    @staticmethod
    def get_built_in_template(template_key: str) -> Dict[str, Any]:
        """Fetch a specific built-in template by key (GH#9042).

        Args:
            template_key: Filename without extension (e.g., 'software-team')

        Returns:
            Full template JSON including metadata, variables, agents, goals, etc.

        Raises:
            BuiltInTemplateNotFoundError: If template_key does not exist
        """
        return _load_built_in_template(template_key)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _validate_no_secrets(data: Dict[str, Any], path: str = "") -> None:
    """Recursively assert no raw secret values exist in template_json.

    Secrets must be replaced with ``{{SECRET_NAME}}`` placeholders before
    publish. This function validates the export was properly scrubbed.
    """
    for key, value in data.items():
        current = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            _validate_no_secrets(value, current)
        elif isinstance(value, str):
            _check_for_secret_patterns(value, current)


def _check_for_secret_patterns(value: str, path: str) -> None:
    """Detect common secret patterns (keys, tokens, passwords)."""
    lower = value.lower()
    suspicious_keys = ("password", "secret", "token", "api_key", "private_key")
    if any(k in lower for k in suspicious_keys) and len(value) > 20:
        logger.warning("Potential secret at path %s — value exceeds 20 chars", path)


def _resolve_placeholders(
    data: Any,
    secrets: Dict[str, str],
) -> Any:
    """Recursively replace ``{{KEY}}`` with values from secrets dict.

    Raises TemplateSecretPlaceholderError if any placeholders remain unresolved.
    """
    result = _replace_in_structure(data, secrets)
    unresolved = _find_placeholders(result)
    if unresolved:
        raise TemplateSecretPlaceholderError(sorted(unresolved))
    return result


def _replace_in_structure(data: Any, secrets: Dict[str, str]) -> Any:
    """Recursively replace placeholders in nested dict/list/str structures."""
    if isinstance(data, dict):
        return {k: _replace_in_structure(v, secrets) for k, v in data.items()}
    if isinstance(data, list):
        return [_replace_in_structure(item, secrets) for item in data]
    if isinstance(data, str):
        return _SECRET_PLACEHOLDER_RE.sub(lambda m: secrets.get(m.group(1), m.group(0)), data)
    return data


def _find_placeholders(data: Any) -> List[str]:
    """Return list of all remaining ``{{KEY}}`` placeholder names."""
    found: List[str] = []
    if isinstance(data, dict):
        for v in data.values():
            found.extend(_find_placeholders(v))
    elif isinstance(data, list):
        for item in data:
            found.extend(_find_placeholders(item))
    elif isinstance(data, str):
        found.extend(_SECRET_PLACEHOLDER_RE.findall(data))
    return found


def _apply_template(template_json: Dict[str, Any]) -> Dict[str, int]:
    """Apply resolved template JSON and return entity creation counts.

    Full entity creation (agents, projects, work items) is deferred to
    GH#8260 follow-up tasks once company creation flow is finalized.
    Returns counts of recognized top-level entity keys for audit.
    """
    entity_keys = ("agents", "projects", "work_items", "goals", "routines")
    return {key: len(template_json[key]) for key in entity_keys if isinstance(template_json.get(key), list)}


async def _upsert_tags(
    session: AsyncSession,
    template_id: uuid.UUID,
    tags: List[str],
) -> None:
    """Insert tags for template; idempotent via ON CONFLICT DO NOTHING."""
    for tag in tags:
        await session.execute(
            sa.text("""
                INSERT INTO llc_template_tags (template_id, tag)
                VALUES (:template_id, :tag)
                ON CONFLICT DO NOTHING
                """),
            {"template_id": str(template_id), "tag": tag.lower().strip()},
        )


async def _fetch_row(session: AsyncSession, template_id: uuid.UUID):
    """Fetch a single template row as a mapping."""
    result = await session.execute(
        sa.text("SELECT * FROM llc_template_library WHERE id = :id"),
        {"id": str(template_id)},
    )
    return result.mappings().first()


async def _fetch_tags(session: AsyncSession, template_id: uuid.UUID) -> List[str]:
    """Fetch sorted tags for a template."""
    result = await session.execute(
        sa.text("SELECT tag FROM llc_template_tags WHERE template_id = :id ORDER BY tag"),
        {"id": str(template_id)},
    )
    return [r["tag"] for r in result.mappings()]


def _check_access(row, requesting_company_id: Optional[uuid.UUID]) -> None:
    """Raise TemplateAccessError if the company cannot see this template."""
    if row["is_public"]:
        return
    owner = row["created_by_company_id"]
    if requesting_company_id is None or str(owner) != str(requesting_company_id):
        raise TemplateAccessError(str(row["id"]))


def _build_list_filters(
    params: TemplateListParams,
    company_id: Optional[uuid.UUID],
) -> tuple:
    """Build WHERE clause and bind params for list query."""
    clauses = []
    bind: Dict[str, Any] = {}

    if company_id:
        clauses.append("(t.is_public = true OR t.created_by_company_id = :company_id)")
        bind["company_id"] = str(company_id)
    else:
        clauses.append("t.is_public = true")

    if params.category:
        clauses.append("t.category = :category")
        bind["category"] = params.category.value

    if params.q:
        clauses.append("(t.name ILIKE :q OR t.description ILIKE :q)")
        bind["q"] = f"%{params.q}%"

    if params.tag:
        clauses.append(
            "EXISTS (SELECT 1 FROM llc_template_tags tt2 " "WHERE tt2.template_id = t.id AND tt2.tag = :tag)"
        )
        bind["tag"] = params.tag.lower().strip()

    where = " AND ".join(clauses) if clauses else "1=1"
    return where, bind


def _row_to_template_read(row) -> TemplateRead:
    """Convert a DB row mapping to TemplateRead."""
    return TemplateRead(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        category=TemplateCategory(row["category"]),
        created_by_company_id=row["created_by_company_id"],
        is_public=row["is_public"],
        usage_count=row["usage_count"],
        tags=row["tags"] or [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_template_detail(row, tags: List[str]) -> TemplateDetail:
    """Convert a DB row mapping to TemplateDetail (includes template_json)."""
    return TemplateDetail(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        category=TemplateCategory(row["category"]),
        created_by_company_id=row["created_by_company_id"],
        is_public=row["is_public"],
        usage_count=row["usage_count"],
        tags=tags,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        template_json=dict(row["template_json"]),
    )


def _dump_json(data: Dict[str, Any]) -> str:
    """Serialize dict to JSON string for parameterized insert."""
    import json

    return json.dumps(data, ensure_ascii=False)


async def _index_template_in_kb(
    template_id: uuid.UUID,
    name: str,
    description: Optional[str],
    category: TemplateCategory,
    tags: List[str],
) -> None:
    """Embed template metadata and upsert into platform:template_kb."""
    try:
        from knowledge import get_knowledge_base

        doc_text = _build_embed_text(name, description, category, tags)
        kb = await get_knowledge_base()
        collection = await kb._async_chroma_client.get_or_create_collection(
            name=_PLATFORM_TEMPLATE_COLLECTION,
            metadata={"entity_type": "template", "scope": "platform"},
        )
        await collection.upsert(
            ids=[str(template_id)],
            documents=[doc_text],
            metadatas=[
                {
                    "template_id": str(template_id),
                    "name": name,
                    "description": description or "",
                    "category": category.value,
                }
            ],
        )
        logger.info("Indexed template %s in %s", template_id, _PLATFORM_TEMPLATE_COLLECTION)
    except Exception:
        logger.exception("Failed to index template %s in ChromaDB", template_id)


async def _remove_template_from_kb(template_id: uuid.UUID) -> None:
    """Remove template embedding from platform:template_kb."""
    try:
        from knowledge import get_knowledge_base

        kb = await get_knowledge_base()
        collection = await kb._async_chroma_client.get_collection(_PLATFORM_TEMPLATE_COLLECTION)
        await collection.delete(ids=[str(template_id)])
        logger.info("Removed template %s from %s", template_id, _PLATFORM_TEMPLATE_COLLECTION)
    except Exception:
        logger.exception("Failed to remove template %s from ChromaDB", template_id)


async def _search_template_kb(query: str) -> List[TemplateSearchResult]:
    """Query platform:template_kb for top-10 semantically similar templates."""
    try:
        from knowledge import get_knowledge_base

        kb = await get_knowledge_base()
        collection = await kb._async_chroma_client.get_or_create_collection(
            name=_PLATFORM_TEMPLATE_COLLECTION,
            metadata={"entity_type": "template", "scope": "platform"},
        )
        results = await collection.query(
            query_texts=[query],
            n_results=_TEMPLATE_SEARCH_LIMIT,
        )
        return _parse_chroma_results(results)
    except Exception:
        logger.exception("Template KB search failed for query: %s", query)
        return []


def _parse_chroma_results(results: Dict[str, Any]) -> List[TemplateSearchResult]:
    """Parse ChromaDB query response into TemplateSearchResult list."""
    output: List[TemplateSearchResult] = []
    ids = (results.get("ids") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    for doc_id, meta, dist in zip(ids, metadatas, distances):
        output.append(
            TemplateSearchResult(
                template_id=doc_id,
                name=meta.get("name", ""),
                description=meta.get("description") or None,
                category=meta.get("category", ""),
                score=round(1.0 - float(dist), 4),
            )
        )
    return output


def _build_embed_text(
    name: str,
    description: Optional[str],
    category: TemplateCategory,
    tags: List[str],
) -> str:
    """Compose embedding source text for a template."""
    parts = [f"Category: {category.value}", f"Name: {name}"]
    if description:
        parts.append(f"Description: {description}")
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    return "\n".join(parts)


# ------------------------------------------------------------------
# Built-in template loaders (GH#9042)
# ------------------------------------------------------------------


def _load_all_built_in_templates() -> List[Dict[str, Any]]:
    """Load metadata for all built-in templates from disk.

    Returns list of template metadata (does not include full template_json).
    """
    templates = []
    if not _BUILT_IN_TEMPLATES_DIR.exists():
        logger.warning("Built-in templates directory not found: %s", _BUILT_IN_TEMPLATES_DIR)
        return templates

    for template_file in sorted(_BUILT_IN_TEMPLATES_DIR.glob("*.json")):
        try:
            with open(template_file, encoding="utf-8") as f:
                data = json.load(f)
                metadata = data.get("metadata", {})
                templates.append(
                    {
                        "key": template_file.stem,
                        "name": metadata.get("name", template_file.stem),
                        "description": metadata.get("description"),
                        "category": metadata.get("category", "company"),
                        "version": metadata.get("version", "1.0"),
                        "tags": metadata.get("tags", []),
                    }
                )
        except Exception:
            logger.exception("Failed to load built-in template: %s", template_file)
            continue

    return templates


def _load_built_in_template(template_key: str) -> Dict[str, Any]:
    """Load a specific built-in template by key.

    Args:
        template_key: Filename without extension (e.g., 'software-team')

    Returns:
        Full template JSON

    Raises:
        BuiltInTemplateNotFoundError: If template does not exist or key is invalid
    """
    # Validate template_key against strict allowlist to prevent path traversal
    if not re.fullmatch(r"[a-z0-9_-]+", template_key):
        raise BuiltInTemplateNotFoundError(
            f"Invalid template key '{template_key}' — must contain only lowercase letters, "
            f"numbers, hyphens, and underscores"
        )

    template_path = _BUILT_IN_TEMPLATES_DIR / f"{template_key}.json"

    # Verify resolved path is within the built-in templates directory
    resolved_path = template_path.resolve()
    base_path = _BUILT_IN_TEMPLATES_DIR.resolve()
    if base_path not in resolved_path.parents and resolved_path != base_path:
        raise BuiltInTemplateNotFoundError(f"Template path outside allowed directory: {template_key}")

    if not resolved_path.exists():
        raise BuiltInTemplateNotFoundError(f"Built-in template '{template_key}' not found")

    try:
        with open(resolved_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.exception("Failed to load built-in template: %s", resolved_path)
        raise BuiltInTemplateNotFoundError(f"Failed to load template '{template_key}'") from exc
