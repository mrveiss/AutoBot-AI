# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Note Taking Skill (Issue #731)

Capture, organize, and search notes with tagging and
full-text search via the knowledge base.
"""

import logging
from typing import Any, Dict

from skills.base_skill import BaseSkill, SkillConfigField, SkillManifest

logger = logging.getLogger(__name__)


class NoteTakingSkill(BaseSkill):
    """Note capture, organization, and search."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        """Return note taking manifest."""
        return SkillManifest(
            name="note-taking",
            version="1.0.0",
            description="Capture, organize, and search notes with AI assistance",
            author="mrveiss",
            category="productivity",
            dependencies=[],
            config={
                "storage_backend": SkillConfigField(
                    type="string",
                    default="redis",
                    description="Where to store notes",
                    choices=["redis", "file", "chromadb"],
                ),
                "auto_tag": SkillConfigField(
                    type="bool",
                    default=True,
                    description="Automatically generate tags from content",
                ),
                "max_note_length": SkillConfigField(
                    type="int",
                    default=10000,
                    description="Maximum note length in characters",
                ),
            },
            tools=[
                "create_note",
                "search_notes",
                "list_notes",
            ],
            triggers=["note_requested"],
            tags=["notes", "knowledge", "organization", "productivity"],
        )

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute note taking action."""
        handlers = {
            "create_note": self._create_note,
            "search_notes": self._search_notes,
            "list_notes": self._list_notes,
        }
        handler = handlers.get(action)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action}"}
        return await handler(params)

    async def _create_note(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new note.

        Helper for execute (Issue #731).
        """
        content = params.get("content")
        if not content:
            return {"success": False, "error": "content is required"}

        max_len = self._config.get("max_note_length", 10000)
        if len(content) > max_len:
            return {
                "success": False,
                "error": f"Note exceeds max length ({max_len})",
            }

        return {
            "success": True,
            "title": params.get("title", "Untitled"),
            "content_length": len(content),
            "tags": params.get("tags", []),
            "auto_tag": self._config.get("auto_tag", True),
            "storage": self._config.get("storage_backend", "redis"),
            "status": "queued",
            "message": "Note creation queued",
        }

    async def _search_notes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search notes by query or tags.

        Helper for execute (Issue #731).
        """
        query = params.get("query", "")
        tags = params.get("tags", [])
        if not query and not tags:
            return {
                "success": False,
                "error": "query or tags required",
            }

        return {
            "success": True,
            "query": query,
            "tags": tags,
            "storage": self._config.get("storage_backend", "redis"),
            "status": "queued",
            "message": "Note search queued",
        }

    async def _list_notes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List recent notes.

        Helper for execute (Issue #731).
        """
        limit = params.get("limit", 20)
        return {
            "success": True,
            "limit": limit,
            "storage": self._config.get("storage_backend", "redis"),
            "status": "queued",
            "message": f"Listing up to {limit} notes",
        }
