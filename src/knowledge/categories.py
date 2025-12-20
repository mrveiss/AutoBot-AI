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

    async def create_category(
        self,
        name: str,
        parent_id: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new category in the hierarchy.

        Issue #411: Hierarchical category tree structure.

        Args:
            name: Category name (e.g., "python")
            parent_id: Optional parent category ID (None = root category)
            description: Optional category description
            icon: Optional icon identifier
            color: Optional hex color code

        Returns:
            Dict with success status and category data
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Validate and normalize name
            name = name.strip().lower().replace(" ", "-")
            if not name:
                return {"success": False, "message": "Category name is required"}

            # Generate category ID
            category_id = str(uuid.uuid4())

            # Build path
            if parent_id:
                # Verify parent exists
                parent_data = await self._get_category_data(parent_id)
                if not parent_data:
                    return {"success": False, "message": f"Parent category not found: {parent_id}"}
                parent_path = parent_data.get("path", "")
                path = f"{parent_path}/{name}"
            else:
                path = name

            # Check path uniqueness
            existing_id = await self.aioredis_client.get(f"category:path:{path}")
            if existing_id:
                return {"success": False, "message": f"Category path already exists: {path}"}

            # Build category data
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

            # Store category hash
            await self.aioredis_client.hset(
                f"category:{category_id}",
                mapping=category_data,
            )

            # Store path lookup
            await self.aioredis_client.set(f"category:path:{path}", category_id)

            # Update parent-child relationships
            if parent_id:
                await self.aioredis_client.sadd(f"category:children:{parent_id}", category_id)
            else:
                await self.aioredis_client.sadd("category:root", category_id)

            logger.info("Created category '%s' (path: %s, id: %s)", name, path, category_id)

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
                return {"success": False, "message": f"Category not found: {category_id}"}

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

    async def update_category(
        self,
        category_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update category metadata.

        Issue #411: Category CRUD operations.

        Note: Renaming updates the path and all child paths.

        Args:
            category_id: Category UUID
            name: New name (triggers path update)
            description: New description
            icon: New icon identifier
            color: New hex color code

        Returns:
            Dict with success status and updated category data
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Get current category data
            current = await self._get_category_data(category_id)
            if not current:
                return {"success": False, "message": f"Category not found: {category_id}"}

            updates = {"updated_at": datetime.now(timezone.utc).isoformat()}

            # Handle rename (updates path)
            if name and name != current["name"]:
                old_path = current["path"]
                new_name = name.strip().lower().replace(" ", "-")

                # Build new path
                parent_id = current.get("parent_id", "")
                if parent_id:
                    parent_data = await self._get_category_data(parent_id)
                    parent_path = parent_data.get("path", "") if parent_data else ""
                    new_path = f"{parent_path}/{new_name}"
                else:
                    new_path = new_name

                # Check new path uniqueness
                existing = await self.aioredis_client.get(f"category:path:{new_path}")
                if existing:
                    return {"success": False, "message": f"Category path already exists: {new_path}"}

                # Update paths (this category and all descendants)
                await self._update_category_path(category_id, old_path, new_path)

                updates["name"] = new_name
                updates["path"] = new_path

            # Update other fields
            if description is not None:
                updates["description"] = description
            if icon is not None:
                updates["icon"] = icon
            if color is not None:
                updates["color"] = color

            # Apply updates
            await self.aioredis_client.hset(f"category:{category_id}", mapping=updates)

            # Get updated data
            updated = await self._get_category_data(category_id)

            logger.info("Updated category '%s'", category_id)
            return {"success": True, "category": updated, "message": "Category updated successfully"}

        except Exception as e:
            logger.error("Failed to update category '%s': %s", category_id, e)
            return {"success": False, "message": str(e)}

    async def delete_category(
        self,
        category_id: str,
        recursive: bool = False,
        reassign_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Delete a category.

        Issue #411: Category deletion with child handling.

        Args:
            category_id: Category UUID to delete
            recursive: If True, delete all descendants. If False, fail if has children.
            reassign_to: Optional category ID to reassign facts to

        Returns:
            Dict with success status and deletion details
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Get category data
            category = await self._get_category_data(category_id)
            if not category:
                return {"success": False, "message": f"Category not found: {category_id}"}

            # Check for children
            children = await self.aioredis_client.smembers(f"category:children:{category_id}")
            if children and not recursive:
                return {
                    "success": False,
                    "message": "Category has children. Use recursive=True to delete all descendants.",
                }

            # Collect categories to delete
            categories_to_delete = [category_id]
            if recursive and children:
                descendants = await self._get_all_descendants(category_id)
                categories_to_delete.extend(descendants)

            # Reassign or orphan facts
            facts_reassigned = 0
            for cat_id in categories_to_delete:
                cat_facts = await self.aioredis_client.smembers(f"category:facts:{cat_id}")
                for fact_id in cat_facts:
                    if isinstance(fact_id, bytes):
                        fact_id = fact_id.decode("utf-8")
                    if reassign_to:
                        await self._assign_fact_to_category(fact_id, reassign_to)
                    else:
                        # Remove category from fact metadata
                        await self._remove_fact_category(fact_id)
                    facts_reassigned += 1

            # Delete categories
            for cat_id in categories_to_delete:
                cat_data = await self._get_category_data(cat_id)
                if cat_data:
                    path = cat_data.get("path", "")
                    parent_id = cat_data.get("parent_id", "")

                    # Delete path lookup
                    await self.aioredis_client.delete(f"category:path:{path}")

                    # Remove from parent's children
                    if parent_id:
                        await self.aioredis_client.srem(f"category:children:{parent_id}", cat_id)
                    else:
                        await self.aioredis_client.srem("category:root", cat_id)

                    # Delete children set
                    await self.aioredis_client.delete(f"category:children:{cat_id}")

                    # Delete facts set
                    await self.aioredis_client.delete(f"category:facts:{cat_id}")

                    # Delete category hash
                    await self.aioredis_client.delete(f"category:{cat_id}")

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

    async def get_category_tree(
        self,
        root_id: Optional[str] = None,
        max_depth: int = 10,
        include_fact_counts: bool = True,
    ) -> Dict[str, Any]:
        """
        Get the full category tree structure.

        Issue #411: Recursive tree building for API response.

        Args:
            root_id: Optional root to start from (None = full tree)
            max_depth: Maximum depth to traverse
            include_fact_counts: Include fact counts in each node

        Returns:
            Dict with tree structure
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            if root_id:
                # Get subtree from specific root
                root_data = await self._get_category_data(root_id)
                if not root_data:
                    return {"success": False, "message": f"Category not found: {root_id}"}
                tree = await self._build_tree_node(root_id, 0, max_depth, include_fact_counts)
                return {"success": True, "tree": [tree], "total_categories": 1}
            else:
                # Get all root categories
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

                # Sort by name
                tree.sort(key=lambda x: x.get("name", ""))

                return {"success": True, "tree": tree, "total_categories": total}

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
                    return {"success": False, "message": f"Category not found: {category_id}"}

            child_ids = await self.aioredis_client.smembers(f"category:children:{category_id}")
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
                return {"success": False, "message": f"Category not found: {category_id}"}

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

    async def assign_fact_to_category(
        self,
        fact_id: str,
        category_id: str,
    ) -> Dict[str, Any]:
        """
        Assign a fact to a category.

        Issue #411: Category assignment to facts.

        Args:
            fact_id: Fact UUID
            category_id: Category UUID

        Returns:
            Dict with success status
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Verify category exists
            category = await self._get_category_data(category_id)
            if not category:
                return {"success": False, "message": f"Category not found: {category_id}"}

            # Verify fact exists
            fact_exists = await self.aioredis_client.exists(f"fact:{fact_id}")
            if not fact_exists:
                return {"success": False, "message": f"Fact not found: {fact_id}"}

            # Remove from old category if any
            old_category = await self._get_fact_category_id(fact_id)
            if old_category and old_category != category_id:
                await self.aioredis_client.srem(f"category:facts:{old_category}", fact_id)
                await self._decrement_category_count(old_category)

            # Assign to new category
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
            logger.error("Failed to assign fact '%s' to category '%s': %s", fact_id, category_id, e)
            return {"success": False, "message": str(e)}

    async def get_facts_in_category(
        self,
        category_id: str,
        include_descendants: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get all facts in a category.

        Issue #411: Retrieve facts by category.

        Args:
            category_id: Category UUID
            include_descendants: Include facts from child categories
            limit: Maximum number of facts
            offset: Pagination offset

        Returns:
            Dict with facts list
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Verify category exists
            category = await self._get_category_data(category_id)
            if not category:
                return {"success": False, "message": f"Category not found: {category_id}"}

            # Collect category IDs to query
            category_ids = [category_id]
            if include_descendants:
                descendants = await self._get_all_descendants(category_id)
                category_ids.extend(descendants)

            # Gather all fact IDs
            all_fact_ids = set()
            for cat_id in category_ids:
                fact_ids = await self.aioredis_client.smembers(f"category:facts:{cat_id}")
                for fid in fact_ids:
                    if isinstance(fid, bytes):
                        fid = fid.decode("utf-8")
                    all_fact_ids.add(fid)

            total_count = len(all_fact_ids)

            # Apply pagination
            fact_ids_list = sorted(list(all_fact_ids))
            paginated_ids = fact_ids_list[offset : offset + limit]

            # Get fact data
            facts = []
            for fid in paginated_ids:
                fact_data = await self.aioredis_client.hgetall(f"fact:{fid}")
                if fact_data:
                    # Decode bytes
                    decoded = {}
                    for k, v in fact_data.items():
                        key = k.decode("utf-8") if isinstance(k, bytes) else k
                        val = v.decode("utf-8") if isinstance(v, bytes) else v
                        decoded[key] = val
                    decoded["id"] = fid
                    facts.append(decoded)

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

    async def search_categories_by_path(
        self,
        path_pattern: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Search categories by path pattern.

        Issue #411: Path-based queries.

        Args:
            path_pattern: Path pattern with wildcards (e.g., "tech/python/*")
            limit: Maximum results

        Returns:
            Dict with matching categories
        """
        if not self.aioredis_client:
            return {"success": False, "message": "Redis not available"}

        try:
            # Convert pattern for Redis SCAN
            pattern = path_pattern.strip().lower()
            if pattern.endswith("*"):
                redis_pattern = f"category:path:{pattern}"
            else:
                redis_pattern = f"category:path:{pattern}*"

            # Scan for matching paths
            matching_categories = []
            async for key in self.aioredis_client.scan_iter(match=redis_pattern, count=100):
                if len(matching_categories) >= limit:
                    break

                if isinstance(key, bytes):
                    key = key.decode("utf-8")

                category_id = await self.aioredis_client.get(key)
                if category_id:
                    if isinstance(category_id, bytes):
                        category_id = category_id.decode("utf-8")
                    cat_data = await self._get_category_data(category_id)
                    if cat_data:
                        matching_categories.append(cat_data)

            # Sort by path
            matching_categories.sort(key=lambda x: x.get("path", ""))

            return {
                "success": True,
                "pattern": path_pattern,
                "categories": matching_categories,
                "count": len(matching_categories),
            }

        except Exception as e:
            logger.error("Failed to search categories by path '%s': %s", path_pattern, e)
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

    async def _build_tree_node(
        self,
        category_id: str,
        current_depth: int,
        max_depth: int,
        include_fact_counts: bool,
    ) -> Optional[Dict[str, Any]]:
        """Recursively build a tree node with children."""
        if current_depth > max_depth:
            return None

        data = await self._get_category_data(category_id)
        if not data:
            return None

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

        # Get children
        child_ids = await self.aioredis_client.smembers(f"category:children:{category_id}")
        children = []

        for cid in child_ids:
            if isinstance(cid, bytes):
                cid = cid.decode("utf-8")
            child_node = await self._build_tree_node(
                cid, current_depth + 1, max_depth, include_fact_counts
            )
            if child_node:
                children.append(child_node)

        # Sort children by name
        children.sort(key=lambda x: x.get("name", ""))
        node["children"] = children

        return node

    def _count_tree_nodes(self, node: Dict[str, Any]) -> int:
        """Count total nodes in a tree structure."""
        count = 1
        for child in node.get("children", []):
            count += self._count_tree_nodes(child)
        return count

    async def _get_all_descendants(self, category_id: str) -> List[str]:
        """Get all descendant category IDs recursively."""
        descendants = []
        child_ids = await self.aioredis_client.smembers(f"category:children:{category_id}")

        for cid in child_ids:
            if isinstance(cid, bytes):
                cid = cid.decode("utf-8")
            descendants.append(cid)
            sub_descendants = await self._get_all_descendants(cid)
            descendants.extend(sub_descendants)

        return descendants

    async def _update_category_path(self, category_id: str, old_path: str, new_path: str) -> None:
        """Update category path and all descendant paths."""
        # Delete old path lookup
        await self.aioredis_client.delete(f"category:path:{old_path}")

        # Set new path lookup
        await self.aioredis_client.set(f"category:path:{new_path}", category_id)

        # Update descendants
        child_ids = await self.aioredis_client.smembers(f"category:children:{category_id}")

        for cid in child_ids:
            if isinstance(cid, bytes):
                cid = cid.decode("utf-8")
            child_data = await self._get_category_data(cid)
            if child_data:
                child_old_path = child_data.get("path", "")
                child_new_path = child_old_path.replace(old_path, new_path, 1)
                await self.aioredis_client.hset(f"category:{cid}", "path", child_new_path)
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
        current = await self.aioredis_client.hget(f"category:{category_id}", "fact_count")
        if current:
            count = int(current.decode("utf-8") if isinstance(current, bytes) else current)
            if count > 0:
                await self.aioredis_client.hset(f"category:{category_id}", "fact_count", count - 1)
