# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response builders for the delete routes of ``api.memory`` (split out in #18825)."""

from fastapi.responses import JSONResponse


def _build_delete_entity_response(
    request_id: str,
    entity_id: str,
    entity_name: str,
    cascade_relations: bool,
) -> JSONResponse:
    """
    Build success response for entity deletion.

    Issue #620: Extracted from delete_entity to reduce function length.

    Args:
        request_id: Request tracking ID
        entity_id: Deleted entity UUID
        entity_name: Deleted entity name
        cascade_relations: Whether relations were cascaded

    Returns:
        JSONResponse with deletion confirmation
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "entity_id": entity_id,
                "entity_name": entity_name,
                "deleted": True,
                "cascade_relations": cascade_relations,
            },
            "message": "Entity deleted successfully",
            "request_id": request_id,
        },
    )


def _build_delete_relation_response(
    request_id: str,
    from_entity: str,
    to_entity: str,
    relation_type: str,
) -> JSONResponse:
    """
    Build success response for relation deletion.

    Issue #620: Extracted from delete_relation to reduce function length.

    Args:
        request_id: Request tracking ID
        from_entity: Source entity name
        to_entity: Target entity name
        relation_type: Type of deleted relation

    Returns:
        JSONResponse with deletion confirmation
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "from_entity": from_entity,
                "to_entity": to_entity,
                "relation_type": relation_type,
                "deleted": True,
            },
            "message": "Relation deleted successfully",
            "request_id": request_id,
        },
    )
