# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Bulk Operations Module

Contains the BulkOperationsMixin class for bulk import, export,
delete, update, cleanup, and deduplication operations.

Issue #358: Fixed file I/O to use proper context managers with asyncio.to_thread.
"""

import asyncio
import csv
import json
import logging
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import aioredis
    import redis

logger = logging.getLogger(__name__)


# ===== Helper functions for date filtering (Issue #398: extracted) =====


def _parse_date_bound(date_str: Optional[str], is_end_date: bool = False) -> Optional[datetime]:
    """
    Parse a date string to datetime.

    Issue #398: Extracted from _apply_date_filter.

    Args:
        date_str: Date string in YYYY-MM-DD format
        is_end_date: If True, set time to end of day

    Returns:
        Parsed datetime or None if invalid
    """
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if is_end_date:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError:
        logger.warning("Invalid date format: %s", date_str)
        return None


def _parse_fact_timestamp(timestamp_str: Any) -> Optional[datetime]:
    """
    Parse fact timestamp to datetime.

    Issue #398: Extracted from _apply_date_filter.

    Args:
        timestamp_str: Timestamp string (ISO format or YYYY-MM-DD)

    Returns:
        Parsed datetime or None if invalid
    """
    if not timestamp_str or not isinstance(timestamp_str, str):
        return None
    try:
        if "T" in timestamp_str:
            return datetime.fromisoformat(
                timestamp_str.replace("Z", "+00:00").split("+")[0]
            )
        return datetime.strptime(timestamp_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _normalize_tags(tags: Any) -> List[str]:
    """
    Normalize tags to list of lowercase strings.

    Issue #398: Extracted from _validate_fact_for_import.

    Args:
        tags: Tags as string, list, or other

    Returns:
        Normalized list of tag strings
    """
    if isinstance(tags, str):
        return [t.strip().lower() for t in tags.split(",") if t.strip()]
    elif isinstance(tags, list):
        return [str(t).strip().lower() for t in tags if t and str(t).strip()]
    return []


def _write_file_sync(filepath: str, content: str) -> None:
    """Write content to file synchronously with proper resource management (Issue #358)."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def _read_file_sync(filepath: str) -> str:
    """Read content from file synchronously with proper resource management (Issue #358)."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


class BulkOperationsMixin:
    """
    Bulk operations mixin for knowledge base.

    Provides bulk operations:
    - Export facts (JSON, CSV, Markdown)
    - Import facts from files
    - Find duplicates
    - Bulk delete
    - Bulk update category
    - Cleanup operations

    Key Features:
    - Multiple export formats
    - Filtering support
    - Duplicate detection with similarity
    - Atomic operations
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"
    vector_store: Any

    async def _get_export_facts(
        self, fact_ids: Optional[List[str]], category: Optional[str],
        categories: Optional[List[str]], tags: Optional[List[str]],
        date_from: Optional[str], date_to: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Get and filter facts for export (Issue #398: extracted)."""
        facts = await self._get_facts_by_ids(fact_ids) if fact_ids else await self.get_all_facts()
        facts = self._apply_category_filter(facts, category)
        facts = self._apply_categories_filter(facts, categories)
        facts = self._apply_tags_filter(facts, tags)
        return self._apply_date_filter(facts, date_from, date_to)

    async def export_facts(
        self, format: str = "json", output_file: Optional[str] = None,
        category: Optional[str] = None, categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None, date_from: Optional[str] = None,
        date_to: Optional[str] = None, fact_ids: Optional[List[str]] = None,
        include_embeddings: bool = False, include_metadata: bool = True,
        include_tags: bool = True,
    ) -> Dict[str, Any]:
        """Export facts with optional filtering (Issue #398: refactored)."""
        try:
            facts = await self._get_export_facts(
                fact_ids, category, categories, tags, date_from, date_to
            )

            if include_embeddings:
                facts = await self._add_embeddings_to_facts(facts)
            if not include_metadata or not include_tags:
                facts = self._filter_fact_fields(facts, include_metadata, include_tags)

            output = self._format_output(facts, format)
            if output is None:
                return {"status": "error", "message": f"Unknown format: {format}"}

            return await self._build_export_result(facts, output, output_file)

        except Exception as e:
            logger.error("Export failed: %s", e)
            return {"status": "error", "message": str(e)}

    def _apply_category_filter(
        self, facts: List[Dict[str, Any]], category: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Filter facts by single category (legacy support)."""
        if not category:
            return facts
        return [
            f for f in facts
            if f.get("metadata", {}).get("category") == category
        ]

    def _apply_categories_filter(
        self, facts: List[Dict[str, Any]], categories: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """
        Filter facts by multiple categories (any match).

        Issue #415: Support filtering by multiple categories.
        """
        if not categories:
            return facts
        categories_set = set(categories)
        return [
            f for f in facts
            if f.get("metadata", {}).get("category") in categories_set
        ]

    def _filter_fact_fields(
        self,
        facts: List[Dict[str, Any]],
        include_metadata: bool,
        include_tags: bool,
    ) -> List[Dict[str, Any]]:
        """
        Filter fact fields based on include flags.

        Issue #415: Control what fields are included in export.
        """
        result = []
        for fact in facts:
            filtered_fact = {
                "fact_id": fact.get("fact_id"),
                "content": fact.get("content"),
            }

            # Include timestamp if present
            if "timestamp" in fact:
                filtered_fact["timestamp"] = fact["timestamp"]

            # Include embedding if present
            if "embedding" in fact:
                filtered_fact["embedding"] = fact["embedding"]

            if include_metadata:
                metadata = fact.get("metadata", {}).copy()
                if not include_tags:
                    metadata.pop("tags", None)
                filtered_fact["metadata"] = metadata
            elif include_tags:
                # Only tags requested, not full metadata
                tags = fact.get("metadata", {}).get("tags", [])
                filtered_fact["tags"] = tags

            result.append(filtered_fact)

        return result

    def _apply_tags_filter(
        self, facts: List[Dict[str, Any]], tags: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """Filter facts by tags (match any)."""
        if not tags:
            return facts
        filtered = []
        for fact in facts:
            fact_tags = set(fact.get("metadata", {}).get("tags", []))
            if any(tag in fact_tags for tag in tags):
                filtered.append(fact)
        return filtered

    def _apply_date_filter(
        self,
        facts: List[Dict[str, Any]],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        Filter facts by date range.

        Issue #415: Date filtering for export.
        Issue #398: Refactored using extracted helpers.

        Args:
            facts: List of facts to filter
            date_from: Start date (YYYY-MM-DD), inclusive
            date_to: End date (YYYY-MM-DD), inclusive

        Returns:
            Filtered list of facts
        """
        if not date_from and not date_to:
            return facts

        from_dt = _parse_date_bound(date_from, is_end_date=False)
        to_dt = _parse_date_bound(date_to, is_end_date=True)

        if not from_dt and not to_dt:
            return facts

        return self._filter_facts_by_date_range(facts, from_dt, to_dt)

    def _filter_facts_by_date_range(
        self,
        facts: List[Dict[str, Any]],
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        """
        Filter facts by parsed date range.

        Issue #398: Extracted from _apply_date_filter.
        """
        filtered = []
        for fact in facts:
            timestamp_str = fact.get("timestamp") or fact.get(
                "metadata", {}
            ).get("created_at")

            if not timestamp_str:
                filtered.append(fact)
                continue

            fact_dt = _parse_fact_timestamp(timestamp_str)
            if fact_dt is None:
                filtered.append(fact)
                continue

            if from_dt and fact_dt < from_dt:
                continue
            if to_dt and fact_dt > to_dt:
                continue

            filtered.append(fact)

        return filtered

    def _decode_redis_field(self, data: dict, *keys: str) -> Optional[str]:
        """Decode a Redis field value (Issue #398: extracted)."""
        for key in keys:
            value = data.get(key.encode()) or data.get(key)
            if value:
                return value.decode("utf-8") if isinstance(value, bytes) else value
        return None

    def _parse_fact_data(self, fact_id: str, fact_data: dict) -> Dict[str, Any]:
        """Parse Redis fact data to dict (Issue #398: extracted)."""
        fact = {"fact_id": fact_id}
        content = self._decode_redis_field(fact_data, "content")
        if content:
            fact["content"] = content
        metadata_json = self._decode_redis_field(fact_data, "metadata")
        if metadata_json:
            fact["metadata"] = json.loads(metadata_json)
        timestamp = self._decode_redis_field(fact_data, "timestamp")
        if timestamp:
            fact["timestamp"] = timestamp
        return fact

    async def _get_facts_by_ids(self, fact_ids: List[str]) -> List[Dict[str, Any]]:
        """Get specific facts by their IDs (Issue #398: refactored)."""
        facts = []
        for fact_id in fact_ids:
            try:
                fact_data = await asyncio.to_thread(
                    self.redis_client.hgetall, f"fact:{fact_id}"
                )
                if fact_data:
                    facts.append(self._parse_fact_data(fact_id, fact_data))
            except Exception as e:
                logger.warning("Failed to get fact %s: %s", fact_id, e)
        return facts

    async def _fetch_embeddings_from_vector_store(
        self, fact_ids: List[str]
    ) -> Dict[str, List[float]]:
        """Fetch embeddings from vector store (Issue #398: extracted)."""
        result = await asyncio.to_thread(
            self.vector_store.get, ids=fact_ids, include=["embeddings"]
        )
        if result and result.get("ids") and result.get("embeddings"):
            return dict(zip(result["ids"], result["embeddings"]))
        return {}

    async def _add_embeddings_to_facts(self, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add vector embeddings to facts from ChromaDB (Issue #398: refactored)."""
        if not facts or not hasattr(self, "vector_store") or self.vector_store is None:
            return facts

        try:
            fact_ids = [f.get("fact_id") for f in facts if f.get("fact_id")]
            if not fact_ids:
                return facts

            try:
                embeddings_map = await self._fetch_embeddings_from_vector_store(fact_ids)
                for fact in facts:
                    fact_id = fact.get("fact_id")
                    if fact_id and fact_id in embeddings_map:
                        fact["embedding"] = embeddings_map[fact_id]
            except Exception as e:
                logger.warning("Could not retrieve embeddings: %s", e)
        except Exception as e:
            logger.error("Failed to add embeddings to facts: %s", e)

        return facts

    def _format_output(
        self, facts: List[Dict[str, Any]], format: str
    ) -> Optional[str]:
        """Format facts based on export format."""
        formatters = {
            "json": self._format_export_json,
            "csv": self._format_export_csv,
            "markdown": self._format_export_markdown,
        }
        formatter = formatters.get(format)
        return formatter(facts) if formatter else None

    async def _build_export_result(
        self,
        facts: List[Dict[str, Any]],
        output: str,
        output_file: Optional[str],
    ) -> Dict[str, Any]:
        """Build export result, optionally saving to file."""
        if output_file:
            await asyncio.to_thread(_write_file_sync, output_file, output)
            return {
                "status": "success",
                "facts_exported": len(facts),
                "output_file": output_file,
            }
        return {
            "status": "success",
            "facts_exported": len(facts),
            "data": output,
        }

    def _format_export_json(self, facts: List[Dict[str, Any]]) -> str:
        """Format facts as JSON"""
        return json.dumps(facts, indent=2, ensure_ascii=False)

    def _format_export_csv(self, facts: List[Dict[str, Any]]) -> str:
        """Format facts as CSV"""
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["fact_id", "content", "category", "tags", "timestamp"])

        for fact in facts:
            metadata = fact.get("metadata", {})
            writer.writerow(
                [
                    fact.get("fact_id", ""),
                    fact.get("content", ""),
                    metadata.get("category", ""),
                    ", ".join(metadata.get("tags", [])),
                    fact.get("timestamp", ""),
                ]
            )

        return output.getvalue()

    def _format_export_markdown(self, facts: List[Dict[str, Any]]) -> str:
        """Format facts as Markdown"""
        lines = ["# Knowledge Base Export", "", f"Generated: {datetime.now().isoformat()}", ""]

        for fact in facts:
            metadata = fact.get("metadata", {})
            lines.append(f"## {metadata.get('title', 'Untitled')}")
            lines.append(f"**ID**: {fact.get('fact_id', '')}")
            lines.append(f"**Category**: {metadata.get('category', 'N/A')}")
            lines.append(f"**Tags**: {', '.join(metadata.get('tags', []))}")
            lines.append("")
            lines.append(fact.get("content", ""))
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    async def _get_import_content(
        self, source_file: Optional[str], data: Optional[str]
    ) -> tuple:
        """Get content for import from file or data (Issue #398: extracted)."""
        if source_file:
            return await asyncio.to_thread(_read_file_sync, source_file), None
        elif data:
            return data, None
        return None, {"status": "error", "message": "Either source_file or data required"}

    def _parse_import_data(
        self, content: str, format: str
    ) -> tuple:
        """Parse import data based on format (Issue #398: extracted)."""
        if format == "json":
            return self._parse_import_json(content), None
        elif format == "csv":
            return self._parse_import_csv(content), None
        return None, {"status": "error", "message": f"Unknown format: {format}"}

    def _validate_all_facts(
        self,
        facts: List[Dict[str, Any]],
        default_category: str,
        min_content_length: int,
        max_content_length: int,
    ) -> tuple:
        """Validate all facts and return results (Issue #398: extracted)."""
        validation_results = []
        valid_facts = []

        for idx, fact_data in enumerate(facts):
            validation = self._validate_fact_for_import(
                fact_data, idx, default_category, min_content_length, max_content_length
            )
            validation_results.append(validation)
            if validation["valid"]:
                valid_facts.append(validation["normalized_fact"])

        valid_count = sum(1 for v in validation_results if v["valid"])
        invalid_count = len(validation_results) - valid_count

        return valid_facts, validation_results, valid_count, invalid_count

    def _build_validation_only_result(
        self, facts: List, validation_results: List, valid_count: int, invalid_count: int
    ) -> Dict[str, Any]:
        """Build validation-only result (Issue #398: extracted)."""
        return {
            "status": "success",
            "mode": "validate_only",
            "total_facts": len(facts),
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "validation_results": validation_results,
        }

    def _build_import_result(
        self,
        facts: List,
        validation_results: List,
        valid_count: int,
        invalid_count: int,
        import_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build final import result (Issue #398: extracted)."""
        return {
            "status": "success",
            "total_facts": len(facts),
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "imported": import_results["imported"],
            "skipped": import_results["skipped"],
            "updated": import_results.get("updated", 0),
            "errors": import_results["errors"] + invalid_count,
            "import_results": import_results.get("per_fact_results", []),
            "validation_errors": [v for v in validation_results if not v["valid"]],
        }

    def _build_no_valid_facts_result(
        self, facts: List, invalid_count: int, validation_results: List
    ) -> Dict[str, Any]:
        """Build error result for no valid facts case (Issue #398: extracted)."""
        return {
            "status": "error", "message": "No valid facts to import",
            "total_facts": len(facts), "valid_count": 0,
            "invalid_count": invalid_count, "validation_results": validation_results,
        }

    async def import_facts(
        self, source_file: Optional[str] = None, data: Optional[str] = None,
        format: str = "json", skip_duplicates: bool = True, validate_only: bool = False,
        overwrite_existing: bool = False, default_category: str = "imported",
        min_content_length: int = 1, max_content_length: int = 100000,
    ) -> Dict[str, Any]:
        """Import facts from file or data string (Issue #398: refactored)."""
        try:
            content, error = await self._get_import_content(source_file, data)
            if error:
                return error

            facts, error = self._parse_import_data(content, format)
            if error:
                return error

            valid_facts, validation_results, valid_count, invalid_count = (
                self._validate_all_facts(facts, default_category, min_content_length, max_content_length)
            )

            if validate_only:
                return self._build_validation_only_result(facts, validation_results, valid_count, invalid_count)
            if not valid_facts:
                return self._build_no_valid_facts_result(facts, invalid_count, validation_results)

            import_results = await self._import_valid_facts(valid_facts, skip_duplicates, overwrite_existing)
            return self._build_import_result(facts, validation_results, valid_count, invalid_count, import_results)

        except json.JSONDecodeError as e:
            logger.error("JSON parse error during import: %s", e)
            return {"status": "error", "message": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.error("Import failed: %s", e)
            return {"status": "error", "message": str(e)}

    def _validate_fact_for_import(
        self,
        fact_data: Dict[str, Any],
        index: int,
        default_category: str,
        min_content_length: int,
        max_content_length: int,
    ) -> Dict[str, Any]:
        """
        Validate a single fact for import.

        Issue #416: Content and schema validation.

        Args:
            fact_data: Raw fact data from import
            index: Index in import file (for error reporting)
            default_category: Default category if not specified
            min_content_length: Minimum content length
            max_content_length: Maximum content length

        Returns:
            Dict with validation result and normalized fact
        """
        errors = []
        content, content_errors = self._validate_content(
            fact_data, min_content_length, max_content_length
        )
        errors.extend(content_errors)

        metadata, metadata_errors = self._normalize_metadata(
            fact_data, default_category
        )
        errors.extend(metadata_errors)

        fact_id = self._normalize_fact_id(fact_data)

        normalized_fact = {
            "content": content if isinstance(content, str) else "",
            "metadata": metadata,
        }
        if fact_id:
            normalized_fact["fact_id"] = fact_id

        return {
            "index": index,
            "valid": len(errors) == 0,
            "errors": errors,
            "normalized_fact": normalized_fact if not errors else None,
        }

    def _validate_content(
        self,
        fact_data: Dict[str, Any],
        min_length: int,
        max_length: int,
    ) -> tuple:
        """
        Validate content field.

        Issue #398: Extracted from _validate_fact_for_import.
        """
        errors = []
        content = fact_data.get("content", "")

        if not content or not isinstance(content, str):
            errors.append("Missing or invalid content field")
        elif len(content) < min_length:
            errors.append(f"Content too short (min: {min_length} chars)")
        elif len(content) > max_length:
            errors.append(f"Content too long (max: {max_length} chars)")

        return content, errors

    def _normalize_metadata(
        self,
        fact_data: Dict[str, Any],
        default_category: str,
    ) -> tuple:
        """
        Normalize metadata with category and tags.

        Issue #398: Extracted from _validate_fact_for_import.
        """
        errors = []
        metadata = fact_data.get("metadata", {})

        if not isinstance(metadata, dict):
            metadata = {}
            errors.append("Invalid metadata format, using default")

        if not metadata.get("category"):
            metadata["category"] = default_category

        metadata["tags"] = _normalize_tags(metadata.get("tags", []))

        return metadata, errors

    def _normalize_fact_id(self, fact_data: Dict[str, Any]) -> Optional[str]:
        """
        Normalize fact_id to string.

        Issue #398: Extracted from _validate_fact_for_import.
        """
        fact_id = fact_data.get("fact_id")
        if fact_id and not isinstance(fact_id, str):
            return str(fact_id)
        return fact_id

    async def _import_valid_facts(
        self,
        facts: List[Dict[str, Any]],
        skip_duplicates: bool,
        overwrite_existing: bool,
    ) -> Dict[str, Any]:
        """
        Import validated facts using parallel processing.

        Issue #416: Enhanced import with overwrite mode and per-fact tracking.
        Issue #398: Refactored using extracted helpers.

        Args:
            facts: List of validated facts to import
            skip_duplicates: Skip duplicate facts
            overwrite_existing: Overwrite existing facts

        Returns:
            Dict with import counts and per-fact results
        """
        semaphore = asyncio.Semaphore(50)

        results = await asyncio.gather(
            *[
                self._store_single_import_fact(
                    fact, semaphore, skip_duplicates, overwrite_existing
                )
                for fact in facts
            ],
            return_exceptions=True,
        )

        return self._count_import_results(results)

    async def _store_single_import_fact(
        self,
        fact_data: Dict[str, Any],
        semaphore: asyncio.Semaphore,
        skip_duplicates: bool,
        overwrite_existing: bool,
    ) -> Dict[str, Any]:
        """
        Store a single fact during import.

        Issue #398: Extracted from _import_valid_facts.
        """
        async with semaphore:
            try:
                fact_id = fact_data.get("fact_id")

                if fact_id:
                    existing_result = await self._handle_existing_fact(
                        fact_id, fact_data, skip_duplicates, overwrite_existing
                    )
                    if existing_result:
                        return existing_result

                result = await self.store_fact(
                    content=fact_data.get("content", ""),
                    metadata=fact_data.get("metadata", {}),
                    fact_id=fact_id,
                )

                return {
                    "fact_id": result.get("fact_id", fact_id),
                    "action": "imported",
                    "status": result.get("status", "error"),
                }

            except Exception as e:
                return {
                    "fact_id": fact_data.get("fact_id"),
                    "action": "error",
                    "status": "error",
                    "message": str(e),
                }

    async def _handle_existing_fact(
        self,
        fact_id: str,
        fact_data: Dict[str, Any],
        skip_duplicates: bool,
        overwrite_existing: bool,
    ) -> Optional[Dict[str, Any]]:
        """
        Handle import when fact already exists.

        Issue #398: Extracted from _import_valid_facts.

        Returns:
            Result dict if handled, None to continue with new store.
        """
        exists = await self._fact_exists(fact_id)
        if not exists:
            return None

        if overwrite_existing:
            result = await self.update_fact(
                fact_id,
                content=fact_data.get("content"),
                metadata=fact_data.get("metadata"),
            )
            return {
                "fact_id": fact_id,
                "action": "updated",
                "status": result.get("status", "error"),
            }
        elif skip_duplicates:
            return {
                "fact_id": fact_id,
                "action": "skipped",
                "status": "duplicate",
            }
        else:
            return {
                "fact_id": fact_id,
                "action": "error",
                "status": "error",
                "message": "Fact already exists",
            }

    def _count_import_results(self, results: List[Any]) -> Dict[str, Any]:
        """
        Count import results by action type.

        Issue #398: Extracted from _import_valid_facts.
        """
        imported = 0
        skipped = 0
        updated = 0
        errors = 0
        per_fact_results = []

        for result in results:
            if isinstance(result, Exception):
                errors += 1
                per_fact_results.append({
                    "action": "error",
                    "status": "error",
                    "message": str(result),
                })
            else:
                per_fact_results.append(result)
                action = result.get("action")
                status = result.get("status")

                if action == "imported" and status == "success":
                    imported += 1
                elif action == "updated" and status == "success":
                    updated += 1
                elif action == "skipped":
                    skipped += 1
                else:
                    errors += 1

        return {
            "imported": imported,
            "skipped": skipped,
            "updated": updated,
            "errors": errors,
            "per_fact_results": per_fact_results,
        }

    async def _fact_exists(self, fact_id: str) -> bool:
        """
        Check if a fact with the given ID exists.

        Issue #416: Helper for duplicate/overwrite handling.
        """
        try:
            fact_key = f"fact:{fact_id}"
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            return bool(exists)
        except Exception:
            return False

    def _parse_import_json(self, content: str) -> List[Dict[str, Any]]:
        """Parse JSON import format"""
        data = json.loads(content)
        return data if isinstance(data, list) else [data]

    def _parse_import_csv(self, content: str) -> List[Dict[str, Any]]:
        """Parse CSV import format"""
        reader = csv.DictReader(StringIO(content))
        facts = []
        for row in reader:
            facts.append(
                {
                    "fact_id": row.get("fact_id"),
                    "content": row.get("content", ""),
                    "metadata": {
                        "category": row.get("category", "general"),
                        "tags": [t.strip() for t in row.get("tags", "").split(",") if t.strip()],
                    },
                }
            )
        return facts

    def _build_empty_duplicates_result(self, use_embeddings: bool) -> Dict[str, Any]:
        """Build empty result for no facts case (Issue #398: extracted)."""
        return {
            "status": "success", "duplicates_found": 0, "duplicate_groups": [],
            "method": "embedding" if use_embeddings else "hash",
        }

    async def find_duplicates(
        self, similarity_threshold: float = 0.95, use_embeddings: bool = False,
        category: Optional[str] = None, max_results: int = 100,
    ) -> Dict[str, Any]:
        """Find duplicate facts by hash or embedding similarity (Issue #398: refactored)."""
        try:
            facts = await self.get_all_facts()
            facts = self._apply_category_filter(facts, category)

            if not facts:
                return self._build_empty_duplicates_result(use_embeddings)

            duplicate_groups = (
                await self._find_duplicates_by_embedding(facts, similarity_threshold, max_results)
                if use_embeddings else self._find_duplicates_by_hash(facts)
            )

            return {
                "status": "success", "duplicates_found": len(duplicate_groups),
                "duplicate_groups": duplicate_groups[:max_results],
                "method": "embedding" if use_embeddings else "hash",
                "threshold": similarity_threshold, "total_facts_analyzed": len(facts),
            }

        except Exception as e:
            logger.error("Duplicate detection failed: %s", e)
            return {"status": "error", "message": str(e)}

    def _find_duplicates_by_hash(
        self, facts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find exact duplicates by content hash.

        Fast but only catches exact matches.
        """
        # Group facts by content hash
        hash_groups: Dict[int, List[Dict[str, Any]]] = {}

        for fact in facts:
            content_hash = hash(fact.get("content", ""))
            if content_hash not in hash_groups:
                hash_groups[content_hash] = []
            hash_groups[content_hash].append({
                "fact_id": fact.get("fact_id"),
                "content_preview": fact.get("content", "")[:100],
            })

        # Extract groups with duplicates
        duplicate_groups = []
        for content_hash, group in hash_groups.items():
            if len(group) > 1:
                duplicate_groups.append({
                    "similarity": 1.0,  # Exact match
                    "facts": group,
                    "reason": "exact_content_match",
                })

        return duplicate_groups

    async def _find_duplicates_by_embedding(
        self,
        facts: List[Dict[str, Any]],
        similarity_threshold: float,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """
        Find semantic duplicates using vector embeddings.

        Issue #417: Embedding-based similarity detection.
        Issue #398: Refactored using extracted helpers.
        """
        if not hasattr(self, "vector_store") or self.vector_store is None:
            logger.warning("Vector store not available, falling back to hash")
            return self._find_duplicates_by_hash(facts)

        try:
            fact_ids = [f.get("fact_id") for f in facts if f.get("fact_id")]
            if len(fact_ids) < 2:
                return []

            embeddings_map = await self._fetch_embeddings_map(fact_ids)
            if not embeddings_map:
                return self._find_duplicates_by_hash(facts)

            fact_info = self._build_fact_info_map(facts)
            duplicate_groups = self._find_similar_pairs(
                fact_ids, embeddings_map, fact_info, similarity_threshold, max_results
            )

            duplicate_groups.sort(key=lambda x: x["max_similarity"], reverse=True)
            return duplicate_groups

        except Exception as e:
            logger.error("Embedding-based duplicate detection failed: %s", e)
            return self._find_duplicates_by_hash(facts)

    async def _fetch_embeddings_map(
        self, fact_ids: List[str]
    ) -> Dict[str, List[float]]:
        """
        Fetch embeddings from vector store.

        Issue #398: Extracted from _find_duplicates_by_embedding.
        """
        result = await asyncio.to_thread(
            self.vector_store.get,
            ids=fact_ids,
            include=["embeddings"],
        )

        if not result or not result.get("embeddings"):
            logger.warning("No embeddings found, falling back to hash")
            return {}

        return dict(zip(result["ids"], result["embeddings"]))

    def _build_fact_info_map(
        self, facts: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build fact info lookup map.

        Issue #398: Extracted from _find_duplicates_by_embedding.
        """
        return {
            f.get("fact_id"): {
                "fact_id": f.get("fact_id"),
                "content_preview": f.get("content", "")[:100],
                "category": f.get("metadata", {}).get("category"),
            }
            for f in facts
        }

    def _find_similar_pairs(
        self,
        fact_ids: List[str],
        embeddings_map: Dict[str, List[float]],
        fact_info: Dict[str, Dict[str, Any]],
        threshold: float,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """
        Find similar fact pairs using cosine similarity.

        Issue #398: Extracted from _find_duplicates_by_embedding.
        """
        duplicate_groups = []
        processed_pairs: set = set()

        for i, fact_id1 in enumerate(fact_ids):
            if fact_id1 not in embeddings_map:
                continue

            similar_facts = self._find_similar_to_fact(
                fact_id1, fact_ids[i + 1:], embeddings_map, fact_info,
                threshold, processed_pairs
            )

            if similar_facts:
                duplicate_groups.append({
                    "primary_fact": fact_info.get(fact_id1, {"fact_id": fact_id1}),
                    "similar_facts": sorted(
                        similar_facts, key=lambda x: x["similarity"], reverse=True
                    ),
                    "max_similarity": max(f["similarity"] for f in similar_facts),
                    "reason": "semantic_similarity",
                })

                if len(duplicate_groups) >= max_results:
                    break

        return duplicate_groups

    def _find_similar_to_fact(
        self,
        fact_id1: str,
        other_ids: List[str],
        embeddings_map: Dict[str, List[float]],
        fact_info: Dict[str, Dict[str, Any]],
        threshold: float,
        processed_pairs: set,
    ) -> List[Dict[str, Any]]:
        """
        Find facts similar to a given fact.

        Issue #398: Extracted from _find_duplicates_by_embedding.
        """
        similar_facts = []
        emb1 = embeddings_map[fact_id1]

        for fact_id2 in other_ids:
            if fact_id2 not in embeddings_map:
                continue

            pair_key = tuple(sorted([fact_id1, fact_id2]))
            if pair_key in processed_pairs:
                continue
            processed_pairs.add(pair_key)

            similarity = self._cosine_similarity(emb1, embeddings_map[fact_id2])
            if similarity >= threshold:
                similar_facts.append({
                    "fact_id": fact_id2,
                    "similarity": round(similarity, 4),
                    **fact_info.get(fact_id2, {}),
                })

        return similar_facts

    def _cosine_similarity(
        self, vec1: List[float], vec2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two vectors.

        Issue #417: Helper for embedding-based deduplication.
        """
        try:
            # Convert to numpy if available, otherwise use pure Python
            try:
                import numpy as np
                v1 = np.array(vec1)
                v2 = np.array(vec2)
                dot_product = np.dot(v1, v2)
                norm1 = np.linalg.norm(v1)
                norm2 = np.linalg.norm(v2)
                if norm1 == 0 or norm2 == 0:
                    return 0.0
                return float(dot_product / (norm1 * norm2))
            except ImportError:
                # Pure Python fallback
                dot_product = sum(a * b for a, b in zip(vec1, vec2))
                norm1 = sum(a * a for a in vec1) ** 0.5
                norm2 = sum(b * b for b in vec2) ** 0.5
                if norm1 == 0 or norm2 == 0:
                    return 0.0
                return dot_product / (norm1 * norm2)
        except Exception:
            return 0.0

    async def bulk_delete(self, fact_ids: List[str]) -> Dict[str, Any]:
        """
        Delete multiple facts in bulk using parallel processing.

        Args:
            fact_ids: List of fact IDs to delete

        Returns:
            Dict with status and counts
        """
        try:
            # Process all deletions in parallel with bounded concurrency
            semaphore = asyncio.Semaphore(50)

            async def bounded_delete(fact_id: str) -> Dict[str, Any]:
                """Delete fact with concurrency limit."""
                async with semaphore:
                    try:
                        return await self.delete_fact(fact_id)
                    except Exception as e:
                        return {"status": "error", "message": str(e)}

            results = await asyncio.gather(
                *[bounded_delete(fact_id) for fact_id in fact_ids],
                return_exceptions=True
            )

            # Count results
            deleted = 0
            errors = 0

            for result in results:
                if isinstance(result, Exception):
                    errors += 1
                elif result.get("status") == "success":
                    deleted += 1
                else:
                    errors += 1

            return {
                "status": "success",
                "deleted": deleted,
                "errors": errors,
                "total": len(fact_ids),
            }

        except Exception as e:
            logger.error("Bulk delete failed: %s", e)
            return {"status": "error", "message": str(e)}

    def _count_bulk_update_results(self, results: List[Any]) -> tuple[int, int]:
        """Count bulk update results (Issue #398: extracted)."""
        updated = errors = 0
        for result in results:
            if isinstance(result, Exception) or result.get("status") != "success":
                errors += 1
            else:
                updated += 1
        return updated, errors

    async def bulk_update_category(self, fact_ids: List[str], new_category: str) -> Dict[str, Any]:
        """Update category for multiple facts using parallel processing (Issue #398: refactored)."""
        try:
            semaphore = asyncio.Semaphore(50)

            async def bounded_update(fact_id: str) -> Dict[str, Any]:
                async with semaphore:
                    try:
                        return await self.update_fact(fact_id, metadata={"category": new_category})
                    except Exception as e:
                        return {"status": "error", "message": str(e)}

            results = await asyncio.gather(*[bounded_update(fid) for fid in fact_ids], return_exceptions=True)
            updated, errors = self._count_bulk_update_results(results)

            return {"status": "success", "updated": updated, "errors": errors, "total": len(fact_ids)}

        except Exception as e:
            logger.error("Bulk category update failed: %s", e)
            return {"status": "error", "message": str(e)}

    async def cleanup(
        self, remove_orphaned_vectors: bool = True, verify_integrity: bool = True
    ) -> Dict[str, Any]:
        """
        Cleanup knowledge base (remove orphaned data, verify integrity).

        Args:
            remove_orphaned_vectors: Remove vectors without Redis facts
            verify_integrity: Verify data integrity

        Returns:
            Dict with cleanup results
        """
        try:
            results = {"removed_vectors": 0, "verified_facts": 0, "errors": []}

            # Verify stats consistency if requested
            if verify_integrity:
                consistency = await self._verify_stats_consistency(auto_correct=True)
                results["stats_consistency"] = consistency

            return {"status": "success", "results": results}

        except Exception as e:
            logger.error("Cleanup failed: %s", e)
            return {"status": "error", "message": str(e)}

    # Method references needed from other mixins
    async def get_all_facts(self):
        """Get all facts - implemented in facts mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def store_fact(self, content: str, metadata: Dict[str, Any], fact_id: str):
        """Store fact - implemented in facts mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def delete_fact(self, fact_id: str):
        """Delete fact - implemented in facts mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def update_fact(self, fact_id: str, **kwargs):
        """Update fact - implemented in facts mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def _verify_stats_consistency(self, auto_correct: bool = True):
        """Verify stats consistency - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    # ===== BACKUP AND RESTORE OPERATIONS (Issue #419) =====

    def _build_backup_success_result(
        self, backup_name: str, backup_file: str, facts: List, file_size: int,
        include_embeddings: bool, compression: bool, created_at: str
    ) -> Dict[str, Any]:
        """Build successful backup result (Issue #398: extracted)."""
        return {
            "status": "success", "backup_file": backup_file, "backup_name": backup_name,
            "facts_count": len(facts), "file_size": file_size,
            "include_embeddings": include_embeddings, "compression": compression, "created_at": created_at,
        }

    async def create_backup(
        self, backup_dir: Optional[str] = None, include_embeddings: bool = True,
        include_metadata: bool = True, compression: bool = True, description: str = "",
    ) -> Dict[str, Any]:
        """Create a full backup of the knowledge base (Issue #398: refactored)."""
        import os

        try:
            backup_dir = self._get_backup_dir(backup_dir)
            os.makedirs(backup_dir, exist_ok=True)

            backup_name, backup_file = self._generate_backup_path(backup_dir, compression)
            logger.info("Creating backup: %s", backup_file)

            facts = await self.get_all_facts()
            if include_embeddings:
                facts = await self._add_embeddings_to_facts(facts)

            backup_data = await self._build_backup_data(facts, description, include_embeddings, include_metadata)
            await self._write_backup_file(backup_file, backup_data, compression)

            file_size = os.path.getsize(backup_file)
            logger.info("Backup created: %s (%d facts, %d bytes)", backup_file, len(facts), file_size)

            return self._build_backup_success_result(
                backup_name, backup_file, facts, file_size,
                include_embeddings, compression, backup_data["created_at"]
            )

        except Exception as e:
            logger.error("Backup failed: %s", e)
            return {"status": "error", "message": str(e)}

    def _get_backup_dir(self, backup_dir: Optional[str]) -> str:
        """
        Get backup directory path.

        Issue #398: Extracted from create_backup.
        """
        if backup_dir:
            return backup_dir
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        return str(project_root / "backups" / "knowledge")

    def _generate_backup_path(
        self, backup_dir: str, compression: bool
    ) -> tuple:
        """
        Generate backup filename and path.

        Issue #398: Extracted from create_backup.
        """
        import os
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"kb_backup_{timestamp}"
        ext = ".jsongz" if compression else ".json"
        backup_file = os.path.join(backup_dir, f"{backup_name}{ext}")
        return backup_name, backup_file

    async def _build_backup_data(
        self,
        facts: List[Dict[str, Any]],
        description: str,
        include_embeddings: bool,
        include_metadata: bool,
    ) -> Dict[str, Any]:
        """
        Build backup data structure.

        Issue #398: Extracted from create_backup.
        """
        backup_data = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "description": description,
            "facts_count": len(facts),
            "include_embeddings": include_embeddings,
            "facts": facts,
        }

        if include_metadata:
            backup_data["metadata"] = await self._get_backup_metadata()

        return backup_data

    async def _get_backup_metadata(self) -> Dict[str, Any]:
        """
        Get metadata for backup.

        Issue #398: Extracted from create_backup.
        """
        try:
            stats = await self.get_stats()
            return {
                "total_facts": stats.get("total_facts", 0),
                "total_vectors": stats.get("total_vectors", 0),
                "categories": stats.get("categories", []),
                "db_size": stats.get("db_size", 0),
            }
        except Exception as e:
            logger.warning("Could not include metadata: %s", e)
            return {}

    async def _write_backup_file(
        self, backup_file: str, backup_data: Dict[str, Any], compression: bool
    ) -> None:
        """
        Write backup data to file.

        Issue #398: Extracted from create_backup.
        """
        json_data = json.dumps(backup_data, ensure_ascii=False, indent=2)

        if compression:
            await asyncio.to_thread(self._write_gzip_file, backup_file, json_data)
        else:
            await asyncio.to_thread(_write_file_sync, backup_file, json_data)

    def _write_gzip_file(self, filepath: str, content: str) -> None:
        """Write content to gzip-compressed file (Issue #419)."""
        import gzip

        with gzip.open(filepath, "wt", encoding="utf-8") as f:
            f.write(content)

    def _read_gzip_file(self, filepath: str) -> str:
        """Read content from gzip-compressed file (Issue #419)."""
        import gzip

        with gzip.open(filepath, "rt", encoding="utf-8") as f:
            return f.read()

    async def restore_backup(
        self,
        backup_file: str,
        overwrite_existing: bool = False,
        skip_duplicates: bool = True,
        restore_embeddings: bool = True,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Restore knowledge base from a backup file.

        Issue #419: Backup and restore functionality.
        Issue #398: Refactored using extracted helpers.
        """
        import os

        try:
            if not os.path.exists(backup_file):
                return {
                    "status": "error",
                    "message": f"Backup file not found: {backup_file}"
                }

            logger.info("Restoring from backup: %s (dry_run=%s)", backup_file, dry_run)

            backup_data = await self._read_backup_file(backup_file)
            validation = self._validate_backup_data(backup_data)
            if validation:
                return validation

            if dry_run:
                return self._build_dry_run_response(backup_data)

            results = await self._restore_facts_from_backup(
                backup_data.get("facts", []),
                overwrite_existing,
                skip_duplicates,
                restore_embeddings and backup_data.get("include_embeddings", False),
            )

            return self._build_restore_response(backup_data, results)

        except json.JSONDecodeError as e:
            logger.error("Invalid backup JSON: %s", e)
            return {"status": "error", "message": f"Invalid backup JSON: {e}"}
        except Exception as e:
            logger.error("Restore failed: %s", e)
            return {"status": "error", "message": str(e)}

    async def _read_backup_file(self, backup_file: str) -> Dict[str, Any]:
        """
        Read and parse backup file.

        Issue #398: Extracted from restore_backup.
        """
        if backup_file.endswith(".gz") or backup_file.endswith(".jsongz"):
            content = await asyncio.to_thread(self._read_gzip_file, backup_file)
        else:
            content = await asyncio.to_thread(_read_file_sync, backup_file)
        return json.loads(content)

    def _validate_backup_data(
        self, backup_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Validate backup data format.

        Issue #398: Extracted from restore_backup.

        Returns:
            Error dict if invalid, None if valid.
        """
        if "version" not in backup_data or "facts" not in backup_data:
            return {"status": "error", "message": "Invalid backup format"}

        logger.info(
            "Backup info: version=%s, facts=%d, created_at=%s",
            backup_data.get("version", "unknown"),
            len(backup_data.get("facts", [])),
            backup_data.get("created_at", "unknown"),
        )
        return None

    def _build_dry_run_response(
        self, backup_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build dry run response with preview.

        Issue #398: Extracted from restore_backup.
        """
        facts = backup_data.get("facts", [])
        return {
            "status": "success",
            "mode": "dry_run",
            "backup_version": backup_data.get("version", "unknown"),
            "backup_created_at": backup_data.get("created_at", "unknown"),
            "total_facts_in_backup": len(facts),
            "has_embeddings": backup_data.get("include_embeddings", False),
            "metadata": backup_data.get("metadata", {}),
            "preview": [
                {
                    "fact_id": f.get("fact_id"),
                    "content_preview": f.get("content", "")[:100],
                    "category": f.get("metadata", {}).get("category"),
                }
                for f in facts[:10]
            ],
        }

    def _build_restore_response(
        self, backup_data: Dict[str, Any], results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build restore response.

        Issue #398: Extracted from restore_backup.
        """
        return {
            "status": "success",
            "mode": "restore",
            "backup_version": backup_data.get("version", "unknown"),
            "backup_created_at": backup_data.get("created_at", "unknown"),
            "total_facts_in_backup": len(backup_data.get("facts", [])),
            "restored": results["restored"],
            "skipped": results["skipped"],
            "updated": results["updated"],
            "errors": results["errors"],
            "embeddings_restored": results.get("embeddings_restored", 0),
        }

    async def _restore_facts_from_backup(
        self,
        facts: List[Dict[str, Any]],
        overwrite_existing: bool,
        skip_duplicates: bool,
        restore_embeddings: bool,
    ) -> Dict[str, Any]:
        """
        Restore facts from backup data.

        Issue #419: Helper for backup restore.
        Issue #398: Refactored using extracted helpers.
        """
        semaphore = asyncio.Semaphore(50)

        restore_results = await asyncio.gather(
            *[
                self._restore_single_backup_fact(
                    fact, semaphore, overwrite_existing,
                    skip_duplicates, restore_embeddings
                )
                for fact in facts
            ],
            return_exceptions=True,
        )

        return self._count_restore_results(restore_results)

    async def _restore_single_backup_fact(
        self,
        fact_data: Dict[str, Any],
        semaphore: asyncio.Semaphore,
        overwrite_existing: bool,
        skip_duplicates: bool,
        restore_embeddings: bool,
    ) -> Dict[str, Any]:
        """
        Restore a single fact from backup.

        Issue #398: Extracted from _restore_facts_from_backup.
        """
        async with semaphore:
            try:
                fact_id = fact_data.get("fact_id")
                content = fact_data.get("content", "")
                metadata = fact_data.get("metadata", {})

                if not content:
                    return {"action": "error", "reason": "empty_content"}

                if fact_id:
                    existing_result = await self._handle_existing_restore(
                        fact_id, content, metadata, overwrite_existing, skip_duplicates
                    )
                    if existing_result:
                        return existing_result

                return await self._store_restored_fact(
                    fact_data, content, metadata, fact_id, restore_embeddings
                )

            except Exception as e:
                return {"action": "error", "reason": str(e)}

    async def _handle_existing_restore(
        self,
        fact_id: str,
        content: str,
        metadata: Dict[str, Any],
        overwrite_existing: bool,
        skip_duplicates: bool,
    ) -> Optional[Dict[str, Any]]:
        """
        Handle restore when fact exists.

        Issue #398: Extracted from _restore_single_backup_fact.
        """
        exists = await self._fact_exists(fact_id)
        if not exists:
            return None

        if overwrite_existing:
            result = await self.update_fact(fact_id, content=content, metadata=metadata)
            if result.get("status") == "success":
                return {"action": "updated"}
            return {"action": "error", "reason": "update_failed"}

        if skip_duplicates:
            return {"action": "skipped", "reason": "duplicate"}

        return {"action": "error", "reason": "already_exists"}

    async def _store_restored_fact(
        self,
        fact_data: Dict[str, Any],
        content: str,
        metadata: Dict[str, Any],
        fact_id: Optional[str],
        restore_embeddings: bool,
    ) -> Dict[str, Any]:
        """
        Store a restored fact and optionally its embedding.

        Issue #398: Extracted from _restore_single_backup_fact.
        """
        result = await self.store_fact(content=content, metadata=metadata, fact_id=fact_id)

        if result.get("status") != "success":
            return {"action": "error", "reason": "store_failed"}

        embedding = fact_data.get("embedding")
        if restore_embeddings and embedding and self.vector_store:
            return await self._restore_fact_embedding(
                result.get("fact_id", fact_id), content, embedding
            )

        return {"action": "restored", "embedding": False}

    async def _restore_fact_embedding(
        self, fact_id: str, content: str, embedding: List[float]
    ) -> Dict[str, Any]:
        """
        Restore embedding for a fact.

        Issue #398: Extracted from _store_restored_fact.
        """
        try:
            await asyncio.to_thread(
                self.vector_store.upsert,
                ids=[fact_id],
                embeddings=[embedding],
                metadatas=[{"content": content[:1000]}],
                documents=[content[:1000]],
            )
            return {"action": "restored", "embedding": True}
        except Exception as e:
            logger.warning("Embedding restore failed: %s", e)
            return {"action": "restored", "embedding": False}

    def _count_restore_results(self, restore_results: List[Any]) -> Dict[str, Any]:
        """
        Count restore results by action type.

        Issue #398: Extracted from _restore_facts_from_backup.
        """
        results = {
            "restored": 0,
            "skipped": 0,
            "updated": 0,
            "errors": 0,
            "embeddings_restored": 0,
        }

        for result in restore_results:
            if isinstance(result, Exception):
                results["errors"] += 1
            else:
                action = result.get("action")
                if action == "restored":
                    results["restored"] += 1
                    if result.get("embedding"):
                        results["embeddings_restored"] += 1
                elif action == "updated":
                    results["updated"] += 1
                elif action == "skipped":
                    results["skipped"] += 1
                else:
                    results["errors"] += 1

        return results

    def _is_valid_backup_file(self, filename: str) -> bool:
        """Check if filename is a valid backup file (Issue #398: extracted)."""
        return filename.startswith("kb_backup_") and (
            filename.endswith(".json")
            or filename.endswith(".jsongz")
            or filename.endswith(".json.gz")
        )

    def _scan_backup_files(self, backup_dir: str) -> List[Dict[str, Any]]:
        """Scan directory for backup files (Issue #398: extracted)."""
        import os
        backups = []
        for filename in os.listdir(backup_dir):
            if self._is_valid_backup_file(filename):
                filepath = os.path.join(backup_dir, filename)
                stat = os.stat(filepath)
                backups.append({
                    "filename": filename,
                    "filepath": filepath,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "compressed": filename.endswith("gz"),
                })
        return backups

    async def list_backups(
        self, backup_dir: Optional[str] = None, limit: int = 50
    ) -> Dict[str, Any]:
        """List available backups (Issue #398: refactored)."""
        import os

        try:
            backup_dir = self._get_backup_dir(backup_dir)

            if not os.path.exists(backup_dir):
                return {"status": "success", "backup_dir": backup_dir, "backups": [], "total_count": 0}

            backups = await asyncio.to_thread(self._scan_backup_files, backup_dir)
            backups.sort(key=lambda x: x["created_at"], reverse=True)

            return {
                "status": "success", "backup_dir": backup_dir,
                "backups": backups[:limit], "total_count": len(backups),
            }

        except Exception as e:
            logger.error("Failed to list backups: %s", e)
            return {"status": "error", "message": str(e)}

    async def delete_backup(
        self,
        backup_file: str,
    ) -> Dict[str, Any]:
        """
        Delete a backup file.

        Issue #419: Backup and restore functionality.

        Args:
            backup_file: Path to backup file to delete

        Returns:
            Dict with deletion status
        """
        import os

        try:
            if not os.path.exists(backup_file):
                return {"status": "error", "message": f"Backup file not found: {backup_file}"}

            # Validate it's a backup file
            filename = os.path.basename(backup_file)
            if not filename.startswith("kb_backup_"):
                return {"status": "error", "message": "Not a valid backup file"}

            # Delete the file
            await asyncio.to_thread(os.remove, backup_file)

            logger.info("Backup deleted: %s", backup_file)

            return {
                "status": "success",
                "deleted_file": backup_file,
            }

        except Exception as e:
            logger.error("Failed to delete backup: %s", e)
            return {"status": "error", "message": str(e)}

    async def get_stats(self) -> Dict[str, Any]:
        """Get stats - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")
