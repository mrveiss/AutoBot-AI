# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Metadata & Versioning API Router

Issue #414: Provides API endpoints for metadata templates, validation,
and fact version history management.

Endpoints:
- Metadata Templates: CRUD for custom metadata field definitions
- Metadata Validation: Validate metadata against templates
- Metadata Search: Search facts by metadata fields
- Version History: List, view, compare, and revert fact versions
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.api.knowledge_models import (
    CompareVersionsRequest,
    CreateMetadataTemplateRequest,
    RevertToVersionRequest,
    SearchByMetadataRequest,
    UpdateMetadataTemplateRequest,
    ValidateMetadataRequest,
)
from src.knowledge import get_knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-metadata"])


# ============================================================================
# METADATA TEMPLATE ENDPOINTS
# ============================================================================


@router.post("/metadata/templates")
async def create_metadata_template(request: CreateMetadataTemplateRequest):
    """
    Create a new metadata template.

    Templates define custom fields for facts in specific categories,
    enabling structured metadata with type validation.

    Example:
        POST /api/knowledge_base/metadata/templates
        {
            "name": "API Documentation",
            "description": "Template for API endpoint documentation",
            "fields": [
                {"name": "version", "type": "string", "required": true},
                {"name": "deprecated", "type": "boolean", "default": false},
                {"name": "endpoint_url", "type": "url", "required": true}
            ],
            "applicable_categories": ["api", "documentation"]
        }
    """
    try:
        kb = await get_knowledge_base()

        # Convert Pydantic models to dicts
        fields = [f.dict() for f in request.fields]

        result = await kb.create_metadata_template(
            name=request.name,
            fields=fields,
            description=request.description,
            applicable_categories=request.applicable_categories,
        )

        if result.get("status") != "success":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to create template"),
            )

        logger.info("Created metadata template: %s", request.name)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create metadata template: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata/templates")
async def list_metadata_templates(category: str = None):
    """
    List all metadata templates, optionally filtered by category.

    Args:
        category: Optional category filter

    Returns:
        List of templates with their field definitions
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.list_metadata_templates(category=category)

        logger.info(
            "Listed %d metadata templates%s",
            result.get("count", 0),
            f" for category '{category}'" if category else "",
        )
        return result

    except Exception as e:
        logger.error("Failed to list metadata templates: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata/templates/{template_id}")
async def get_metadata_template(template_id: str):
    """Get a specific metadata template by ID."""
    try:
        kb = await get_knowledge_base()
        result = await kb.get_metadata_template(template_id)

        if result.get("status") != "success":
            raise HTTPException(status_code=404, detail="Template not found")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get metadata template %s: %s", template_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/metadata/templates/{template_id}")
async def update_metadata_template(
    template_id: str, request: UpdateMetadataTemplateRequest
):
    """Update an existing metadata template."""
    try:
        kb = await get_knowledge_base()

        # Convert fields if provided
        fields = None
        if request.fields is not None:
            fields = [f.dict() for f in request.fields]

        result = await kb.update_metadata_template(
            template_id=template_id,
            name=request.name,
            description=request.description,
            fields=fields,
            applicable_categories=request.applicable_categories,
        )

        if result.get("status") != "success":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to update template"),
            )

        logger.info("Updated metadata template %s", template_id)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update metadata template %s: %s", template_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/metadata/templates/{template_id}")
async def delete_metadata_template(template_id: str):
    """Delete a metadata template."""
    try:
        kb = await get_knowledge_base()
        result = await kb.delete_metadata_template(template_id)

        if result.get("status") != "success":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to delete template"),
            )

        logger.info("Deleted metadata template %s", template_id)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete metadata template %s: %s", template_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# METADATA VALIDATION ENDPOINTS
# ============================================================================


@router.post("/metadata/validate")
async def validate_metadata(request: ValidateMetadataRequest):
    """
    Validate metadata against applicable templates.

    Checks that metadata conforms to the templates defined for
    the specified category.

    Returns:
        - valid: bool - Whether metadata is valid
        - errors: list - Validation errors
        - warnings: list - Non-blocking warnings
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.validate_metadata(
            metadata=request.metadata,
            category=request.category,
        )

        return result

    except Exception as e:
        logger.error("Failed to validate metadata: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/metadata/search")
async def search_by_metadata(request: SearchByMetadataRequest):
    """
    Search facts by metadata field value.

    Supports multiple comparison operators for flexible querying.

    Example:
        POST /api/knowledge_base/metadata/search
        {
            "field_name": "author",
            "value": "john",
            "operator": "contains",
            "limit": 50
        }
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.search_by_metadata(
            field_name=request.field_name,
            value=request.value,
            operator=request.operator,
            limit=request.limit,
        )

        if result.get("status") != "success":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Search failed"),
            )

        logger.info(
            "Metadata search found %d facts for %s %s '%s'",
            result.get("count", 0),
            request.field_name,
            request.operator,
            request.value,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to search by metadata: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VERSION HISTORY ENDPOINTS
# ============================================================================


@router.get("/facts/{fact_id}/versions")
async def list_fact_versions(fact_id: str, limit: int = 10):
    """
    List version history for a fact.

    Returns versions in chronological order (newest first).

    Args:
        fact_id: Fact ID
        limit: Maximum versions to return (default 10, max 50)
    """
    try:
        if limit > 50:
            limit = 50

        kb = await get_knowledge_base()
        result = await kb.list_versions(fact_id, limit=limit)

        if result.get("status") != "success":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to list versions"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list versions for %s: %s", fact_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facts/{fact_id}/versions/{version}")
async def get_fact_version(fact_id: str, version: int):
    """
    Get a specific version of a fact.

    Returns the full content and metadata at that version point.
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.get_version(fact_id, version)

        if result.get("status") != "success":
            raise HTTPException(
                status_code=404,
                detail=result.get("message", "Version not found"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get version %d for %s: %s", version, fact_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facts/{fact_id}/revert")
async def revert_to_version(fact_id: str, request: RevertToVersionRequest):
    """
    Revert a fact to a previous version.

    Creates a new version with the content from the specified version.

    Example:
        POST /api/knowledge_base/facts/abc123/revert
        {
            "version": 3,
            "created_by": "admin"
        }
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.revert_to_version(
            fact_id=fact_id,
            version=request.version,
            created_by=request.created_by,
        )

        if result.get("status") != "success":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to revert"),
            )

        logger.info("Reverted fact %s to version %d", fact_id, request.version)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to revert %s to version %d: %s", fact_id, request.version, e
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facts/{fact_id}/versions/compare")
async def compare_versions(fact_id: str, request: CompareVersionsRequest):
    """
    Compare two versions of a fact.

    Returns detailed diff information about content and metadata changes.
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.compare_versions(
            fact_id=fact_id,
            version_a=request.version_a,
            version_b=request.version_b,
        )

        if result.get("status") != "success":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Comparison failed"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to compare versions for %s: %s", fact_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/facts/{fact_id}/versions")
async def delete_version_history(fact_id: str, confirm: bool = False):
    """
    Delete all version history for a fact.

    WARNING: This cannot be undone. Requires confirm=true.
    """
    try:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Must set confirm=true to delete version history",
            )

        kb = await get_knowledge_base()
        result = await kb.delete_version_history(fact_id)

        if result.get("status") != "success":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to delete history"),
            )

        logger.warning("Deleted version history for fact %s", fact_id)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete version history for %s: %s", fact_id, e)
        raise HTTPException(status_code=500, detail=str(e))
