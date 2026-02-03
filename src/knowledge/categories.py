# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Category Management Module (Issue #411)

Contains the CategoriesMixin class for hierarchical category operations including
creating, updating, deleting, and navigating category trees.

Categories enable hierarchical organization like "tech/python/async" with
parent-child relationships and path-based lookups.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import aioredis
    import redis

logger = logging.getLogger(__name__)


class CategoriesMixin:
    """
    Category management mixin for knowledge base (Issue #411).

    Provides hierarchical category operations:
    - Create/update/delete categories
    - Parent-child relationships
    - Path-based lookups (e.g., "tech/python/*")
    - Tree structure traversal
    - Category assignment to facts

    Redis Storage Structure:
    - category:{id} -> Hash with category data
    - category:path:{path} -> Category ID (for path lookups)
    - category:children:{parent_id} -> Set of child category IDs
    - category:root -> Set of root category IDs
    - category:facts:{category_id} -> Set of fact IDs in category
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"

    # =========================================================================
    # CATEGORY CRUD OPERATIONS (Issue #411)
    # =========================================================================

    async def _build_category_path(
        self, name: str, parent_id: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """Build category path from name and parent (Issue #398: extracted).

        Returns: (path, error_message) - error_message is None if successful
        """
        if parent_id:
            parent_data = await self._get_category_data(parent_id)
            if not parent_data:
                return None, f"Parent category not found: {parent_id}"
            return f"{parent_data.get('path', '')}/{name}", None
        return name, None

    async def _store_category(
        self, category_id: str, category_data: Dict[str, Any], parent_id: Optional[str]
    ) -> None:
        """Store category in Redis (Issue #398: extracted)."""
        await self.aioredis_client.hset(
            f"category:{category_id}", mapping=category_data
        )
        await self.aioredis_client.set(
            f"category:path:{category_data['path']}", category_id
        )

        if parent_id:
            await self.aioredis_client.sadd(
                f"category:children:{parent_id}", category_id
            )
        else:
            await self.aioredis_client.sadd("category:root", category_id)

    async def create_category(
        self,
        name: str,
        parent_id: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new category in the hierarchy (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            name = name.strip().lower().replace(" ", "-")
            if not name:
                return {"success": False, "message": "Category name is required"}

            path, error = await self._build_category_path(name, parent_id)
            if error:
                return {"success": False, "message": error}

            if await self.aioredis_client.get(f"category:path:{path}"):
                return {
                    "success": False,
                    "message": f"Category path already exists: {path}",
                }

            category_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            category_data = {
                "id": category_id,
                "name": name,
                "parent_id": parent_id or "",
                "path": path,
                "description": description or "",
                "icon": icon or "",
                "color": color or "",
                "created_at": now,
                "updated_at": now,
                "fact_count": 0,
            }

            await self._store_category(category_id, category_data, parent_id)
            logger.info(
                "Created category '%s' (path: %s, id: %s)", name, path, category_id
            )

            return {
                "success": True,
                "category": category_data,
                "message": f"Category '{name}' created successfully",
            }

        except Exception as e:
            logger.error("Failed to create category '%s': %s", name, e)
            return {"success": False, "message": str(e)}

    async def get_category(self, category_id: str) -> Dict[str, Any]:
        """
        Get a single category by ID.

        Issue #411: Hierarchical category tree structure.

        Args:
            category_id: Category UUID

        Returns:
            Dict with success status and category data
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            data = await self._get_category_data(category_id)
            if not data:
                return {
                    "success": False,
                    "message": f"Category not found: {category_id}",
                }

            return {"success": True, "category": data}

        except Exception as e:
            logger.error("Failed to get category '%s': %s", category_id, e)
            return {"success": False, "message": str(e)}

    async def get_category_by_path(self, path: str) -> Dict[str, Any]:
        """
        Get a category by its path.

        Issue #411: Path-based category lookups.

        Args:
            path: Category path (e.g., "tech/python/async")

        Returns:
            Dict with success status and category data
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            path = path.strip().lower()
            category_id = await self.aioredis_client.get(f"category:path:{path}")

            if not category_id:
                return {"success": False, "message": f"Category path not found: {path}"}

            if isinstance(category_id, bytes):
                category_id = category_id.decode("utf-8")

            return await self.get_category(category_id)

        except Exception as e:
            logger.error("Failed to get category by path '%s': %s", path, e)
            return {"success": False, "message": str(e)}

    async def _handle_category_rename(
        self,
        category_id: str,
        current: Dict[str, Any],
        new_name: str,
        updates: Dict[str, Any],
    ) -> Optional[str]:
        """Handle category rename and path update (Issue #398: extracted).

        Returns: error message or None if successful
        """
        old_path = current["path"]
        new_name = new_name.strip().lower().replace(" ", "-")

        parent_id = current.get("parent_id", "")
        if parent_id:
            parent_data = await self._get_category_data(parent_id)
            parent_path = parent_data.get("path", "") if parent_data else ""
            new_path = f"{parent_path}/{new_name}"
        else:
            new_path = new_name

        if await self.aioredis_client.get(f"category:path:{new_path}"):
            return f"Category path already exists: {new_path}"

        await self._update_category_path(category_id, old_path, new_path)
        updates["name"] = new_name
        updates["path"] = new_path
        return None

    async def update_category(
        self,
        category_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update category metadata (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            current = await self._get_category_data(category_id)
            if not current:
                return {
                    "success": False,
                    "message": f"Category not found: {category_id}",
                }

            updates: Dict[str, Any] = {
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            if name and name != current["name"]:
                error = await self._handle_category_rename(
                    category_id, current, name, updates
                )
                if error:
                    return {"success": False, "message": error}

            if description is not None:
                updates["description"] = description
            if icon is not None:
                updates["icon"] = icon
            if color is not None:
                updates["color"] = color

            await self.aioredis_client.hset(f"category:{category_id}", mapping=updates)
            updated = await self._get_category_data(category_id)

            logger.info("Updated category '%s'", category_id)
            return {
                "success": True,
                "category": updated,
                "message": "Category updated successfully",
            }

        except Exception as e:
            logger.error("Failed to update category '%s': %s", category_id, e)
            return {"success": False, "message": str(e)}

    async def _reassign_category_facts(
        self, categories: List[str], reassign_to: Optional[str]
    ) -> int:
        """Reassign facts from categories being deleted (Issue #398: extracted)."""
        count = 0
        for cat_id in categories:
            cat_facts = await self.aioredis_client.smembers(f"category:facts:{cat_id}")
            for fact_id in cat_facts:
                if isinstance(fact_id, bytes):
                    fact_id = fact_id.decode("utf-8")
                if reassign_to:
                    await self._assign_fact_to_category(fact_id, reassign_to)
                else:
                    await self._remove_fact_category(fact_id)
                count += 1
        return count

    async def _delete_category_records(self, cat_id: str) -> None:
        """Delete all Redis records for a category (Issue #398: extracted)."""
        cat_data = await self._get_category_data(cat_id)
        if not cat_data:
            return

        path = cat_data.get("path", "")
        parent_id = cat_data.get("parent_id", "")

        await self.aioredis_client.delete(f"category:path:{path}")
        if parent_id:
            await self.aioredis_client.srem(f"category:children:{parent_id}", cat_id)
        else:
            await self.aioredis_client.srem("category:root", cat_id)

        await self.aioredis_client.delete(f"category:children:{cat_id}")
        await self.aioredis_client.delete(f"category:facts:{cat_id}")
        await self.aioredis_client.delete(f"category:{cat_id}")

    async def delete_category(
        self,
        category_id: str,
        recursive: bool = False,
        reassign_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a category (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            category = await self._get_category_data(category_id)
            if not category:
                return {
                    "success": False,
                    "message": f"Category not found: {category_id}",
                }

            children = await self.aioredis_client.smembers(
                f"category:children:{category_id}"
            )
            if children and not recursive:
                return {
                    "success": False,
                    "message": "Category has children. Use recursive=True to delete.",
                }

            categories_to_delete = [category_id]
            if recursive and children:
                categories_to_delete.extend(
                    await self._get_all_descendants(category_id)
                )

            facts_reassigned = await self._reassign_category_facts(
                categories_to_delete, reassign_to
            )

            for cat_id in categories_to_delete:
                await self._delete_category_records(cat_id)

            logger.info(
                "Deleted %d categories, reassigned %d facts",
                len(categories_to_delete),
                facts_reassigned,
            )

            return {
                "success": True,
                "deleted_count": len(categories_to_delete),
                "facts_reassigned": facts_reassigned,
                "message": f"Deleted {len(categories_to_delete)} categories",
            }

        except Exception as e:
            logger.error("Failed to delete category '%s': %s", category_id, e)
            return {"success": False, "message": str(e)}

    # =========================================================================
    # CATEGORY TREE OPERATIONS (Issue #411)
    # =========================================================================

    async def _build_full_tree(
        self, max_depth: int, include_fact_counts: bool
    ) -> Dict[str, Any]:
        """Build full tree from all roots (Issue #398: extracted)."""
        root_ids = await self.aioredis_client.smembers("category:root")
        tree = []
        total = 0

        for rid in root_ids:
            if isinstance(rid, bytes):
                rid = rid.decode("utf-8")
            node = await self._build_tree_node(rid, 0, max_depth, include_fact_counts)
            if node:
                tree.append(node)
                total += self._count_tree_nodes(node)

        tree.sort(key=lambda x: x.get("name", ""))
        return {"success": True, "tree": tree, "total_categories": total}

    async def get_category_tree(
        self,
        root_id: Optional[str] = None,
        max_depth: int = 10,
        include_fact_counts: bool = True,
    ) -> Dict[str, Any]:
        """Get full category tree structure (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            if root_id:
                root_data = await self._get_category_data(root_id)
                if not root_data:
                    return {
                        "success": False,
                        "message": f"Category not found: {root_id}",
                    }
                tree = await self._build_tree_node(
                    root_id, 0, max_depth, include_fact_counts
                )
                return {"success": True, "tree": [tree], "total_categories": 1}

            return await self._build_full_tree(max_depth, include_fact_counts)

        except Exception as e:
            logger.error("Failed to get category tree: %s", e)
            return {"success": False, "message": str(e)}

    async def get_children(self, category_id: str) -> Dict[str, Any]:
        """
        Get immediate children of a category.

        Args:
            category_id: Parent category ID

        Returns:
            Dict with list of child categories
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Verify parent exists
            if category_id:
                parent = await self._get_category_data(category_id)
                if not parent:
                    return {
                        "success": False,
                        "message": f"Category not found: {category_id}",
                    }

            child_ids = await self.aioredis_client.smembers(
                f"category:children:{category_id}"
            )
            children = []

            for cid in child_ids:
                if isinstance(cid, bytes):
                    cid = cid.decode("utf-8")
                child_data = await self._get_category_data(cid)
                if child_data:
                    children.append(child_data)

            # Sort by name
            children.sort(key=lambda x: x.get("name", ""))

            return {
                "success": True,
                "parent_id": category_id,
                "children": children,
                "count": len(children),
            }

        except Exception as e:
            logger.error("Failed to get children for '%s': %s", category_id, e)
            return {"success": False, "message": str(e)}

    async def get_ancestors(self, category_id: str) -> Dict[str, Any]:
        """
        Get all ancestors of a category (breadcrumb trail).

        Args:
            category_id: Category ID

        Returns:
            Dict with list of ancestors from root to parent
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            category = await self._get_category_data(category_id)
            if not category:
                return {
                    "success": False,
                    "message": f"Category not found: {category_id}",
                }

            ancestors = []
            current_id = category.get("parent_id", "")

            while current_id:
                parent_data = await self._get_category_data(current_id)
                if parent_data:
                    ancestors.insert(0, parent_data)  # Insert at beginning
                    current_id = parent_data.get("parent_id", "")
                else:
                    break

            return {
                "success": True,
                "category_id": category_id,
                "ancestors": ancestors,
                "depth": len(ancestors),
            }

        except Exception as e:
            logger.error("Failed to get ancestors for '%s': %s", category_id, e)
            return {"success": False, "message": str(e)}

    # =========================================================================
    # CATEGORY-FACT OPERATIONS (Issue #411)
    # =========================================================================

    async def _validate_fact_and_category(
        self, fact_id: str, category_id: str
    ) -> tuple[Optional[Dict], Optional[str]]:
        """Validate fact and category exist (Issue #398: extracted).

        Returns: (category_data, error_message)
        """
        category = await self._get_category_data(category_id)
        if not category:
            return None, f"Category not found: {category_id}"

        fact_exists = await self.aioredis_client.exists(f"fact:{fact_id}")
        if not fact_exists:
            return None, f"Fact not found: {fact_id}"

        return category, None

    async def _remove_from_old_category(
        self, fact_id: str, new_category_id: str
    ) -> None:
        """Remove fact from old category if reassigning (Issue #398: extracted)."""
        old_category = await self._get_fact_category_id(fact_id)
        if old_category and old_category != new_category_id:
            await self.aioredis_client.srem(f"category:facts:{old_category}", fact_id)
            await self._decrement_category_count(old_category)

    async def assign_fact_to_category(
        self, fact_id: str, category_id: str
    ) -> Dict[str, Any]:
        """Assign a fact to a category (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            category, error = await self._validate_fact_and_category(
                fact_id, category_id
            )
            if error:
                return {"success": False, "message": error}

            await self._remove_from_old_category(fact_id, category_id)
            await self._assign_fact_to_category(fact_id, category_id)

            logger.info("Assigned fact '%s' to category '%s'", fact_id, category_id)
            return {
                "success": True,
                "fact_id": fact_id,
                "category_id": category_id,
                "category_path": category.get("path"),
                "message": "Fact assigned to category",
            }

        except Exception as e:
            logger.error(
                "Failed to assign fact '%s' to category '%s': %s",
                fact_id,
                category_id,
                e,
            )
            return {"success": False, "message": str(e)}

    async def _gather_category_fact_ids(self, category_ids: List[str]) -> set:
        """Gather all fact IDs from multiple categories (Issue #398: extracted)."""
        all_ids: set = set()
        for cat_id in category_ids:
            fact_ids = await self.aioredis_client.smembers(f"category:facts:{cat_id}")
            for fid in fact_ids:
                all_ids.add(fid.decode("utf-8") if isinstance(fid, bytes) else fid)
        return all_ids

    async def _load_fact_data(self, fact_ids: List[str]) -> List[Dict[str, Any]]:
        """Load fact data for multiple fact IDs (Issue #398: extracted)."""
        facts = []
        for fid in fact_ids:
            fact_data = await self.aioredis_client.hgetall(f"fact:{fid}")
            if fact_data:
                decoded = {
                    (k.decode("utf-8") if isinstance(k, bytes) else k): (
                        v.decode("utf-8") if isinstance(v, bytes) else v
                    )
                    for k, v in fact_data.items()
                }
                decoded["id"] = fid
                facts.append(decoded)
        return facts

    async def get_facts_in_category(
        self,
        category_id: str,
        include_descendants: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get all facts in a category (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            category = await self._get_category_data(category_id)
            if not category:
                return {
                    "success": False,
                    "message": f"Category not found: {category_id}",
                }

            category_ids = [category_id]
            if include_descendants:
                category_ids.extend(await self._get_all_descendants(category_id))

            all_fact_ids = await self._gather_category_fact_ids(category_ids)
            total_count = len(all_fact_ids)

            paginated_ids = sorted(list(all_fact_ids))[offset : offset + limit]
            facts = await self._load_fact_data(paginated_ids)

            return {
                "success": True,
                "category_id": category_id,
                "category_path": category.get("path"),
                "facts": facts,
                "total_count": total_count,
                "returned_count": len(facts),
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
                "include_descendants": include_descendants,
            }

        except Exception as e:
            logger.error("Failed to get facts for category '%s': %s", category_id, e)
            return {"success": False, "message": str(e)}

    def _build_redis_path_pattern(self, path_pattern: str) -> str:
        """Build Redis SCAN pattern from path pattern (Issue #398: extracted)."""
        pattern = path_pattern.strip().lower()
        if pattern.endswith("*"):
            return f"category:path:{pattern}"
        return f"category:path:{pattern}*"

    async def _scan_matching_categories(
        self, redis_pattern: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Scan Redis for categories matching pattern (Issue #398: extracted)."""
        # Issue #614: Fix N+1 pattern - collect keys first, then batch fetch
        keys = []
        async for key in self.aioredis_client.scan_iter(match=redis_pattern, count=100):
            key = key.decode("utf-8") if isinstance(key, bytes) else key
            keys.append(key)
            if len(keys) >= limit * 2:  # Over-fetch to account for nulls
                break

        if not keys:
            return []

        # Batch fetch all category IDs using pipeline
        pipe = self.aioredis_client.pipeline()
        for key in keys:
            pipe.get(key)
        category_ids = await pipe.execute()

        # Collect valid category IDs
        valid_ids = []
        for cat_id in category_ids:
            if cat_id:
                cat_id = cat_id.decode("utf-8") if isinstance(cat_id, bytes) else cat_id
                valid_ids.append(cat_id)
            if len(valid_ids) >= limit:
                break

        if not valid_ids:
            return []

        # Batch fetch all category data using pipeline
        pipe = self.aioredis_client.pipeline()
        for cat_id in valid_ids:
            pipe.hgetall(f"category:{cat_id}")
        results = await pipe.execute()

        # Process results
        matching = []
        for result in results:
            if result:
                cat_data = self._decode_category_data(result)
                if cat_data:
                    matching.append(cat_data)
            if len(matching) >= limit:
                break

        matching.sort(key=lambda x: x.get("path", ""))
        return matching

    def _decode_category_data(self, data: dict) -> Optional[Dict[str, Any]]:
        """Decode category data from Redis hash (helper for batched operations)."""
        if not data:
            return None
        result = {}
        for k, v in data.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else k
            val = v.decode("utf-8") if isinstance(v, bytes) else v
            if key in ("fact_count",):
                try:
                    val = int(val)
                except ValueError:
                    pass
            result[key] = val
        return result

    async def search_categories_by_path(
        self, path_pattern: str, limit: int = 50
    ) -> Dict[str, Any]:
        """Search categories by path pattern (Issue #398: refactored)."""
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            redis_pattern = self._build_redis_path_pattern(path_pattern)
            matching_categories = await self._scan_matching_categories(
                redis_pattern, limit
            )

            return {
                "success": True,
                "pattern": path_pattern,
                "categories": matching_categories,
                "count": len(matching_categories),
            }
        except Exception as e:
            logger.error(
                "Failed to search categories by path '%s': %s", path_pattern, e
            )
            return {"success": False, "message": str(e)}

    # =========================================================================
    # PRIVATE HELPER METHODS (Issue #411)
    # =========================================================================

    async def _get_category_data(self, category_id: str) -> Optional[Dict[str, Any]]:
        """Get category data from Redis hash."""
        data = await self.aioredis_client.hgetall(f"category:{category_id}")
        if not data:
            return None

        # Decode bytes
        result = {}
        for k, v in data.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else k
            val = v.decode("utf-8") if isinstance(v, bytes) else v
            # Convert numeric strings
            if key in ("fact_count",):
                try:
                    val = int(val)
                except ValueError:
                    pass
            result[key] = val

        return result

    def _build_node_base(
        self, data: Dict[str, Any], include_fact_counts: bool
    ) -> Dict[str, Any]:
        """Build base node structure from category data. Issue #620.

        Args:
            data: Category data dictionary
            include_fact_counts: Whether to include fact count

        Returns:
            Dict with base node structure
        """
        node = {
            "id": data.get("id"),
            "name": data.get("name"),
            "path": data.get("path"),
            "description": data.get("description"),
            "icon": data.get("icon"),
            "color": data.get("color"),
        }
        if include_fact_counts:
            node["fact_count"] = data.get("fact_count", 0)
        return node

    async def _fetch_and_build_children(
        self,
        category_id: str,
        current_depth: int,
        max_depth: int,
        include_fact_counts: bool,
    ) -> List[Dict[str, Any]]:
        """Fetch and build child nodes in parallel. Issue #620.

        Args:
            category_id: Parent category ID
            current_depth: Current tree depth
            max_depth: Maximum tree depth
            include_fact_counts: Whether to include fact counts

        Returns:
            List of child node dictionaries
        """
        child_ids = await self.aioredis_client.smembers(
            f"category:children:{category_id}"
        )
        if not child_ids:
            return []

        decoded_ids = [
            cid.decode("utf-8") if isinstance(cid, bytes) else cid for cid in child_ids
        ]

        child_tasks = [
            self._build_tree_node(
                cid, current_depth + 1, max_depth, include_fact_counts
            )
            for cid in decoded_ids
        ]
        child_results = await asyncio.gather(*child_tasks, return_exceptions=True)

        children = [
            result
            for result in child_results
            if result is not None and not isinstance(result, Exception)
        ]
        children.sort(key=lambda x: x.get("name", ""))
        return children

    async def _build_tree_node(
        self,
        category_id: str,
        current_depth: int,
        max_depth: int,
        include_fact_counts: bool,
    ) -> Optional[Dict[str, Any]]:
        """Recursively build a tree node with children. Issue #620."""
        if current_depth > max_depth:
            return None

        data = await self._get_category_data(category_id)
        if not data:
            return None

        node = self._build_node_base(data, include_fact_counts)
        node["children"] = await self._fetch_and_build_children(
            category_id, current_depth, max_depth, include_fact_counts
        )
        return node

    def _count_tree_nodes(self, node: Dict[str, Any]) -> int:
        """Count total nodes in a tree structure."""
        count = 1
        for child in node.get("children", []):
            count += self._count_tree_nodes(child)
        return count

    async def _get_all_descendants(self, category_id: str) -> List[str]:
        """Get all descendant category IDs recursively."""
        child_ids = await self.aioredis_client.smembers(
            f"category:children:{category_id}"
        )

        if not child_ids:
            return []

        # Decode child IDs
        decoded_ids = [
            cid.decode("utf-8") if isinstance(cid, bytes) else cid for cid in child_ids
        ]

        # Issue #614: Fix N+1 pattern - fetch all sub-descendants in parallel
        sub_tasks = [self._get_all_descendants(cid) for cid in decoded_ids]
        sub_results = await asyncio.gather(*sub_tasks, return_exceptions=True)

        # Combine results
        descendants = list(decoded_ids)
        for result in sub_results:
            if isinstance(result, list):
                descendants.extend(result)

        return descendants

    async def _update_category_path(
        self, category_id: str, old_path: str, new_path: str
    ) -> None:
        """Update category path and all descendant paths."""
        # Delete old path lookup
        await self.aioredis_client.delete(f"category:path:{old_path}")

        # Set new path lookup
        await self.aioredis_client.set(f"category:path:{new_path}", category_id)

        # Update descendants
        child_ids = await self.aioredis_client.smembers(
            f"category:children:{category_id}"
        )

        for cid in child_ids:
            if isinstance(cid, bytes):
                cid = cid.decode("utf-8")
            child_data = await self._get_category_data(cid)
            if child_data:
                child_old_path = child_data.get("path", "")
                child_new_path = child_old_path.replace(old_path, new_path, 1)
                await self.aioredis_client.hset(
                    f"category:{cid}", "path", child_new_path
                )
                await self._update_category_path(cid, child_old_path, child_new_path)

    async def _assign_fact_to_category(self, fact_id: str, category_id: str) -> None:
        """Internal method to assign a fact to a category."""
        # Add to category's fact set
        await self.aioredis_client.sadd(f"category:facts:{category_id}", fact_id)

        # Update fact metadata
        await self.aioredis_client.hset(f"fact:{fact_id}", "category_id", category_id)

        # Increment category count
        await self.aioredis_client.hincrby(f"category:{category_id}", "fact_count", 1)

    async def _remove_fact_category(self, fact_id: str) -> None:
        """Remove category assignment from a fact."""
        await self.aioredis_client.hdel(f"fact:{fact_id}", "category_id")

    async def _get_fact_category_id(self, fact_id: str) -> Optional[str]:
        """Get the category ID a fact is assigned to."""
        category_id = await self.aioredis_client.hget(f"fact:{fact_id}", "category_id")
        if category_id and isinstance(category_id, bytes):
            category_id = category_id.decode("utf-8")
        return category_id if category_id else None

    async def _decrement_category_count(self, category_id: str) -> None:
        """Decrement fact count for a category."""
        current = await self.aioredis_client.hget(
            f"category:{category_id}", "fact_count"
        )
        if current:
            count = int(
                current.decode("utf-8") if isinstance(current, bytes) else current
            )
            if count > 0:
                await self.aioredis_client.hset(
                    f"category:{category_id}", "fact_count", count - 1
                )
