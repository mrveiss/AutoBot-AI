"""
System Knowledge API endpoints for managing system documentation and prompts.
Provides endpoints for retrieving, importing, and managing system knowledge.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from src.manage_system_knowledge import SystemKnowledgeManager
from src.config import Config

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/system_knowledge", tags=["system_knowledge"])

# Initialize system knowledge manager
config = Config()
knowledge_manager = SystemKnowledgeManager(config)


@router.get("/documentation")
async def get_system_documentation() -> Dict[str, Any]:
    """
    Get all system documentation entries.

    Returns:
        Dict containing documentation entries with metadata
    """
    try:
        # Get system knowledge from the knowledge manager
        system_docs = knowledge_manager.get_system_documentation()

        # Format for frontend consumption
        formatted_docs = []
        for doc_id, doc_data in system_docs.items():
            formatted_doc = {
                "id": doc_id,
                "title": doc_data.get("title", doc_id),
                "name": doc_data.get("name", doc_id),
                "content": doc_data.get("content", ""),
                "description": doc_data.get("description", ""),
                "type": doc_data.get("type", "documentation"),
                "source": doc_data.get("source", "system"),
                "version": doc_data.get("version", "1.0"),
                "status": doc_data.get("status", "active"),
                "immutable": doc_data.get("immutable", True),
                "updated_at": doc_data.get("updated_at"),
                "created_at": doc_data.get("created_at"),
                "metadata": doc_data.get("metadata", {}),
            }
            formatted_docs.append(formatted_doc)

        return {
            "documentation": formatted_docs,
            "count": len(formatted_docs),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error retrieving system documentation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve system documentation: {str(e)}"
        )


@router.get("/prompts")
async def get_system_prompts() -> Dict[str, Any]:
    """
    Get all system prompts and templates.

    Returns:
        Dict containing prompt entries with metadata
    """
    try:
        # Get system prompts from the knowledge manager
        system_prompts = knowledge_manager.get_system_prompts()

        # Format for frontend consumption
        formatted_prompts = []
        for prompt_id, prompt_data in system_prompts.items():
            formatted_prompt = {
                "id": prompt_id,
                "name": prompt_data.get("name", prompt_id),
                "title": prompt_data.get("title", prompt_id),
                "description": prompt_data.get("description", ""),
                "template": prompt_data.get("template", ""),
                "content": prompt_data.get("content", prompt_data.get("template", "")),
                "category": prompt_data.get("category", "general"),
                "tags": prompt_data.get("tags", []),
                "version": prompt_data.get("version", "1.0"),
                "usage_count": prompt_data.get("usage_count", 0),
                "immutable": prompt_data.get("immutable", True),
                "created_at": prompt_data.get("created_at"),
                "updated_at": prompt_data.get("updated_at"),
                "metadata": prompt_data.get("metadata", {}),
            }
            formatted_prompts.append(formatted_prompt)

        return {
            "prompts": formatted_prompts,
            "count": len(formatted_prompts),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error retrieving system prompts: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve system prompts: {str(e)}"
        )


@router.post("/import_documentation")
async def import_system_documentation() -> Dict[str, Any]:
    """
    Import system documentation from templates and files.

    Returns:
        Dict with import results
    """
    try:
        # Import system documentation
        import_result = knowledge_manager.import_system_documentation()

        return {
            "status": "success",
            "message": "System documentation imported successfully",
            "count": import_result.get("imported_count", 0),
            "details": import_result,
        }

    except Exception as e:
        logger.error(f"Error importing system documentation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to import system documentation: {str(e)}"
        )


@router.post("/import_prompts")
async def import_system_prompts() -> Dict[str, Any]:
    """
    Import system prompts from templates and files.

    Returns:
        Dict with import results
    """
    try:
        # Import system prompts
        import_result = knowledge_manager.import_system_prompts()

        return {
            "status": "success",
            "message": "System prompts imported successfully",
            "count": import_result.get("imported_count", 0),
            "details": import_result,
        }

    except Exception as e:
        logger.error(f"Error importing system prompts: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to import system prompts: {str(e)}"
        )


@router.get("/categories")
async def get_knowledge_categories() -> Dict[str, Any]:
    """
    Get knowledge base categories with statistics.

    Returns:
        Dict containing categories with entry counts and metadata
    """
    try:
        # Get categories from knowledge base
        categories = knowledge_manager.get_knowledge_categories()

        # Format for frontend consumption
        formatted_categories = []
        for category_name, category_data in categories.items():
            formatted_category = {
                "name": category_name,
                "description": category_data.get(
                    "description", f"Entries in {category_name} category"
                ),
                "icon": category_data.get("icon", "📁"),
                "count": category_data.get("count", 0),
                "last_updated": category_data.get("last_updated"),
                "metadata": category_data.get("metadata", {}),
            }
            formatted_categories.append(formatted_category)

        return {
            "categories": formatted_categories,
            "count": len(formatted_categories),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error retrieving knowledge categories: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve knowledge categories: {str(e)}"
        )


@router.get("/documentation/{doc_id}")
async def get_documentation_by_id(doc_id: str) -> Dict[str, Any]:
    """
    Get specific system documentation by ID.

    Args:
        doc_id: Documentation identifier

    Returns:
        Dict containing documentation details
    """
    try:
        doc_data = knowledge_manager.get_system_documentation_by_id(doc_id)

        if not doc_data:
            raise HTTPException(
                status_code=404, detail=f"Documentation with ID '{doc_id}' not found"
            )

        return {"documentation": doc_data, "status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving documentation {doc_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve documentation: {str(e)}"
        )


@router.get("/prompts/{prompt_id}")
async def get_prompt_by_id(prompt_id: str) -> Dict[str, Any]:
    """
    Get specific system prompt by ID.

    Args:
        prompt_id: Prompt identifier

    Returns:
        Dict containing prompt details
    """
    try:
        prompt_data = knowledge_manager.get_system_prompt_by_id(prompt_id)

        if not prompt_data:
            raise HTTPException(
                status_code=404, detail=f"Prompt with ID '{prompt_id}' not found"
            )

        return {"prompt": prompt_data, "status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving prompt {prompt_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve prompt: {str(e)}"
        )


@router.post("/prompts/{prompt_id}/use")
async def use_system_prompt(prompt_id: str) -> Dict[str, Any]:
    """
    Mark a system prompt as used (increment usage counter).

    Args:
        prompt_id: Prompt identifier

    Returns:
        Dict with operation result
    """
    try:
        result = knowledge_manager.increment_prompt_usage(prompt_id)

        return {
            "status": "success",
            "message": f"Prompt usage recorded for '{prompt_id}'",
            "usage_count": result.get("usage_count", 0),
        }

    except Exception as e:
        logger.error(f"Error recording prompt usage {prompt_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to record prompt usage: {str(e)}"
        )


@router.get("/stats")
async def get_system_knowledge_stats() -> Dict[str, Any]:
    """
    Get system knowledge statistics.

    Returns:
        Dict containing statistics about system knowledge
    """
    try:
        stats = knowledge_manager.get_system_knowledge_stats()

        return {"stats": stats, "status": "success"}

    except Exception as e:
        logger.error(f"Error retrieving system knowledge stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve system knowledge stats: {str(e)}",
        )
