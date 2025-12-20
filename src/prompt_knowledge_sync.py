# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prompt-to-Knowledge Base Synchronization System

This module extends the prompt management system to automatically sync
selected prompts into the knowledge base, making operational intelligence
searchable and accessible during agent operations.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.knowledge_base import KnowledgeBase
from src.prompt_manager import prompt_manager

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for domain expertise keywords (Issue #326)
DOMAIN_EXPERTISE_KEYWORDS = {"developer", "hacker", "researcher"}

# Performance optimization: Lookup table for prompt type determination (Issue #315)
PROMPT_TYPE_KEYWORDS = [
    ("tool", "tool_guidance"),
    ("fw.", "framework_response"),
    ("behaviour", "behavioral_pattern"),
    ("behavior", "behavioral_pattern"),
    ("error", "error_handling"),
    ("memory", "memory_pattern"),
]


class PromptKnowledgeSync:
    """
    Synchronizes selected prompts from the prompt manager into the knowledge base
    for enhanced agent intelligence and contextual decision making.
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize prompt-knowledge synchronizer with KB and import categories."""
        self.knowledge_base = knowledge_base
        self.prompt_manager = prompt_manager

        # Define what to import vs exclude
        self.IMPORT_CATEGORIES = {
            "tool_patterns": {
                "patterns": [r".*\.tool\..*\.md$", r".*tools\.md$"],
                "collection": "Tool Usage Patterns",
                "description": "Tool-specific usage patterns and best practices",
            },
            "error_recovery": {
                "patterns": [
                    r".*fw\.error.*\.md$",
                    r".*fw\.code.*\.md$",
                    r".*fw\.tool.*\.md$",
                    r".*fw\.runtime.*\.md$",
                ],
                "collection": "Error Recovery Intelligence",
                "description": "Error handling and recovery strategies",
            },
            "behavioral_intelligence": {
                "patterns": [
                    r".*behaviour.*\.md$",
                    r".*solving\.md$",
                    r".*tips\.md$",
                    r".*communication\.md$",
                ],
                "collection": "Behavioral Intelligence",
                "description": "Agent behavioral patterns and communication strategies",
            },
            "framework_responses": {
                "patterns": [r".*fw\..*\.md$"],
                "collection": "Framework Response Patterns",
                "description": "Standardized framework response templates",
            },
            "domain_expertise": {
                "patterns": [
                    r"developer/.*\.md$",
                    r"hacker/.*\.md$",
                    r"researcher/.*\.md$",
                    r"reflection/.*\.md$",
                ],
                "collection": "Domain Expertise",
                "description": "Domain-specific operational knowledge",
            },
            "memory_patterns": {
                "patterns": [r".*memory.*\.md$", r".*memories.*\.md$"],
                "collection": "Memory Management Patterns",
                "description": "Memory and learning pattern guidance",
            },
        }

        # Exclude core system prompts that should stay in prompt manager
        self.EXCLUDE_PATTERNS = [
            r".*main\.role\.md$",  # Core agent identity
            r".*main\.environment\.md$",  # System environment
            r"orchestrator/system_prompt\.md$",  # System orchestration
            r".*_context\.md$",  # Template files
            r".*\.txt$",  # Legacy text files
            r".*:Zone\.Identifier$",  # Windows file system artifacts
        ]

    def should_import_prompt(
        self, prompt_key: str, file_path: str
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Determine if a prompt should be imported to knowledge base.

        Returns:
            (should_import, category, collection_name)
        """
        # Check exclusion patterns first
        for exclude_pattern in self.EXCLUDE_PATTERNS:
            if re.match(exclude_pattern, file_path):
                return False, None, None

        # Check import categories
        for category_name, category_info in self.IMPORT_CATEGORIES.items():
            for pattern in category_info["patterns"]:
                if re.match(pattern, file_path):
                    return True, category_name, category_info["collection"]

        return False, None, None

    def extract_prompt_metadata(
        self,
        prompt_key: str,
        content: str,
        file_path: str,
        category: str,
        collection_name: str,
    ) -> Dict[str, Any]:
        """
        Extract metadata from prompt content and file information.
        """
        # Generate content hash for change detection
        content_hash = hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()

        # Extract tags from filename and content
        tags = self._generate_tags(prompt_key, content, category)

        # Determine prompt type
        prompt_type = self._determine_prompt_type(prompt_key, content)

        return {
            "source": f"prompts/{file_path}",
            "prompt_key": prompt_key,
            "category": category,
            "collection": collection_name,
            "prompt_type": prompt_type,
            "tags": tags,
            "content_hash": content_hash,
            "last_updated": datetime.now().isoformat(),
            "auto_imported": True,
        }

    def _generate_tags(self, prompt_key: str, content: str, category: str) -> List[str]:
        """
        Generate relevant tags for the prompt based on key, content, and category.
        """
        tags = [category]

        # Add tags based on prompt key structure
        key_parts = prompt_key.split(".")
        tags.extend([part for part in key_parts if len(part) > 2])

        # Add content-based tags
        content_lower = content.lower()

        # Tool-related tags
        if "tool" in content_lower:
            tags.append("tool_usage")
        if "json" in content_lower:
            tags.append("json_format")
        if "response" in content_lower:
            tags.append("response_format")

        # Error/framework tags
        if "error" in content_lower:
            tags.append("error_handling")
        if "debug" in content_lower:
            tags.append("debugging")
        if "failed" in content_lower or "failure" in content_lower:
            tags.append("failure_recovery")

        # Behavioral tags
        if "behavior" in content_lower or "behaviour" in content_lower:
            tags.append("behavior_pattern")
        if "communicate" in content_lower:
            tags.append("communication")
        if "solve" in content_lower or "problem" in content_lower:
            tags.append("problem_solving")

        # Remove duplicates and return
        return list(set(tags))

    def _determine_prompt_type(self, prompt_key: str, content: str) -> str:
        """
        Determine the type of prompt based on key and content (Issue #315: flattened).
        Uses lookup table to avoid deep if/elif nesting.
        """
        # Check keyword lookup table (O(n) where n is small constant)
        for keyword, prompt_type in PROMPT_TYPE_KEYWORDS:
            if keyword in prompt_key:
                return prompt_type

        # Check domain expertise keywords
        if any(domain in prompt_key for domain in DOMAIN_EXPERTISE_KEYWORDS):
            return "domain_expertise"

        return "operational_guidance"

    def _should_skip_unchanged(
        self,
        existing_entries: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        force_update: bool,
    ) -> bool:
        """
        Check if prompt should be skipped due to no content change.

        Issue #281: Extracted helper for change detection.

        Args:
            existing_entries: Existing knowledge base entries
            metadata: New prompt metadata with content_hash
            force_update: Whether to force update regardless

        Returns:
            True if should skip (no changes), False otherwise
        """
        if not existing_entries or force_update:
            return False

        existing_hash = existing_entries[0].get("metadata", {}).get("content_hash")
        return existing_hash == metadata["content_hash"]

    async def _store_or_update_prompt(
        self,
        prompt_key: str,
        content: str,
        metadata: Dict[str, Any],
        existing_entries: List[Dict[str, Any]],
        results: Dict[str, Any],
    ) -> None:
        """
        Store new prompt or update existing one in knowledge base.

        Issue #281: Extracted helper for storage operations.

        Args:
            prompt_key: Unique prompt identifier
            content: Prompt content
            metadata: Prompt metadata
            existing_entries: Existing entries (if any)
            results: Results dict to update counters
        """
        if existing_entries:
            existing_fact_id = existing_entries[0]["id"]
            success = await self.knowledge_base.update_fact(
                fact_id=existing_fact_id, content=content, metadata=metadata
            )
            if success:
                results["updated"] += 1
                logger.debug("Updated prompt in knowledge base: %s", prompt_key)
            else:
                results["errors"] += 1
                logger.error("Failed to update prompt: %s", prompt_key)
        else:
            result = await self.knowledge_base.store_fact(
                content=content, metadata=metadata
            )
            if result.get("status") == "success":
                results["imported"] += 1
                logger.debug("Imported prompt to knowledge base: %s", prompt_key)
            else:
                results["errors"] += 1
                logger.error("Failed to import prompt: %s", prompt_key)

    async def sync_prompts_to_knowledge(
        self, force_update: bool = False
    ) -> Dict[str, Any]:
        """
        Synchronize selected prompts from prompt manager to knowledge base.

        Issue #281: Refactored from 111 lines to use extracted helper methods.

        Args:
            force_update: If True, update all prompts regardless of changes

        Returns:
            Sync results summary
        """
        logger.info("Starting prompt-to-knowledge synchronization...")

        results = {
            "total_prompts": 0,
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "categories": {},
            "error_details": [],
        }

        available_prompts = self.prompt_manager.list_prompts()
        results["total_prompts"] = len(available_prompts)

        for prompt_key in available_prompts:
            try:
                file_path = prompt_key.replace(".", "/") + ".md"

                should_import, category, collection_name = self.should_import_prompt(
                    prompt_key, file_path
                )

                if not should_import:
                    results["skipped"] += 1
                    continue

                category = category or "uncategorized"
                collection_name = collection_name or "Uncategorized"

                content = self.prompt_manager.get_raw(prompt_key)
                metadata = self.extract_prompt_metadata(
                    prompt_key, content, file_path, category, collection_name
                )

                existing_entries = await self._find_existing_prompt_entry(prompt_key)

                # Issue #281: uses helper
                if self._should_skip_unchanged(existing_entries, metadata, force_update):
                    results["skipped"] += 1
                    continue

                # Issue #281: uses helper
                await self._store_or_update_prompt(
                    prompt_key, content, metadata, existing_entries, results
                )

                # Track by category
                if category not in results["categories"]:
                    results["categories"][category] = 0
                results["categories"][category] += 1

            except Exception as e:
                results["errors"] += 1
                error_detail = f"Error processing {prompt_key}: {str(e)}"
                results["error_details"].append(error_detail)
                logger.error(error_detail)

        logger.info(
            f"Prompt sync completed: {results['imported']} imported, "
            f"{results['updated']} updated, {results['skipped']} skipped, "
            f"{results['errors']} errors"
        )
        return results

    async def _find_existing_prompt_entry(
        self, prompt_key: str
    ) -> List[Dict[str, Any]]:
        """
        Find existing knowledge base entries for a given prompt key.
        """
        try:
            # Get all facts and filter by prompt_key in metadata
            all_facts = await self.knowledge_base.get_all_facts(collection="all")

            exact_matches = []
            for fact in all_facts:
                metadata = fact.get("metadata", {})
                if (
                    isinstance(metadata, dict)
                    and metadata.get("prompt_key") == prompt_key
                ):
                    exact_matches.append(fact)

            return exact_matches
        except Exception as e:
            logger.warning("Error finding existing prompt entry for %s: %s", prompt_key, e)
            return []

    async def remove_prompt_knowledge(self, prompt_key: str) -> bool:
        """
        Remove a prompt's knowledge base entries (for cleanup).
        """
        try:
            existing_entries = await self._find_existing_prompt_entry(prompt_key)

            removed_count = 0
            for entry in existing_entries:
                fact_id = entry.get("id")
                if fact_id:
                    success = await self.knowledge_base.delete_fact(fact_id)
                    if success:
                        removed_count += 1

            logger.info(
                f"Removed {removed_count} knowledge entries for prompt: "
                f"{prompt_key}"
            )
            return removed_count > 0

        except Exception as e:
            logger.error("Error removing prompt knowledge for %s: %s", prompt_key, e)
            return False

    async def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current synchronization status and statistics.
        """
        try:
            # Count prompts by category in knowledge base
            knowledge_stats = {}

            for category_name, category_info in self.IMPORT_CATEGORIES.items():
                collection_name = category_info["collection"]

                # Get all facts and count those in this collection
                # with auto_imported flag
                all_facts = await self.knowledge_base.get_all_facts(collection="all")

                auto_imported_count = sum(
                    1
                    for fact in all_facts
                    if (
                        fact.get("metadata", {}).get("collection") == collection_name
                        and fact.get("metadata", {}).get("auto_imported", False)
                    )
                )

                knowledge_stats[category_name] = {
                    "collection": collection_name,
                    "entries": auto_imported_count,
                    "description": category_info["description"],
                }

            # Count total available prompts that could be imported
            available_prompts = self.prompt_manager.list_prompts()
            importable_count = 0

            for prompt_key in available_prompts:
                file_path = prompt_key.replace(".", "/") + ".md"
                should_import, _, _ = self.should_import_prompt(prompt_key, file_path)
                if should_import:
                    importable_count += 1

            return {
                "total_available_prompts": len(available_prompts),
                "importable_prompts": importable_count,
                "knowledge_base_stats": knowledge_stats,
                "last_sync": None,  # Could be tracked in configuration
            }

        except Exception as e:
            logger.error("Error getting sync status: %s", e)
            return {"error": str(e)}


# Global instance
prompt_knowledge_sync = None


def get_prompt_knowledge_sync(knowledge_base: KnowledgeBase) -> PromptKnowledgeSync:
    """
    Get or create the global PromptKnowledgeSync instance.
    """
    global prompt_knowledge_sync
    if prompt_knowledge_sync is None:
        prompt_knowledge_sync = PromptKnowledgeSync(knowledge_base)
    return prompt_knowledge_sync


async def sync_prompts_to_knowledge(
    knowledge_base: KnowledgeBase, force_update: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to sync prompts to knowledge base.
    """
    sync_manager = get_prompt_knowledge_sync(knowledge_base)
    return await sync_manager.sync_prompts_to_knowledge(force_update)
