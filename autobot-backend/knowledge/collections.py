# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Collection Management Module (Issue #412)

Contains the CollectionsMixin class for collection/folder operations enabling
project-based organization of knowledge base facts.

Collections provide a way to group related facts together. Unlike categories
(which are hierarchical), collections are flat and facts can belong to
multiple collections (many-to-many relationship).
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import aioredis
    import redis

logger = logging.getLogger(__name__)


class CollectionsMixin:
    """
    Collection management mixin for knowledge base (Issue #412).

    Provides collection (folder) operations:
    - Create/update/delete collections
    - Add/remove facts from collections
    - List facts in a collection
    - Many-to-many relationship (fact can be in multiple collections)
    - Collection-level bulk operations

    Redis Storage Structure:
    - collection:{id} -> Hash with collection data
    - collection:facts:{id} -> Set of fact IDs in collection
    - fact:collections:{fact_id} -> Set of collection IDs containing fact
    - collection:all -> Set of all collection IDs
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"

    # =========================================================================
    # COLLECTION CRUD OPERATIONS (Issue #412)
    # =========================================================================

    def _build_collection_data(
        self,
        collection_id: str,
        name: str,
        description: Optional[str],
        icon: Optional[str],
        color: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build collection data dict for storage (Issue #398: extracted)."""
        now = datetime.now(timezone.utc).isoformat()
        collection_data = {
            "id": collection_id,
            "name": name,
            "description": description or "",
            "icon": icon or "",
            "color": color or "",
            "created_at": now,
            "updated_at": now,
            "fact_count": 0,
            "metadata": json.dumps(metadata) if metadata else "{}",
        }
        return collection_data

    async def _store_collection(
        self, collection_id: str, collection_data: Dict[str, Any]
    ) -> None:
        """Store collection in Redis (Issue #398: extracted)."""
        await self.aioredis_client.hset(
            f"collection:{collection_id}", mapping=collection_data
        )
        await self.aioredis_client.sadd("collection:all", collection_id)

    async def create_collection(
        self,
        name: str,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new collection (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            name = name.strip()
            if not name:
                return {"success": False, "message": "Collection name is required"}

            collection_id = str(uuid.uuid4())
            collection_data = self._build_collection_data(
                collection_id, name, description, icon, color, metadata
            )
            await self._store_collection(collection_id, collection_data)

            logger.info("Created collection '%s' (id: %s)", name, collection_id)
            return {
                "success": True,
                "collection": collection_data,
                "message": f"Collection '{name}' created successfully",
            }

        except Exception as e:
            logger.error("Failed to create collection '%s': %s", name, e)
            return {"success": False, "message": str(e)}

    async def get_collection(self, collection_id: str) -> Dict[str, Any]:
        """
        Get a single collection by ID.

        Issue #412: Collections/Folders for grouping documents.

        Args:
            collection_id: Collection UUID

        Returns:
            Dict with success status and collection data
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            data = await self._get_collection_data(collection_id)
            if not data:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            return {"success": True, "collection": data}

        except Exception as e:
            logger.error("Failed to get collection '%s': %s", collection_id, e)
            return {"success": False, "message": str(e)}

    async def _fetch_all_collections(self) -> List[Dict[str, Any]]:
        """Fetch all collections from Redis (Issue #398: extracted)."""
        collection_ids = await self.aioredis_client.smembers("collection:all")
        collections = []
        for cid in collection_ids:
            if isinstance(cid, bytes):
                cid = cid.decode("utf-8")
            data = await self._get_collection_data(cid)
            if data:
                collections.append(data)
        return collections

    def _sort_collections(
        self, collections: List[Dict[str, Any]], sort_by: str
    ) -> List[Dict[str, Any]]:
        """Sort collections by specified field (Issue #398: extracted)."""
        if sort_by == "name":
            collections.sort(key=lambda x: x.get("name", "").lower())
        elif sort_by == "created_at":
            collections.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        elif sort_by == "fact_count":
            collections.sort(key=lambda x: x.get("fact_count", 0), reverse=True)
        return collections

    async def list_collections(
        self, limit: int = 100, offset: int = 0, sort_by: str = "name"
    ) -> Dict[str, Any]:
        """List all collections (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            collections = await self._fetch_all_collections()
            total_count = len(collections)
            collections = self._sort_collections(collections, sort_by)
            paginated = collections[offset : offset + limit]

            return {
                "success": True,
                "collections": paginated,
                "total_count": total_count,
                "returned_count": len(paginated),
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
            }

        except Exception as e:
            logger.error("Failed to list collections: %s", e)
            return {"success": False, "message": str(e)}

    def _build_collection_updates(
        self,
        name: Optional[str],
        description: Optional[str],
        icon: Optional[str],
        color: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build updates dict for collection (Issue #398: extracted)."""
        updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if name is not None:
            updates["name"] = name.strip()
        if description is not None:
            updates["description"] = description
        if icon is not None:
            updates["icon"] = icon
        if color is not None:
            updates["color"] = color
        if metadata is not None:
            updates["metadata"] = json.dumps(metadata)
        return updates

    async def update_collection(
        self,
        collection_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update collection metadata (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            current = await self._get_collection_data(collection_id)
            if not current:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            updates = self._build_collection_updates(
                name, description, icon, color, metadata
            )
            await self.aioredis_client.hset(
                f"collection:{collection_id}", mapping=updates
            )
            updated = await self._get_collection_data(collection_id)

            logger.info("Updated collection '%s'", collection_id)
            return {
                "success": True,
                "collection": updated,
                "message": "Collection updated successfully",
            }

        except Exception as e:
            logger.error("Failed to update collection '%s': %s", collection_id, e)
            return {"success": False, "message": str(e)}

    async def _remove_facts_from_deleted_collection(
        self, collection_id: str, fact_ids: set, delete_facts: bool
    ) -> int:
        """Remove or delete facts when collection is deleted (Issue #398: extracted)."""
        facts_deleted = 0
        for fid in fact_ids:
            if isinstance(fid, bytes):
                fid = fid.decode("utf-8")
            await self.aioredis_client.srem(f"fact:collections:{fid}", collection_id)
            if delete_facts:
                await self.aioredis_client.delete(f"fact:{fid}")
                facts_deleted += 1
        return facts_deleted

    async def _delete_collection_records(self, collection_id: str) -> None:
        """Delete collection records from Redis (Issue #398: extracted)."""
        await self.aioredis_client.delete(f"collection:{collection_id}")
        await self.aioredis_client.delete(f"collection:facts:{collection_id}")
        await self.aioredis_client.srem("collection:all", collection_id)

    async def delete_collection(
        self, collection_id: str, delete_facts: bool = False
    ) -> Dict[str, Any]:
        """Delete a collection (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            collection = await self._get_collection_data(collection_id)
            if not collection:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            fact_ids = await self.aioredis_client.smembers(
                f"collection:facts:{collection_id}"
            )
            facts_count = len(fact_ids)
            facts_deleted = await self._remove_facts_from_deleted_collection(
                collection_id, fact_ids, delete_facts
            )
            await self._delete_collection_records(collection_id)

            logger.info(
                "Deleted collection '%s' (%d facts %s)",
                collection_id,
                facts_count,
                "deleted" if delete_facts else "preserved",
            )
            return {
                "success": True,
                "collection_id": collection_id,
                "facts_in_collection": facts_count,
                "facts_deleted": facts_deleted,
                "message": "Collection deleted successfully",
            }

        except Exception as e:
            logger.error("Failed to delete collection '%s': %s", collection_id, e)
            return {"success": False, "message": str(e)}

    # =========================================================================
    # COLLECTION MEMBERSHIP OPERATIONS (Issue #412)
    # =========================================================================

    async def _process_facts_for_add(
        self, collection_id: str, fact_ids: List[str]
    ) -> tuple:
        """Process facts for adding to collection (Issue #398: extracted)."""
        added_count = 0
        already_in_collection = 0
        not_found = []

        for fid in fact_ids:
            fact_exists = await self.aioredis_client.exists(f"fact:{fid}")
            if not fact_exists:
                not_found.append(fid)
                continue

            is_member = await self.aioredis_client.sismember(
                f"collection:facts:{collection_id}", fid
            )
            if is_member:
                already_in_collection += 1
                continue

            await self.aioredis_client.sadd(f"collection:facts:{collection_id}", fid)
            await self.aioredis_client.sadd(f"fact:collections:{fid}", collection_id)
            added_count += 1

        return added_count, already_in_collection, not_found

    async def _update_collection_fact_count(self, collection_id: str) -> int:
        """Update and return collection fact count (Issue #398: extracted)."""
        new_count = await self.aioredis_client.scard(
            f"collection:facts:{collection_id}"
        )
        await self.aioredis_client.hset(
            f"collection:{collection_id}", "fact_count", new_count
        )
        return new_count

    async def add_facts_to_collection(
        self, collection_id: str, fact_ids: List[str]
    ) -> Dict[str, Any]:
        """Add facts to a collection (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            collection = await self._get_collection_data(collection_id)
            if not collection:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            (
                added_count,
                already_in_collection,
                not_found,
            ) = await self._process_facts_for_add(collection_id, fact_ids)
            new_count = await self._update_collection_fact_count(collection_id)

            logger.info(
                "Added %d facts to collection '%s' (%d already present, %d not found)",
                added_count,
                collection_id,
                already_in_collection,
                len(not_found),
            )
            return {
                "success": True,
                "collection_id": collection_id,
                "added_count": added_count,
                "already_in_collection": already_in_collection,
                "not_found": not_found,
                "total_facts": new_count,
                "message": f"Added {added_count} facts to collection",
            }

        except Exception as e:
            logger.error("Failed to add facts to collection '%s': %s", collection_id, e)
            return {"success": False, "message": str(e)}

    async def _process_facts_for_remove(
        self, collection_id: str, fact_ids: List[str]
    ) -> tuple:
        """Process facts for removal from collection (Issue #398: extracted)."""
        removed_count = 0
        not_in_collection = 0

        for fid in fact_ids:
            is_member = await self.aioredis_client.sismember(
                f"collection:facts:{collection_id}", fid
            )
            if not is_member:
                not_in_collection += 1
                continue

            await self.aioredis_client.srem(f"collection:facts:{collection_id}", fid)
            await self.aioredis_client.srem(f"fact:collections:{fid}", collection_id)
            removed_count += 1

        return removed_count, not_in_collection

    async def remove_facts_from_collection(
        self, collection_id: str, fact_ids: List[str]
    ) -> Dict[str, Any]:
        """Remove facts from a collection (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            collection = await self._get_collection_data(collection_id)
            if not collection:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            removed_count, not_in_collection = await self._process_facts_for_remove(
                collection_id, fact_ids
            )
            new_count = await self._update_collection_fact_count(collection_id)

            logger.info(
                "Removed %d facts from collection '%s' (%d not in collection)",
                removed_count,
                collection_id,
                not_in_collection,
            )
            return {
                "success": True,
                "collection_id": collection_id,
                "removed_count": removed_count,
                "not_in_collection": not_in_collection,
                "total_facts": new_count,
                "message": f"Removed {removed_count} facts from collection",
            }

        except Exception as e:
            logger.error(
                "Failed to remove facts from collection '%s': %s", collection_id, e
            )
            return {"success": False, "message": str(e)}

    async def _fetch_fact_for_collection(
        self, fid: str, include_content: bool
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single fact for collection display (Issue #398: extracted)."""
        fact_data = await self.aioredis_client.hgetall(f"fact:{fid}")
        if not fact_data:
            return None
        decoded = {
            (k.decode("utf-8") if isinstance(k, bytes) else k): (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in fact_data.items()
        }
        result = {
            "id": fid,
            "category": decoded.get("category", ""),
            "created_at": decoded.get("created_at", ""),
        }
        if include_content:
            result["content"] = decoded.get("content", "")
        return result

    async def get_facts_in_collection(
        self,
        collection_id: str,
        limit: int = 50,
        offset: int = 0,
        include_content: bool = False,
    ) -> Dict[str, Any]:
        """Get all facts in a collection (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            collection = await self._get_collection_data(collection_id)
            if not collection:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            fact_ids = await self.aioredis_client.smembers(
                f"collection:facts:{collection_id}"
            )
            total_count = len(fact_ids)

            fact_ids_list = sorted(
                [
                    fid.decode("utf-8") if isinstance(fid, bytes) else fid
                    for fid in fact_ids
                ]
            )
            paginated_ids = fact_ids_list[offset : offset + limit]

            facts = []
            for fid in paginated_ids:
                fact = await self._fetch_fact_for_collection(fid, include_content)
                if fact:
                    facts.append(fact)

            return {
                "success": True,
                "collection_id": collection_id,
                "collection_name": collection.get("name"),
                "facts": facts,
                "total_count": total_count,
                "returned_count": len(facts),
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
            }

        except Exception as e:
            logger.error("Failed to get facts in collection '%s': %s", collection_id, e)
            return {"success": False, "message": str(e)}

    async def get_fact_collections(self, fact_id: str) -> Dict[str, Any]:
        """
        Get all collections a fact belongs to.

        Issue #412: Many-to-many relationship support.

        Args:
            fact_id: Fact UUID

        Returns:
            Dict with list of collections
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Verify fact exists
            fact_exists = await self.aioredis_client.exists(f"fact:{fact_id}")
            if not fact_exists:
                return {"success": False, "message": f"Fact not found: {fact_id}"}

            # Get collection IDs
            collection_ids = await self.aioredis_client.smembers(
                f"fact:collections:{fact_id}"
            )

            collections = []
            for cid in collection_ids:
                if isinstance(cid, bytes):
                    cid = cid.decode("utf-8")
                data = await self._get_collection_data(cid)
                if data:
                    collections.append(data)

            # Sort by name
            collections.sort(key=lambda x: x.get("name", "").lower())

            return {
                "success": True,
                "fact_id": fact_id,
                "collections": collections,
                "count": len(collections),
            }

        except Exception as e:
            logger.error("Failed to get collections for fact '%s': %s", fact_id, e)
            return {"success": False, "message": str(e)}

    # =========================================================================
    # COLLECTION BULK OPERATIONS (Issue #412)
    # =========================================================================

    async def _export_single_fact(
        self,
        fid: str,
        include_content: bool,
        include_metadata: bool,
    ) -> Optional[Dict[str, Any]]:
        """Export a single fact with optional content/metadata (Issue #398: extracted)."""
        fact_data = await self.aioredis_client.hgetall(f"fact:{fid}")
        if not fact_data:
            return None

        decoded = {}
        for k, v in fact_data.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else k
            val = v.decode("utf-8") if isinstance(v, bytes) else v
            decoded[key] = val

        export_fact: Dict[str, Any] = {"id": fid}

        if include_content:
            export_fact["content"] = decoded.get("content", "")

        if include_metadata:
            export_fact["category"] = decoded.get("category", "")
            export_fact["created_at"] = decoded.get("created_at", "")
            export_fact["updated_at"] = decoded.get("updated_at", "")
            if "metadata" in decoded:
                try:
                    export_fact["metadata"] = json.loads(decoded["metadata"])
                except Exception:
                    export_fact["metadata"] = {}

        return export_fact

    async def export_collection(
        self,
        collection_id: str,
        include_content: bool = True,
        include_metadata: bool = True,
    ) -> Dict[str, Any]:
        """Export all facts in a collection (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            collection = await self._get_collection_data(collection_id)
            if not collection:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            fact_ids = await self.aioredis_client.smembers(
                f"collection:facts:{collection_id}"
            )

            facts = []
            for fid in fact_ids:
                if isinstance(fid, bytes):
                    fid = fid.decode("utf-8")
                export_fact = await self._export_single_fact(
                    fid, include_content, include_metadata
                )
                if export_fact:
                    facts.append(export_fact)

            return {
                "success": True,
                "collection": {
                    "id": collection.get("id"),
                    "name": collection.get("name"),
                    "description": collection.get("description"),
                },
                "facts": facts,
                "total_count": len(facts),
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to export collection '%s': %s", collection_id, e)
            return {"success": False, "message": str(e)}

    async def _get_bulk_delete_preview(self, collection_id: str) -> Dict[str, Any]:
        """Get preview of bulk delete operation (Issue #398: extracted)."""
        collection = await self._get_collection_data(collection_id)
        if not collection:
            return {
                "success": False,
                "message": f"Collection not found: {collection_id}",
            }

        fact_count = await self.aioredis_client.scard(
            f"collection:facts:{collection_id}"
        )
        return {
            "success": True,
            "collection_id": collection_id,
            "facts_to_delete": fact_count,
            "confirm_required": True,
            "message": f"Set confirm=True to delete {fact_count} facts",
        }

    async def _delete_fact_completely(self, fid: str) -> None:
        """Delete a fact and remove from all collections (Issue #398: extracted)."""
        if isinstance(fid, bytes):
            fid = fid.decode("utf-8")
        collections = await self.aioredis_client.smembers(f"fact:collections:{fid}")
        for cid in collections:
            if isinstance(cid, bytes):
                cid = cid.decode("utf-8")
            await self.aioredis_client.srem(f"collection:facts:{cid}", fid)
        await self.aioredis_client.delete(f"fact:{fid}")
        await self.aioredis_client.delete(f"fact:collections:{fid}")

    async def bulk_delete_collection_facts(
        self, collection_id: str, confirm: bool = False
    ) -> Dict[str, Any]:
        """Delete all facts in a collection (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        if not confirm:
            return await self._get_bulk_delete_preview(collection_id)

        try:
            collection = await self._get_collection_data(collection_id)
            if not collection:
                return {
                    "success": False,
                    "message": f"Collection not found: {collection_id}",
                }

            fact_ids = await self.aioredis_client.smembers(
                f"collection:facts:{collection_id}"
            )
            deleted_count = 0
            for fid in fact_ids:
                await self._delete_fact_completely(fid)
                deleted_count += 1

            await self.aioredis_client.hset(
                f"collection:{collection_id}", "fact_count", 0
            )
            logger.info(
                "Bulk deleted %d facts from collection '%s'",
                deleted_count,
                collection_id,
            )

            return {
                "success": True,
                "collection_id": collection_id,
                "deleted_count": deleted_count,
                "message": f"Deleted {deleted_count} facts from collection",
            }

        except Exception as e:
            logger.error(
                "Failed to bulk delete facts in collection '%s': %s", collection_id, e
            )
            return {"success": False, "message": str(e)}

    # =========================================================================
    # PRIVATE HELPER METHODS (Issue #412)
    # =========================================================================

    async def _get_collection_data(
        self, collection_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get collection data from Redis hash."""
        data = await self.aioredis_client.hgetall(f"collection:{collection_id}")
        if not data:
            return None

        # Decode bytes and convert types
        result = {}
        for k, v in data.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else k
            val = v.decode("utf-8") if isinstance(v, bytes) else v

            # Convert numeric strings
            if key == "fact_count":
                try:
                    val = int(val)
                except ValueError:
                    pass

            # Parse metadata JSON
            if key == "metadata":
                try:
                    import json

                    val = json.loads(val)
                except Exception:
                    val = {}

            result[key] = val

        return result
