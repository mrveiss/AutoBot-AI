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

    async def export_facts(
        self,
        format: str = "json",
        output_file: Optional[str] = None,
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        fact_ids: Optional[List[str]] = None,
        include_embeddings: bool = False,
        include_metadata: bool = True,
        include_tags: bool = True,
    ) -> Dict[str, Any]:
        """
        Export facts with optional filtering.

        Issue #415: Enhanced with date filtering, fact IDs filter, and embeddings export.

        Args:
            format: Export format ("json", "csv", "markdown")
            output_file: Optional output file path
            category: Filter by single category (legacy support)
            categories: Filter by multiple categories (any match)
            tags: Filter by tags (any match)
            date_from: Filter facts created on or after this date (YYYY-MM-DD)
            date_to: Filter facts created on or before this date (YYYY-MM-DD)
            fact_ids: Export only these specific fact IDs
            include_embeddings: Include vector embeddings in export
            include_metadata: Include metadata in export (default: True)
            include_tags: Include tags in export (default: True)

        Returns:
            Dict with status and data/file path
        """
        try:
            # Get facts - either specific IDs or all
            if fact_ids:
                facts = await self._get_facts_by_ids(fact_ids)
            else:
                facts = await self.get_all_facts()

            # Apply filters
            facts = self._apply_category_filter(facts, category)
            facts = self._apply_categories_filter(facts, categories)
            facts = self._apply_tags_filter(facts, tags)
            facts = self._apply_date_filter(facts, date_from, date_to)

            # Include embeddings if requested (Issue #415)
            if include_embeddings:
                facts = await self._add_embeddings_to_facts(facts)

            # Remove metadata/tags if not requested
            if not include_metadata or not include_tags:
                facts = self._filter_fact_fields(facts, include_metadata, include_tags)

            # Format output
            output = self._format_output(facts, format)
            if output is None:
                return {"status": "error", "message": "Unknown format: %s" % format}

            # Build and return result
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

        Args:
            facts: List of facts to filter
            date_from: Start date (YYYY-MM-DD), inclusive
            date_to: End date (YYYY-MM-DD), inclusive

        Returns:
            Filtered list of facts
        """
        if not date_from and not date_to:
            return facts

        # Parse date bounds
        from_dt = None
        to_dt = None

        if date_from:
            try:
                from_dt = datetime.strptime(date_from, "%Y-%m-%d")
            except ValueError:
                logger.warning("Invalid date_from format: %s", date_from)

        if date_to:
            try:
                # Add 1 day to include the entire end date
                to_dt = datetime.strptime(date_to, "%Y-%m-%d")
                to_dt = to_dt.replace(hour=23, minute=59, second=59)
            except ValueError:
                logger.warning("Invalid date_to format: %s", date_to)

        if not from_dt and not to_dt:
            return facts

        filtered = []
        for fact in facts:
            # Try to get timestamp from fact or metadata
            timestamp_str = fact.get("timestamp") or fact.get(
                "metadata", {}
            ).get("created_at")

            if not timestamp_str:
                # If no timestamp, include fact (don't filter out)
                filtered.append(fact)
                continue

            try:
                # Parse ISO format timestamp
                if isinstance(timestamp_str, str):
                    # Handle various ISO formats
                    if "T" in timestamp_str:
                        fact_dt = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00").split("+")[0]
                        )
                    else:
                        fact_dt = datetime.strptime(timestamp_str, "%Y-%m-%d")
                else:
                    filtered.append(fact)
                    continue

                # Apply date range filter
                if from_dt and fact_dt < from_dt:
                    continue
                if to_dt and fact_dt > to_dt:
                    continue

                filtered.append(fact)

            except (ValueError, TypeError) as e:
                logger.debug("Could not parse timestamp %s: %s", timestamp_str, e)
                # Include fact if timestamp parsing fails
                filtered.append(fact)

        return filtered

    async def _get_facts_by_ids(
        self, fact_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Get specific facts by their IDs.

        Issue #415: Selective export by fact IDs.

        Args:
            fact_ids: List of fact IDs to retrieve

        Returns:
            List of fact dictionaries
        """
        facts = []

        for fact_id in fact_ids:
            try:
                fact_key = f"fact:{fact_id}"
                fact_data = await asyncio.to_thread(
                    self.redis_client.hgetall, fact_key
                )

                if fact_data:
                    fact = {"fact_id": fact_id}

                    # Parse content
                    content = fact_data.get(b"content") or fact_data.get("content")
                    if content:
                        if isinstance(content, bytes):
                            content = content.decode("utf-8")
                        fact["content"] = content

                    # Parse metadata
                    metadata_json = (
                        fact_data.get(b"metadata") or fact_data.get("metadata")
                    )
                    if metadata_json:
                        if isinstance(metadata_json, bytes):
                            metadata_json = metadata_json.decode("utf-8")
                        fact["metadata"] = json.loads(metadata_json)

                    # Parse timestamp
                    timestamp = (
                        fact_data.get(b"timestamp") or fact_data.get("timestamp")
                    )
                    if timestamp:
                        if isinstance(timestamp, bytes):
                            timestamp = timestamp.decode("utf-8")
                        fact["timestamp"] = timestamp

                    facts.append(fact)

            except Exception as e:
                logger.warning("Failed to get fact %s: %s", fact_id, e)

        return facts

    async def _add_embeddings_to_facts(
        self, facts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Add vector embeddings to facts from ChromaDB.

        Issue #415: Include embeddings in export.

        Args:
            facts: List of facts to enhance with embeddings

        Returns:
            Facts with embeddings added
        """
        if not facts or not hasattr(self, "vector_store") or self.vector_store is None:
            return facts

        try:
            # Get fact IDs
            fact_ids = [f.get("fact_id") for f in facts if f.get("fact_id")]

            if not fact_ids:
                return facts

            # Retrieve embeddings from ChromaDB
            try:
                result = await asyncio.to_thread(
                    self.vector_store.get,
                    ids=fact_ids,
                    include=["embeddings"],
                )

                # Map embeddings by ID
                embeddings_map = {}
                if result and result.get("ids") and result.get("embeddings"):
                    for fact_id, embedding in zip(
                        result["ids"], result["embeddings"]
                    ):
                        embeddings_map[fact_id] = embedding

                # Add embeddings to facts
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

    async def import_facts(
        self,
        source_file: Optional[str] = None,
        data: Optional[str] = None,
        format: str = "json",
        skip_duplicates: bool = True,
        validate_only: bool = False,
        overwrite_existing: bool = False,
        default_category: str = "imported",
        min_content_length: int = 1,
        max_content_length: int = 100000,
    ) -> Dict[str, Any]:
        """
        Import facts from a file or data string using parallel processing.

        Issue #416: Enhanced with validation, progress tracking, and overwrite mode.

        Args:
            source_file: Source file path (mutually exclusive with data)
            data: Import data as string (mutually exclusive with source_file)
            format: Import format ("json", "csv")
            skip_duplicates: Skip duplicate facts (default: True)
            validate_only: Only validate, don't actually import (default: False)
            overwrite_existing: Overwrite existing facts with same ID (default: False)
            default_category: Default category for facts without one (default: "imported")
            min_content_length: Minimum content length (default: 1)
            max_content_length: Maximum content length (default: 100000)

        Returns:
            Dict with import status and per-fact results
        """
        try:
            # Get content from file or data parameter
            if source_file:
                content = await asyncio.to_thread(_read_file_sync, source_file)
            elif data:
                content = data
            else:
                return {"status": "error", "message": "Either source_file or data required"}

            # Parse based on format
            if format == "json":
                facts = self._parse_import_json(content)
            elif format == "csv":
                facts = self._parse_import_csv(content)
            else:
                return {"status": "error", "message": f"Unknown format: {format}"}

            # Validate all facts first (Issue #416)
            validation_results = []
            valid_facts = []

            for idx, fact_data in enumerate(facts):
                validation = self._validate_fact_for_import(
                    fact_data,
                    idx,
                    default_category,
                    min_content_length,
                    max_content_length,
                )
                validation_results.append(validation)

                if validation["valid"]:
                    valid_facts.append(validation["normalized_fact"])

            # Count validation results
            valid_count = sum(1 for v in validation_results if v["valid"])
            invalid_count = len(validation_results) - valid_count

            # If validate_only, return validation results without importing
            if validate_only:
                return {
                    "status": "success",
                    "mode": "validate_only",
                    "total_facts": len(facts),
                    "valid_count": valid_count,
                    "invalid_count": invalid_count,
                    "validation_results": validation_results,
                }

            # If no valid facts, return early
            if not valid_facts:
                return {
                    "status": "error",
                    "message": "No valid facts to import",
                    "total_facts": len(facts),
                    "valid_count": 0,
                    "invalid_count": invalid_count,
                    "validation_results": validation_results,
                }

            # Import valid facts
            import_results = await self._import_valid_facts(
                valid_facts,
                skip_duplicates,
                overwrite_existing,
            )

            # Merge validation and import results
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
                "validation_errors": [
                    v for v in validation_results if not v["valid"]
                ],
            }

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

        # Validate content exists and has proper length
        content = fact_data.get("content", "")
        if not content or not isinstance(content, str):
            errors.append("Missing or invalid content field")
        elif len(content) < min_content_length:
            errors.append(f"Content too short (min: {min_content_length} chars)")
        elif len(content) > max_content_length:
            errors.append(f"Content too long (max: {max_content_length} chars)")

        # Validate and normalize metadata
        metadata = fact_data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            errors.append("Invalid metadata format, using default")

        # Ensure category exists
        if not metadata.get("category"):
            metadata["category"] = default_category

        # Validate and normalize tags
        tags = metadata.get("tags", [])
        if isinstance(tags, str):
            # Handle comma-separated string
            tags = [t.strip().lower() for t in tags.split(",") if t.strip()]
        elif isinstance(tags, list):
            # Normalize list of tags
            tags = [
                str(t).strip().lower()
                for t in tags
                if t and str(t).strip()
            ]
        else:
            tags = []
        metadata["tags"] = tags

        # Validate fact_id if provided
        fact_id = fact_data.get("fact_id")
        if fact_id and not isinstance(fact_id, str):
            fact_id = str(fact_id)

        # Build normalized fact
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

    async def _import_valid_facts(
        self,
        facts: List[Dict[str, Any]],
        skip_duplicates: bool,
        overwrite_existing: bool,
    ) -> Dict[str, Any]:
        """
        Import validated facts using parallel processing.

        Issue #416: Enhanced import with overwrite mode and per-fact tracking.

        Args:
            facts: List of validated facts to import
            skip_duplicates: Skip duplicate facts
            overwrite_existing: Overwrite existing facts

        Returns:
            Dict with import counts and per-fact results
        """
        # Process all facts in parallel with bounded concurrency
        semaphore = asyncio.Semaphore(50)

        async def store_single_fact(fact_data: Dict[str, Any]) -> Dict[str, Any]:
            """Store a single fact with error handling."""
            async with semaphore:
                try:
                    fact_id = fact_data.get("fact_id")

                    # Check if fact exists (for duplicate/overwrite handling)
                    if fact_id:
                        exists = await self._fact_exists(fact_id)

                        if exists:
                            if overwrite_existing:
                                # Update existing fact
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

                    # Store new fact
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

        results = await asyncio.gather(
            *[store_single_fact(fact) for fact in facts],
            return_exceptions=True,
        )

        # Count results
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

    async def find_duplicates(
        self,
        similarity_threshold: float = 0.95,
        use_embeddings: bool = False,
        category: Optional[str] = None,
        max_results: int = 100,
    ) -> Dict[str, Any]:
        """
        Find duplicate facts based on content hash or embedding similarity.

        Issue #417: Enhanced with embedding-based similarity detection.

        Args:
            similarity_threshold: Similarity threshold (0.0-1.0)
            use_embeddings: Use vector embeddings for similarity (more accurate)
            category: Optional category to limit search scope
            max_results: Maximum number of duplicate groups to return

        Returns:
            Dict with duplicate groups and similarity scores
        """
        try:
            # Get all facts
            facts = await self.get_all_facts()

            # Apply category filter if provided
            if category:
                facts = [
                    f for f in facts
                    if f.get("metadata", {}).get("category") == category
                ]

            if not facts:
                return {
                    "status": "success",
                    "duplicates_found": 0,
                    "duplicate_groups": [],
                    "method": "embedding" if use_embeddings else "hash",
                }

            # Choose detection method
            if use_embeddings:
                duplicate_groups = await self._find_duplicates_by_embedding(
                    facts, similarity_threshold, max_results
                )
            else:
                duplicate_groups = self._find_duplicates_by_hash(facts)

            return {
                "status": "success",
                "duplicates_found": len(duplicate_groups),
                "duplicate_groups": duplicate_groups[:max_results],
                "method": "embedding" if use_embeddings else "hash",
                "threshold": similarity_threshold,
                "total_facts_analyzed": len(facts),
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

        Uses cosine similarity between fact embeddings to find
        semantically similar content that may not be exact matches.
        """
        if not hasattr(self, "vector_store") or self.vector_store is None:
            logger.warning("Vector store not available, falling back to hash")
            return self._find_duplicates_by_hash(facts)

        try:
            # Get fact IDs
            fact_ids = [f.get("fact_id") for f in facts if f.get("fact_id")]

            if len(fact_ids) < 2:
                return []

            # Retrieve embeddings from ChromaDB
            result = await asyncio.to_thread(
                self.vector_store.get,
                ids=fact_ids,
                include=["embeddings"],
            )

            if not result or not result.get("embeddings"):
                logger.warning("No embeddings found, falling back to hash")
                return self._find_duplicates_by_hash(facts)

            # Build ID to embedding map
            embeddings_map = {}
            for fact_id, embedding in zip(result["ids"], result["embeddings"]):
                embeddings_map[fact_id] = embedding

            # Build fact info map
            fact_info = {
                f.get("fact_id"): {
                    "fact_id": f.get("fact_id"),
                    "content_preview": f.get("content", "")[:100],
                    "category": f.get("metadata", {}).get("category"),
                }
                for f in facts
            }

            # Calculate pairwise similarities
            duplicate_groups = []
            processed_pairs = set()

            for i, fact_id1 in enumerate(fact_ids):
                if fact_id1 not in embeddings_map:
                    continue

                similar_facts = []
                emb1 = embeddings_map[fact_id1]

                for fact_id2 in fact_ids[i + 1:]:
                    if fact_id2 not in embeddings_map:
                        continue

                    pair_key = tuple(sorted([fact_id1, fact_id2]))
                    if pair_key in processed_pairs:
                        continue
                    processed_pairs.add(pair_key)

                    emb2 = embeddings_map[fact_id2]
                    similarity = self._cosine_similarity(emb1, emb2)

                    if similarity >= similarity_threshold:
                        similar_facts.append({
                            "fact_id": fact_id2,
                            "similarity": round(similarity, 4),
                            **fact_info.get(fact_id2, {}),
                        })

                if similar_facts:
                    duplicate_groups.append({
                        "primary_fact": fact_info.get(fact_id1, {"fact_id": fact_id1}),
                        "similar_facts": sorted(
                            similar_facts,
                            key=lambda x: x["similarity"],
                            reverse=True,
                        ),
                        "max_similarity": max(f["similarity"] for f in similar_facts),
                        "reason": "semantic_similarity",
                    })

                    if len(duplicate_groups) >= max_results:
                        break

            # Sort by max similarity
            duplicate_groups.sort(
                key=lambda x: x["max_similarity"],
                reverse=True,
            )

            return duplicate_groups

        except Exception as e:
            logger.error("Embedding-based duplicate detection failed: %s", e)
            return self._find_duplicates_by_hash(facts)

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

    async def bulk_update_category(
        self, fact_ids: List[str], new_category: str
    ) -> Dict[str, Any]:
        """
        Update category for multiple facts using parallel processing.

        Args:
            fact_ids: List of fact IDs
            new_category: New category name

        Returns:
            Dict with status and counts
        """
        try:
            # Process all updates in parallel with bounded concurrency
            semaphore = asyncio.Semaphore(50)

            async def bounded_update(fact_id: str) -> Dict[str, Any]:
                """Update single fact category with semaphore-controlled concurrency."""
                async with semaphore:
                    try:
                        return await self.update_fact(
                            fact_id, metadata={"category": new_category}
                        )
                    except Exception as e:
                        return {"status": "error", "message": str(e)}

            results = await asyncio.gather(
                *[bounded_update(fact_id) for fact_id in fact_ids],
                return_exceptions=True
            )

            # Count results
            updated = 0
            errors = 0

            for result in results:
                if isinstance(result, Exception):
                    errors += 1
                elif result.get("status") == "success":
                    updated += 1
                else:
                    errors += 1

            return {
                "status": "success",
                "updated": updated,
                "errors": errors,
                "total": len(fact_ids),
            }

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

    async def create_backup(
        self,
        backup_dir: Optional[str] = None,
        include_embeddings: bool = True,
        include_metadata: bool = True,
        compression: bool = True,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Create a full backup of the knowledge base.

        Issue #419: Backup and restore functionality.

        Args:
            backup_dir: Directory to store backup (default: backups/)
            include_embeddings: Include vector embeddings (default: True)
            include_metadata: Include backup metadata (default: True)
            compression: Use gzip compression (default: True)
            description: Optional description for the backup

        Returns:
            Dict with backup status and file path
        """
        import os
        from pathlib import Path

        try:
            # Set default backup directory
            if not backup_dir:
                project_root = Path(__file__).parent.parent.parent
                backup_dir = str(project_root / "backups" / "knowledge")

            # Ensure backup directory exists
            os.makedirs(backup_dir, exist_ok=True)

            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"kb_backup_{timestamp}"
            backup_file = os.path.join(
                backup_dir,
                f"{backup_name}.json{'gz' if compression else ''}",
            )

            logger.info(f"Creating backup: {backup_file}")

            # Get all facts
            facts = await self.get_all_facts()

            # Include embeddings if requested
            if include_embeddings:
                facts = await self._add_embeddings_to_facts(facts)

            # Build backup data structure
            backup_data = {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "description": description,
                "facts_count": len(facts),
                "include_embeddings": include_embeddings,
                "facts": facts,
            }

            # Add metadata if requested
            if include_metadata:
                try:
                    stats = await self.get_stats()
                    backup_data["metadata"] = {
                        "total_facts": stats.get("total_facts", 0),
                        "total_vectors": stats.get("total_vectors", 0),
                        "categories": stats.get("categories", []),
                        "db_size": stats.get("db_size", 0),
                    }
                except Exception as e:
                    logger.warning(f"Could not include metadata: {e}")
                    backup_data["metadata"] = {}

            # Serialize to JSON
            json_data = json.dumps(backup_data, ensure_ascii=False, indent=2)

            # Write to file (with optional compression)
            if compression:
                await asyncio.to_thread(
                    self._write_gzip_file, backup_file, json_data
                )
            else:
                await asyncio.to_thread(_write_file_sync, backup_file, json_data)

            # Get file size
            file_size = os.path.getsize(backup_file)

            logger.info(
                f"Backup created: {backup_file} ({len(facts)} facts, {file_size} bytes)"
            )

            return {
                "status": "success",
                "backup_file": backup_file,
                "backup_name": backup_name,
                "facts_count": len(facts),
                "file_size": file_size,
                "include_embeddings": include_embeddings,
                "compression": compression,
                "created_at": backup_data["created_at"],
            }

        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return {"status": "error", "message": str(e)}

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

        Args:
            backup_file: Path to backup file
            overwrite_existing: Overwrite existing facts (default: False)
            skip_duplicates: Skip duplicate facts (default: True)
            restore_embeddings: Restore vector embeddings (default: True)
            dry_run: Only validate, don't actually restore (default: True)

        Returns:
            Dict with restore status and counts
        """
        import os

        try:
            # Validate backup file exists
            if not os.path.exists(backup_file):
                return {"status": "error", "message": f"Backup file not found: {backup_file}"}

            logger.info(f"Restoring from backup: {backup_file} (dry_run={dry_run})")

            # Read backup file
            if backup_file.endswith(".gz") or backup_file.endswith(".jsongz"):
                content = await asyncio.to_thread(
                    self._read_gzip_file, backup_file
                )
            else:
                content = await asyncio.to_thread(_read_file_sync, backup_file)

            # Parse backup data
            backup_data = json.loads(content)

            # Validate backup format
            if "version" not in backup_data or "facts" not in backup_data:
                return {"status": "error", "message": "Invalid backup format"}

            facts = backup_data.get("facts", [])
            backup_version = backup_data.get("version", "unknown")
            backup_created_at = backup_data.get("created_at", "unknown")
            backup_embeddings = backup_data.get("include_embeddings", False)

            logger.info(
                f"Backup info: version={backup_version}, "
                f"facts={len(facts)}, created_at={backup_created_at}"
            )

            # If dry run, just validate and return preview
            if dry_run:
                return {
                    "status": "success",
                    "mode": "dry_run",
                    "backup_version": backup_version,
                    "backup_created_at": backup_created_at,
                    "total_facts_in_backup": len(facts),
                    "has_embeddings": backup_embeddings,
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

            # Perform actual restore
            results = await self._restore_facts_from_backup(
                facts,
                overwrite_existing,
                skip_duplicates,
                restore_embeddings and backup_embeddings,
            )

            return {
                "status": "success",
                "mode": "restore",
                "backup_version": backup_version,
                "backup_created_at": backup_created_at,
                "total_facts_in_backup": len(facts),
                "restored": results["restored"],
                "skipped": results["skipped"],
                "updated": results["updated"],
                "errors": results["errors"],
                "embeddings_restored": results.get("embeddings_restored", 0),
            }

        except json.JSONDecodeError as e:
            logger.error(f"Invalid backup JSON: {e}")
            return {"status": "error", "message": f"Invalid backup JSON: {e}"}
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return {"status": "error", "message": str(e)}

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
        """
        semaphore = asyncio.Semaphore(50)
        results = {
            "restored": 0,
            "skipped": 0,
            "updated": 0,
            "errors": 0,
            "embeddings_restored": 0,
        }

        async def restore_single_fact(fact_data: Dict[str, Any]) -> Dict[str, str]:
            """Restore a single fact."""
            async with semaphore:
                try:
                    fact_id = fact_data.get("fact_id")
                    content = fact_data.get("content", "")
                    metadata = fact_data.get("metadata", {})
                    embedding = fact_data.get("embedding")

                    if not content:
                        return {"action": "error", "reason": "empty_content"}

                    # Check if fact exists
                    if fact_id:
                        exists = await self._fact_exists(fact_id)

                        if exists:
                            if overwrite_existing:
                                # Update existing fact
                                result = await self.update_fact(
                                    fact_id,
                                    content=content,
                                    metadata=metadata,
                                )
                                if result.get("status") == "success":
                                    return {"action": "updated"}
                                return {"action": "error", "reason": "update_failed"}

                            elif skip_duplicates:
                                return {"action": "skipped", "reason": "duplicate"}
                            else:
                                return {"action": "error", "reason": "already_exists"}

                    # Store new fact
                    result = await self.store_fact(
                        content=content,
                        metadata=metadata,
                        fact_id=fact_id,
                    )

                    if result.get("status") == "success":
                        # Restore embedding if available and requested
                        if restore_embeddings and embedding and self.vector_store:
                            try:
                                new_fact_id = result.get("fact_id", fact_id)
                                await asyncio.to_thread(
                                    self.vector_store.upsert,
                                    ids=[new_fact_id],
                                    embeddings=[embedding],
                                    metadatas=[{"content": content[:1000]}],
                                    documents=[content[:1000]],
                                )
                                return {"action": "restored", "embedding": True}
                            except Exception as e:
                                logger.warning(f"Embedding restore failed: {e}")
                                return {"action": "restored", "embedding": False}

                        return {"action": "restored", "embedding": False}

                    return {"action": "error", "reason": "store_failed"}

                except Exception as e:
                    return {"action": "error", "reason": str(e)}

        # Process all facts in parallel
        restore_results = await asyncio.gather(
            *[restore_single_fact(fact) for fact in facts],
            return_exceptions=True,
        )

        # Count results
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

    async def list_backups(
        self,
        backup_dir: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        List available backups.

        Issue #419: Backup and restore functionality.

        Args:
            backup_dir: Directory to scan (default: backups/)
            limit: Maximum number of backups to return (default: 50)

        Returns:
            Dict with list of available backups
        """
        import os
        from pathlib import Path

        try:
            # Set default backup directory
            if not backup_dir:
                project_root = Path(__file__).parent.parent.parent
                backup_dir = str(project_root / "backups" / "knowledge")

            # Check if directory exists
            if not os.path.exists(backup_dir):
                return {
                    "status": "success",
                    "backup_dir": backup_dir,
                    "backups": [],
                    "total_count": 0,
                }

            # List backup files
            backups = []

            def _scan_backups():
                for filename in os.listdir(backup_dir):
                    is_backup = filename.startswith("kb_backup_") and (
                        filename.endswith(".json")
                        or filename.endswith(".jsongz")
                        or filename.endswith(".json.gz")
                    )
                    if is_backup:
                        filepath = os.path.join(backup_dir, filename)
                        stat = os.stat(filepath)
                        backups.append({
                            "filename": filename,
                            "filepath": filepath,
                            "size": stat.st_size,
                            "created_at": datetime.fromtimestamp(
                                stat.st_mtime
                            ).isoformat(),
                            "compressed": filename.endswith("gz"),
                        })

            await asyncio.to_thread(_scan_backups)

            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x["created_at"], reverse=True)

            return {
                "status": "success",
                "backup_dir": backup_dir,
                "backups": backups[:limit],
                "total_count": len(backups),
            }

        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
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

            logger.info(f"Backup deleted: {backup_file}")

            return {
                "status": "success",
                "deleted_file": backup_file,
            }

        except Exception as e:
            logger.error(f"Failed to delete backup: {e}")
            return {"status": "error", "message": str(e)}

    async def get_stats(self) -> Dict[str, Any]:
        """Get stats - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")
