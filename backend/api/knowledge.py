from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import tempfile
import os as os_module

from src.knowledge_base import KnowledgeBase

router = APIRouter()

logger = logging.getLogger(__name__)

knowledge_base: KnowledgeBase | None = None

class GetFactRequest(BaseModel):
    fact_id: Optional[int] = None
    query: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5


async def init_knowledge_base():
    global knowledge_base
    if knowledge_base is None:
        try:
            knowledge_base = KnowledgeBase()
            await knowledge_base.ainit()
            logger.info("Knowledge base initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize knowledge base: {str(e)}")
            knowledge_base = None

@router.post("/get_fact")
async def get_fact_api(fact_id: Optional[int] = None, query: Optional[str] = None):
    """API to retrieve facts from the knowledge base."""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            return {"facts": [], "message": "Knowledge base not available"}
        
        facts = knowledge_base.get_fact(fact_id=fact_id, query=query)
        return {"facts": facts}
    except Exception as e:
        logger.error(f"Error getting fact: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get fact: {str(e)}")

@router.post("/search")
async def search_knowledge_base_api(query: str = Form(...), n_results: int = Form(5)):
    """API to search the vector store in the knowledge base."""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            return {"results": [], "message": "Knowledge base not available"}
        
        results = knowledge_base.search(query, n_results)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error searching knowledge base: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to search knowledge base: {str(e)}")

@router.post("/knowledge/search")
async def search_knowledge(request: dict):
    """Search knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "results": [],
                "message": "Knowledge base not available",
                "query": request.get('query', ''),
                "limit": request.get('limit', 10)
            }

        query = request.get('query', '')
        limit = request.get('limit', 10)

        logger.info(f"Knowledge search request: {query} (limit: {limit})")

        results = await knowledge_base.search(query, limit)

        return {
            "results": results,
            "query": query,
            "limit": limit,
            "total_results": len(results)
        }
    except Exception as e:
        logger.error(f"Error in knowledge search: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error in knowledge search: {str(e)}")


@router.post("/knowledge/add_text")
async def add_text_to_knowledge(request: dict):
    """Add text to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(
                status_code=503, detail="Knowledge base not available")

        text = request.get('text', '')
        title = request.get('title', '')
        source = request.get('source', 'Manual Entry')

        if not text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")

        logger.info(f"Knowledge add text request: {title} ({len(text)} chars)")

        metadata = {
            "title": title,
            "source": source,
            "type": "text",
            "content_type": "manual_entry"
        }

        result = await knowledge_base.store_fact(text, metadata)

        return {
            "status": result.get("status"),
            "message": result.get("message", "Text added to knowledge base successfully"),
            "fact_id": result.get("fact_id"),
            "text_length": len(text),
            "title": title,
            "source": source
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding text to knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding text to knowledge: {str(e)}")


@router.post("/knowledge/add_url")
async def add_url_to_knowledge(request: dict):
    """Add URL to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(
                status_code=503, detail="Knowledge base not available")

        url = request.get('url', '')
        method = request.get('method', 'fetch')

        if not url.strip():
            raise HTTPException(status_code=400, detail="URL is required")

        logger.info(f"Knowledge add URL request: {url} (method: {method})")

        if method == 'fetch':
            # For now, store as reference - actual fetching would require additional implementation
            metadata = {
                "url": url,
                "source": "URL",
                "type": "url_reference",
                "method": method,
                "content_type": "url"
            }

            content = f"URL Reference: {url}"
            result = await knowledge_base.store_fact(content, metadata)

            return {
                "status": result.get("status"),
                "message": result.get("message", "URL reference added to knowledge base"),
                "fact_id": result.get("fact_id"),
                "url": url,
                "method": method
            }
        else:
            # Store as reference only
            metadata = {
                "url": url,
                "source": "URL Reference",
                "type": "url_reference",
                "method": method,
                "content_type": "url"
            }

            content = f"URL Reference: {url}"
            result = await knowledge_base.store_fact(content, metadata)

            return {
                "status": result.get("status"),
                "message": result.get("message", "URL reference stored successfully"),
                "fact_id": result.get("fact_id"),
                "url": url,
                "method": method
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding URL to knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding URL to knowledge: {str(e)}")


@router.post("/knowledge/add_file")
async def add_file_to_knowledge(file: UploadFile = File(...)):
    """Add file to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(
                status_code=503, detail="Knowledge base not available")

        logger.info(
            f"Knowledge add file request: {file.filename} ({file.content_type})")

        # Check if filename exists
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        # Get file extension
        file_ext = os_module.path.splitext(file.filename)[1].lower()
        supported_extensions = ['.txt', '.pdf', '.csv', '.docx', '.md']

        if file_ext not in supported_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Supported types: {', '.join(supported_extensions)}"
            )

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        try:
            # Determine file type
            file_type = file_ext[1:]  # Remove the dot

            # Add file to knowledge base
            metadata = {
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size": len(content),
                "source": "File Upload",
                "type": "document"
            }

            result = await knowledge_base.add_file(temp_file_path, file_type, metadata)

            return {
                "status": result.get("status"),
                "message": result.get("message", "File added to knowledge base successfully"),
                "filename": file.filename,
                "file_type": file_type,
                "file_size": len(content)
            }
        finally:
            # Clean up temporary file
            try:
                os_module.unlink(temp_file_path)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to clean up temporary file {temp_file_path}: {cleanup_error}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding file to knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding file to knowledge: {str(e)}")


@router.get("/knowledge/export")
async def export_knowledge():
    """Export knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return JSONResponse(
                content={"message": "Knowledge base not available"},
                media_type="application/json"
            )

        logger.info("Knowledge export request")

        # Get all facts and data
        export_data = await knowledge_base.export_all_data()

        # Create export object with metadata
        export_object = {
            "export_timestamp": datetime.now().isoformat(),
            "total_entries": len(export_data),
            "version": "1.0",
            "data": export_data
        }

        return JSONResponse(
            content=export_object,
            media_type="application/json"
        )
    except Exception as e:
        logger.error(f"Error exporting knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error exporting knowledge: {str(e)}")


@router.post("/knowledge/cleanup")
async def cleanup_knowledge():
    """Cleanup knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(
                status_code=503, detail="Knowledge base not available")

        logger.info("Knowledge cleanup request")

        # Default to 30 days cleanup
        days_to_keep = 30
        result = await knowledge_base.cleanup_old_entries(days_to_keep)

        return {
            "status": result.get("status"),
            "message": result.get("message", "Knowledge base cleanup completed"),
            "removed_count": result.get("removed_count", 0),
            "days_kept": days_to_keep
        }
    except Exception as e:
        logger.error(f"Error cleaning up knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error cleaning up knowledge: {str(e)}")


@router.get("/knowledge/stats")
async def get_knowledge_stats():
    """Get knowledge base statistics"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "total_facts": 0,
                "total_documents": 0,
                "total_vectors": 0,
                "db_size": 0,
                "message": "Knowledge base not available"
            }

        logger.info("Knowledge stats request")

        stats = await knowledge_base.get_stats()

        return stats
    except Exception as e:
        logger.error(f"Error getting knowledge stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting knowledge stats: {str(e)}")


@router.get("/knowledge/detailed_stats")
async def get_detailed_knowledge_stats():
    """Get detailed knowledge base statistics"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "message": "Knowledge base not available",
                "implementation_status": "unavailable"
            }

        logger.info("Detailed knowledge stats request")

        detailed_stats = await knowledge_base.get_detailed_stats()

        return detailed_stats
    except Exception as e:
        logger.error(f"Error getting detailed knowledge stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting detailed knowledge stats: {str(e)}")
