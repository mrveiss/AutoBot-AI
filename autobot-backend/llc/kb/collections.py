# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""KB collection lifecycle manager (GH#8235).

Canonical naming and lifecycle for ChromaDB collections across all LLC entities.
Collections are created on entity creation and archived on entity deletion,
with document merging support for ephemeral entities (sprints, work items).
"""

import uuid
from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)


async def _get_kb():
    from knowledge import get_knowledge_base  # lazy — avoids chromadb at import time

    return await get_knowledge_base()


class KbCollectionManager:
    """Manages KB collection lifecycle for all LLC entities.

    Provides canonical collection naming, creation, archiving, and merging.
    Acts as the single authority for collection naming conventions.
    """

    # Collection name prefixes
    COMPANY_PREFIX = "company"
    PROJECT_PREFIX = "project"
    SPRINT_PREFIX = "sprint"
    WORK_ITEM_PREFIX = "work_item"
    AGENT_PREFIX = "agent"

    # Collection suffixes (optional per entity)
    AGENTS_SUFFIX = "agents"
    DECISIONS_SUFFIX = "decisions"

    @classmethod
    def collection_name(
        cls,
        entity_type: str,
        entity_id: uuid.UUID | str,
        suffix: Optional[str] = None,
    ) -> str:
        """Generate canonical collection name.

        Args:
            entity_type: Type of entity (company, project, sprint, work_item, agent)
            entity_id: Unique identifier for the entity
            suffix: Optional suffix (agents, decisions, etc.)

        Returns:
            Collection name in format: prefix:id or prefix:id:suffix
        """
        entity_id_str = str(entity_id) if isinstance(entity_id, uuid.UUID) else entity_id
        name = f"{entity_type}:{entity_id_str}"
        if suffix:
            name = f"{name}:{suffix}"
        return name

    async def ensure_collection(
        self,
        entity_type: str,
        entity_id: uuid.UUID | str,
        suffix: Optional[str] = None,
    ) -> str:
        """Create ChromaDB collection if not exists; idempotent.

        Args:
            entity_type: Type of entity
            entity_id: Unique identifier for the entity
            suffix: Optional suffix

        Returns:
            Collection name

        Raises:
            RuntimeError: If KB initialization fails
        """
        collection_name = self.collection_name(entity_type, entity_id, suffix)

        try:
            kb = await _get_kb()
            # get_or_create_collection is idempotent
            await kb._async_chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"entity_type": entity_type, "entity_id": str(entity_id)},
            )
            logger.info("Ensured KB collection: %s", collection_name)
            return collection_name
        except Exception as e:
            logger.error(
                "Failed to ensure KB collection %s: %s",
                collection_name,
                str(e),
            )
            raise RuntimeError(f"Failed to ensure KB collection {collection_name}") from e

    async def archive_collection(
        self,
        entity_type: str,
        entity_id: uuid.UUID | str,
        suffix: Optional[str] = None,
    ) -> str:
        """Archive collection by renaming to :archived:timestamp format.

        Data is preserved for audit. Original collection is deleted.

        Args:
            entity_type: Type of entity
            entity_id: Unique identifier for the entity
            suffix: Optional suffix

        Returns:
            Archived collection name

        Raises:
            RuntimeError: If KB operations fail
        """
        original_name = self.collection_name(entity_type, entity_id, suffix)
        timestamp = now_utc().isoformat()
        archived_name = f"{original_name}:archived:{timestamp}"

        try:
            kb = await _get_kb()
            # Get original collection to verify it exists
            try:
                original = await kb._async_chroma_client.get_collection(original_name)
            except Exception:
                logger.warning(
                    "Collection %s does not exist; nothing to archive",
                    original_name,
                )
                return archived_name

            # Create archived collection
            archived = await kb._async_chroma_client.create_collection(
                name=archived_name,
                metadata={
                    "entity_type": entity_type,
                    "entity_id": str(entity_id),
                    "archived_at": timestamp,
                },
            )

            # Copy all documents from original to archived
            documents = await original.get()
            if documents and documents.get("ids"):
                embeddings = documents.get("embeddings")
                add_kwargs: dict = {
                    "ids": documents["ids"],
                    "metadatas": documents.get("metadatas"),
                    "documents": documents.get("documents"),
                }
                if embeddings is not None:
                    add_kwargs["embeddings"] = embeddings
                await archived.add(**add_kwargs)

            # Delete original collection
            await kb._async_chroma_client.delete_collection(original_name)
            logger.info(
                "Archived KB collection %s -> %s",
                original_name,
                archived_name,
            )
            return archived_name

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(
                "Failed to archive KB collection %s: %s",
                original_name,
                str(e),
            )
            raise RuntimeError(f"Failed to archive KB collection {original_name}") from e

    async def merge_collection(
        self,
        src_entity_type: str,
        src_entity_id: uuid.UUID | str,
        dst_entity_type: str,
        dst_entity_id: uuid.UUID | str,
        src_suffix: Optional[str] = None,
        dst_suffix: Optional[str] = None,
        summarize: bool = False,
    ) -> None:
        """Copy documents from source collection into destination collection.

        For ephemeral entities (work items, sprints) merged into project KB.
        If summarize=True, documents are LLM-summarized before merging
        (not yet implemented; returns early for now).

        Args:
            src_entity_type: Source entity type
            src_entity_id: Source entity ID
            dst_entity_type: Destination entity type
            dst_entity_id: Destination entity ID
            src_suffix: Optional source suffix
            dst_suffix: Optional destination suffix
            summarize: Whether to LLM-summarize before merge (GH#8238)

        Raises:
            RuntimeError: If merge fails
        """
        src_name = self.collection_name(src_entity_type, src_entity_id, src_suffix)
        dst_name = self.collection_name(dst_entity_type, dst_entity_id, dst_suffix)

        if summarize:
            logger.info(
                "Collection merge with summarization requested (%s -> %s); " "deferring to GH#8238",
                src_name,
                dst_name,
            )
            return

        try:
            kb = await _get_kb()

            # Get source collection
            try:
                src = await kb._async_chroma_client.get_collection(src_name)
            except Exception:
                logger.warning(
                    "Source collection %s does not exist; skipping merge",
                    src_name,
                )
                return

            # Ensure destination collection exists
            dst = await kb._async_chroma_client.get_or_create_collection(
                name=dst_name,
                metadata={
                    "entity_type": dst_entity_type,
                    "entity_id": str(dst_entity_id),
                },
            )

            # Copy all documents from source to destination
            documents = await src.get()
            if documents and documents.get("ids"):
                await dst.add(
                    ids=documents["ids"],
                    embeddings=documents.get("embeddings"),
                    metadatas=documents.get("metadatas"),
                    documents=documents.get("documents"),
                )
                logger.info(
                    "Merged %d documents from %s into %s",
                    len(documents["ids"]),
                    src_name,
                    dst_name,
                )
            else:
                logger.info(
                    "Source collection %s is empty; merge complete",
                    src_name,
                )

        except Exception as e:
            logger.error(
                "Failed to merge KB collection %s -> %s: %s",
                src_name,
                dst_name,
                str(e),
            )
            raise RuntimeError(f"Failed to merge KB collection {src_name} -> {dst_name}") from e
