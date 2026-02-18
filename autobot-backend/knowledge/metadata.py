# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Metadata Templates Module

Issue #414: Implements custom metadata field definitions and templates
for structured fact metadata with validation.

Features:
- Define custom metadata fields with types and validation
- Create templates that apply to specific categories
- Validate metadata on fact creation/update
- Index metadata for enhanced search
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    import aioredis
    import redis

logger = logging.getLogger(__name__)

# Supported field types
FIELD_TYPES = {"string", "number", "date", "boolean", "list", "url", "email"}

# Validation pattern for email
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# Validation pattern for URL
URL_PATTERN = re.compile(
    r"^https?://[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+.*$"
)


class MetadataMixin:
    """
    Metadata templates mixin for knowledge base.

    Issue #414: Provides custom metadata field definitions and templates
    with validation support.

    Features:
    - Create/read/update/delete metadata templates
    - Define field types, required fields, defaults, and validation rules
    - Apply templates to categories
    - Validate fact metadata against templates
    - Query facts by metadata fields
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"

    # Redis key patterns
    TEMPLATE_PREFIX = "metadata:template:"
    TEMPLATE_ALL = "metadata:template:all"
    CATEGORY_TEMPLATES = "metadata:category:templates:"

    def _build_template_data(
        self,
        template_id: str,
        name: str,
        description: str,
        validated_fields: List[Dict],
        applicable_categories: List[str],
    ) -> Dict[str, Any]:
        """Build template data dictionary (Issue #398: extracted)."""
        created_at = datetime.utcnow().isoformat()
        return {
            "id": template_id,
            "name": name,
            "description": description or "",
            "fields": validated_fields,
            "applicable_categories": applicable_categories or [],
            "created_at": created_at,
            "updated_at": created_at,
        }

    async def _store_template_in_redis(
        self,
        template_id: str,
        template_data: Dict[str, Any],
        applicable_categories: List[str],
    ) -> None:
        """Store template and link to categories (Issue #398: extracted)."""
        template_key = f"{self.TEMPLATE_PREFIX}{template_id}"
        await asyncio.to_thread(
            self.redis_client.set, template_key, json.dumps(template_data)
        )
        await asyncio.to_thread(self.redis_client.sadd, self.TEMPLATE_ALL, template_id)

        for category in applicable_categories or []:
            await asyncio.to_thread(
                self.redis_client.sadd,
                f"{self.CATEGORY_TEMPLATES}{category}",
                template_id,
            )

    async def create_metadata_template(
        self,
        name: str,
        fields: List[Dict[str, Any]],
        description: str = None,
        applicable_categories: List[str] = None,
    ) -> Dict[str, Any]:
        """Create a new metadata template (Issue #398: refactored)."""
        try:
            validated_fields = self._validate_field_definitions(fields)
            if not validated_fields.get("success"):
                return validated_fields

            template_id = str(uuid.uuid4())[:8]
            template_data = self._build_template_data(
                template_id,
                name,
                description,
                validated_fields["fields"],
                applicable_categories,
            )

            await self._store_template_in_redis(
                template_id, template_data, applicable_categories
            )
            logger.info("Created metadata template '%s' (id=%s)", name, template_id)
            return {"status": "success", "template": template_data}

        except Exception as e:
            logger.error("Failed to create metadata template: %s", e)
            return {"status": "error", "message": str(e)}

    def _validate_field_definitions(
        self, fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Validate field definitions for a template."""
        validated_fields = []

        for i, field in enumerate(fields):
            # Name is required
            if "name" not in field or not field["name"]:
                return {
                    "success": False,
                    "status": "error",
                    "message": f"Field {i}: 'name' is required",
                }

            # Type is required and must be valid
            field_type = field.get("type", "string")
            if field_type not in FIELD_TYPES:
                return {
                    "success": False,
                    "status": "error",
                    "message": f"Field {i}: invalid type '{field_type}'. "
                    f"Must be one of: {', '.join(FIELD_TYPES)}",
                }

            # Validate regex if provided
            validation_pattern = field.get("validation")
            if validation_pattern:
                try:
                    re.compile(validation_pattern)
                except re.error as e:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"Field {i}: invalid validation regex: {e}",
                    }

            validated_field = {
                "name": field["name"].strip(),
                "type": field_type,
                "required": bool(field.get("required", False)),
                "default": field.get("default"),
                "validation": validation_pattern,
                "description": field.get("description", ""),
            }
            validated_fields.append(validated_field)

        return {"success": True, "fields": validated_fields}

    async def get_metadata_template(self, template_id: str) -> Dict[str, Any]:
        """Get a metadata template by ID."""
        try:
            template_key = f"{self.TEMPLATE_PREFIX}{template_id}"
            data = await asyncio.to_thread(self.redis_client.get, template_key)

            if not data:
                return {"status": "error", "message": "Template not found"}

            template = json.loads(data)
            return {"status": "success", "template": template}

        except Exception as e:
            logger.error("Failed to get metadata template: %s", e)
            return {"status": "error", "message": str(e)}

    async def list_metadata_templates(self, category: str = None) -> Dict[str, Any]:
        """
        List all metadata templates, optionally filtered by category.

        Args:
            category: If provided, only return templates for this category

        Returns:
            Dict with list of templates
        """
        try:
            if category:
                # Get templates for specific category
                category_key = f"{self.CATEGORY_TEMPLATES}{category}"
                template_ids = await asyncio.to_thread(
                    self.redis_client.smembers, category_key
                )
            else:
                # Get all templates
                template_ids = await asyncio.to_thread(
                    self.redis_client.smembers, self.TEMPLATE_ALL
                )

            templates = []
            for tid in template_ids:
                tid_str = tid.decode() if isinstance(tid, bytes) else tid
                result = await self.get_metadata_template(tid_str)
                if result.get("status") == "success":
                    templates.append(result["template"])

            # Sort by name
            templates.sort(key=lambda t: t.get("name", ""))

            return {
                "status": "success",
                "templates": templates,
                "count": len(templates),
            }

        except Exception as e:
            logger.error("Failed to list metadata templates: %s", e)
            return {"status": "error", "message": str(e), "templates": []}

    async def _update_template_category_links(
        self, template_id: str, old_categories: set, new_categories: set
    ) -> None:
        """Update category links for template (Issue #398: extracted)."""
        for cat in old_categories - new_categories:
            await asyncio.to_thread(
                self.redis_client.srem, f"{self.CATEGORY_TEMPLATES}{cat}", template_id
            )
        for cat in new_categories - old_categories:
            await asyncio.to_thread(
                self.redis_client.sadd, f"{self.CATEGORY_TEMPLATES}{cat}", template_id
            )

    async def update_metadata_template(
        self,
        template_id: str,
        name: str = None,
        description: str = None,
        fields: List[Dict[str, Any]] = None,
        applicable_categories: List[str] = None,
    ) -> Dict[str, Any]:
        """Update a metadata template (Issue #398: refactored)."""
        try:
            result = await self.get_metadata_template(template_id)
            if result.get("status") != "success":
                return result

            template = result["template"]
            old_categories = set(template.get("applicable_categories", []))

            if name is not None:
                template["name"] = name
            if description is not None:
                template["description"] = description
            if fields is not None:
                validated = self._validate_field_definitions(fields)
                if not validated.get("success"):
                    return validated
                template["fields"] = validated["fields"]
            if applicable_categories is not None:
                template["applicable_categories"] = applicable_categories

            template["updated_at"] = datetime.utcnow().isoformat()
            template_key = f"{self.TEMPLATE_PREFIX}{template_id}"
            await asyncio.to_thread(
                self.redis_client.set, template_key, json.dumps(template)
            )

            if applicable_categories is not None:
                await self._update_template_category_links(
                    template_id, old_categories, set(applicable_categories)
                )

            logger.info("Updated metadata template %s", template_id)
            return {"status": "success", "template": template}

        except Exception as e:
            logger.error("Failed to update metadata template: %s", e)
            return {"status": "error", "message": str(e)}

    async def delete_metadata_template(self, template_id: str) -> Dict[str, Any]:
        """Delete a metadata template."""
        try:
            # Get template to find categories
            result = await self.get_metadata_template(template_id)
            if result.get("status") != "success":
                return result

            template = result["template"]
            categories = template.get("applicable_categories", [])

            # Remove from category links
            for cat in categories:
                await asyncio.to_thread(
                    self.redis_client.srem,
                    f"{self.CATEGORY_TEMPLATES}{cat}",
                    template_id,
                )

            # Remove from all templates set
            await asyncio.to_thread(
                self.redis_client.srem, self.TEMPLATE_ALL, template_id
            )

            # Delete template
            template_key = f"{self.TEMPLATE_PREFIX}{template_id}"
            await asyncio.to_thread(self.redis_client.delete, template_key)

            logger.info("Deleted metadata template %s", template_id)
            return {"status": "success", "message": "Template deleted"}

        except Exception as e:
            logger.error("Failed to delete metadata template: %s", e)
            return {"status": "error", "message": str(e)}

    def _validate_single_field(
        self, field: Dict, field_value: Any, errors: List[str]
    ) -> None:
        """Validate a single field against its definition (Issue #398: extracted)."""
        field_name = field["name"]
        if field.get("required") and field_value is None:
            errors.append(f"Required field '{field_name}' is missing")
            return
        if field_value is None:
            return
        field_type = field.get("type", "string")
        type_error = self._validate_field_type(field_name, field_value, field_type)
        if type_error:
            errors.append(type_error)
            return
        pattern = field.get("validation")
        if (
            pattern
            and isinstance(field_value, str)
            and not re.match(pattern, field_value)
        ):
            errors.append(f"Field '{field_name}' doesn't match pattern: {pattern}")

    async def validate_metadata(
        self, metadata: Dict[str, Any], category: str = None
    ) -> Dict[str, Any]:
        """Validate metadata against applicable templates (Issue #398: refactored)."""
        try:
            errors = []

            if category:
                result = await self.list_metadata_templates(category=category)
                templates = result.get("templates", [])
            else:
                templates = []

            if not templates:
                return {
                    "valid": True,
                    "errors": [],
                    "warnings": [],
                    "message": "No templates apply to this category",
                }

            for template in templates:
                for field in template.get("fields", []):
                    self._validate_single_field(
                        field, metadata.get(field["name"]), errors
                    )

            return {"valid": len(errors) == 0, "errors": errors, "warnings": []}

        except Exception as e:
            logger.error("Failed to validate metadata: %s", e)
            return {"valid": False, "errors": [str(e)], "warnings": []}

    def _validate_field_type(self, field_name: str, value: Any, field_type: str) -> str:
        """Validate a field value against its expected type. Returns error or None."""
        if field_type == "string":
            if not isinstance(value, str):
                return f"Field '{field_name}' must be a string"
        elif field_type == "number":
            if not isinstance(value, (int, float)):
                return f"Field '{field_name}' must be a number"
        elif field_type == "boolean":
            if not isinstance(value, bool):
                return f"Field '{field_name}' must be a boolean"
        elif field_type == "list":
            if not isinstance(value, list):
                return f"Field '{field_name}' must be a list"
        elif field_type == "date":
            if isinstance(value, str):
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return f"Field '{field_name}' must be a valid ISO date"
            else:
                return f"Field '{field_name}' must be an ISO date string"
        elif field_type == "url":
            if not isinstance(value, str) or not URL_PATTERN.match(value):
                return f"Field '{field_name}' must be a valid URL"
        elif field_type == "email":
            if not isinstance(value, str) or not EMAIL_PATTERN.match(value):
                return f"Field '{field_name}' must be a valid email"

        return None  # No error

    async def get_templates_for_category(self, category: str) -> Dict[str, Any]:
        """Get all templates applicable to a category."""
        return await self.list_metadata_templates(category=category)

    async def apply_template_defaults(
        self, metadata: Dict[str, Any], category: str
    ) -> Dict[str, Any]:
        """
        Apply default values from templates to metadata.

        Args:
            metadata: Current metadata dict
            category: Category to get templates for

        Returns:
            Dict with metadata including defaults
        """
        try:
            result = await self.list_metadata_templates(category=category)
            templates = result.get("templates", [])

            enhanced_metadata = dict(metadata)

            for template in templates:
                for field in template.get("fields", []):
                    field_name = field["name"]
                    default_value = field.get("default")

                    # Apply default if field not present and has default
                    if (
                        field_name not in enhanced_metadata
                        and default_value is not None
                    ):
                        enhanced_metadata[field_name] = default_value

            return {
                "status": "success",
                "metadata": enhanced_metadata,
                "defaults_applied": len(enhanced_metadata) - len(metadata),
            }

        except Exception as e:
            logger.error("Failed to apply template defaults: %s", e)
            return {"status": "error", "message": str(e), "metadata": metadata}

    def _match_metadata_value(
        self, field_value: Any, value: Any, operator: str
    ) -> bool:
        """Check if field value matches criteria (Issue #398: extracted)."""
        if operator == "eq":
            return field_value == value
        elif operator == "contains":
            return (
                isinstance(field_value, str)
                and isinstance(value, str)
                and value.lower() in field_value.lower()
            )
        elif operator == "gt":
            return field_value > value
        elif operator == "lt":
            return field_value < value
        return False

    async def _get_filtered_fact_keys(self) -> List[str]:
        """Get fact keys excluding index keys (Issue #398: extracted)."""
        fact_keys = await asyncio.to_thread(self.redis_client.keys, "fact:*")
        return [
            k
            for k in fact_keys
            if not any(
                x in (k.decode() if isinstance(k, bytes) else k)
                for x in [":tags", ":category", ":all"]
            )
        ]

    async def search_by_metadata(
        self,
        field_name: str,
        value: Any,
        operator: str = "eq",
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Search facts by metadata field value (Issue #398: refactored)."""
        try:
            fact_keys = await self._get_filtered_fact_keys()
            matching_facts = []

            for key in fact_keys[:500]:
                key_str = key.decode() if isinstance(key, bytes) else key
                if ":" in key_str and key_str.count(":") > 1:
                    continue

                metadata_json = await asyncio.to_thread(
                    self.redis_client.hget, key, "metadata"
                )
                if not metadata_json:
                    continue

                try:
                    metadata = json.loads(metadata_json)
                    field_value = metadata.get(field_name)
                    if field_value is None:
                        continue

                    if self._match_metadata_value(field_value, value, operator):
                        matching_facts.append(key_str.split(":")[-1])
                        if len(matching_facts) >= limit:
                            break
                except (json.JSONDecodeError, TypeError):
                    continue

            return {
                "status": "success",
                "fact_ids": matching_facts,
                "count": len(matching_facts),
                "field": field_name,
                "operator": operator,
                "value": value,
            }

        except Exception as e:
            logger.error("Failed to search by metadata: %s", e)
            return {"status": "error", "message": str(e), "fact_ids": []}

    def ensure_initialized(self):
        """Ensure the knowledge base is initialized. Implemented in composed class."""
        raise NotImplementedError("Should be implemented in composed class")
