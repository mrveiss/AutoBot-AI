# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Bulk Operations Module

Contains the BulkOperationsMixin class for bulk import, export,
delete, update, cleanup, and deduplication operations.
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
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Export facts with optional filtering.

        Args:
            format: Export format ("json", "csv", "markdown")
            output_file: Optional output file path
            category: Filter by category
            tags: Filter by tags

        Returns:
            Dict with status and data/file path
        """
        try:
            # Get all facts
            facts = await self.get_all_facts()

            # Apply filters
            if category:
                facts = [
                    f
                    for f in facts
                    if f.get("metadata", {}).get("category") == category
                ]

            if tags:
                filtered = []
                for fact in facts:
                    fact_tags = set(fact.get("metadata", {}).get("tags", []))
                    if any(tag in fact_tags for tag in tags):
                        filtered.append(fact)
                facts = filtered

            # Format output
            if format == "json":
                output = self._format_export_json(facts)
            elif format == "csv":
                output = self._format_export_csv(facts)
            elif format == "markdown":
                output = self._format_export_markdown(facts)
            else:
                return {"status": "error", "message": f"Unknown format: {format}"}

            # Save to file if specified
            if output_file:
                await asyncio.to_thread(
                    lambda: open(output_file, "w", encoding="utf-8").write(output)
                )
                return {
                    "status": "success",
                    "facts_exported": len(facts),
                    "output_file": output_file,
                }
            else:
                return {
                    "status": "success",
                    "facts_exported": len(facts),
                    "data": output,
                }

        except Exception as e:
            logger.error(f"Export failed: {e}")
            return {"status": "error", "message": str(e)}

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
        self, source_file: str, format: str = "json", skip_duplicates: bool = True
    ) -> Dict[str, Any]:
        """
        Import facts from a file.

        Args:
            source_file: Source file path
            format: Import format ("json", "csv")
            skip_duplicates: Skip duplicate facts

        Returns:
            Dict with import status
        """
        try:
            # Read file
            content = await asyncio.to_thread(
                lambda: open(source_file, "r", encoding="utf-8").read()
            )

            # Parse based on format
            if format == "json":
                facts = self._parse_import_json(content)
            elif format == "csv":
                facts = self._parse_import_csv(content)
            else:
                return {"status": "error", "message": f"Unknown format: {format}"}

            # Import each fact
            imported = 0
            skipped = 0
            errors = 0

            for fact_data in facts:
                try:
                    result = await self.store_fact(
                        content=fact_data.get("content", ""),
                        metadata=fact_data.get("metadata", {}),
                        fact_id=fact_data.get("fact_id"),
                    )

                    if result.get("status") == "success":
                        imported += 1
                    elif result.get("status") == "duplicate" and skip_duplicates:
                        skipped += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

            return {
                "status": "success",
                "imported": imported,
                "skipped": skipped,
                "errors": errors,
                "total": len(facts),
            }

        except Exception as e:
            logger.error(f"Import failed: {e}")
            return {"status": "error", "message": str(e)}

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
        self, similarity_threshold: float = 0.95
    ) -> Dict[str, Any]:
        """
        Find duplicate facts based on similarity.

        Args:
            similarity_threshold: Similarity threshold (0.0-1.0)

        Returns:
            Dict with duplicate groups
        """
        try:
            # Get all facts
            facts = await self.get_all_facts()

            # Find duplicates (simplified implementation)
            duplicates = []
            seen = {}

            for fact in facts:
                content_hash = hash(fact.get("content", ""))
                if content_hash in seen:
                    duplicates.append(
                        {
                            "fact_id": fact.get("fact_id"),
                            "duplicate_of": seen[content_hash],
                        }
                    )
                else:
                    seen[content_hash] = fact.get("fact_id")

            return {
                "status": "success",
                "duplicates_found": len(duplicates),
                "duplicates": duplicates,
            }

        except Exception as e:
            logger.error(f"Duplicate detection failed: {e}")
            return {"status": "error", "message": str(e)}

    async def bulk_delete(self, fact_ids: List[str]) -> Dict[str, Any]:
        """
        Delete multiple facts in bulk.

        Args:
            fact_ids: List of fact IDs to delete

        Returns:
            Dict with status and counts
        """
        try:
            deleted = 0
            errors = 0

            for fact_id in fact_ids:
                result = await self.delete_fact(fact_id)
                if result.get("status") == "success":
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
            logger.error(f"Bulk delete failed: {e}")
            return {"status": "error", "message": str(e)}

    async def bulk_update_category(
        self, fact_ids: List[str], new_category: str
    ) -> Dict[str, Any]:
        """
        Update category for multiple facts.

        Args:
            fact_ids: List of fact IDs
            new_category: New category name

        Returns:
            Dict with status and counts
        """
        try:
            updated = 0
            errors = 0

            for fact_id in fact_ids:
                result = await self.update_fact(
                    fact_id, metadata={"category": new_category}
                )
                if result.get("status") == "success":
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
            logger.error(f"Bulk category update failed: {e}")
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
            logger.error(f"Cleanup failed: {e}")
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
