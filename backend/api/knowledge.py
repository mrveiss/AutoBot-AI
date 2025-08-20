import logging
import os as os_module
import tempfile
from datetime import datetime
from typing import Optional
import aiohttp
import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agents.system_knowledge_manager import SystemKnowledgeManager
from src.knowledge_base import KnowledgeBase
from src.services.fact_extraction_service import FactExtractionService
from src.models.atomic_fact import FactType, TemporalType
from src.utils.entity_resolver import entity_resolver
from src.services.temporal_invalidation_service import get_temporal_invalidation_service

router = APIRouter()

logger = logging.getLogger(__name__)

knowledge_base: KnowledgeBase | None = None
system_knowledge_manager: SystemKnowledgeManager | None = None
fact_extraction_service: FactExtractionService | None = None


class GetFactRequest(BaseModel):
    fact_id: Optional[int] = None
    query: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5


async def init_knowledge_base():
    global knowledge_base, system_knowledge_manager, fact_extraction_service
    if knowledge_base is None:
        try:
            knowledge_base = KnowledgeBase()
            await knowledge_base.ainit()
            logger.info("Knowledge base initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize knowledge base: {str(e)}")
            knowledge_base = None

    if system_knowledge_manager is None and knowledge_base is not None:
        try:
            system_knowledge_manager = SystemKnowledgeManager(knowledge_base)
            logger.info("System knowledge manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize system knowledge manager: {str(e)}")
            system_knowledge_manager = None

    if fact_extraction_service is None and knowledge_base is not None:
        try:
            fact_extraction_service = FactExtractionService(knowledge_base)
            logger.info("Fact extraction service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize fact extraction service: {str(e)}")
            fact_extraction_service = None


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
async def search_knowledge(request: dict):
    """Search knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "results": [],
                "message": "Knowledge base not available",
                "query": request.get("query", ""),
                "limit": request.get("limit", 10),
            }

        query = request.get("query", "")
        limit = request.get("limit", 10)

        logger.info(f"Knowledge search request: {query} (limit: {limit})")

        results = await knowledge_base.search(query, limit)

        return {
            "results": results,
            "query": query,
            "limit": limit,
            "total_results": len(results),
        }
    except Exception as e:
        logger.error(f"Error in knowledge search: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error in knowledge search: {str(e)}"
        )


@router.post("/add_text")
async def add_text_to_knowledge(request: dict):
    """Add text to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        text = request.get("text", "")
        title = request.get("title", "")
        source = request.get("source", "Manual Entry")

        if not text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")

        logger.info(f"Knowledge add text request: {title} ({len(text)} chars)")

        metadata = {
            "title": title,
            "source": source,
            "type": "text",
            "content_type": "manual_entry",
        }

        result = await knowledge_base.store_fact(text, metadata)

        return {
            "status": result.get("status"),
            "message": result.get(
                "message", "Text added to knowledge base successfully"
            ),
            "fact_id": result.get("fact_id"),
            "text_length": len(text),
            "title": title,
            "source": source,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding text to knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding text to knowledge: {str(e)}"
        )


@router.post("/add_text_semantic")
async def add_text_with_semantic_chunking(request: dict):
    """Add text to knowledge base using semantic chunking for enhanced processing"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        text = request.get("text", "")
        title = request.get("title", "")
        source = request.get("source", "Manual Entry - Semantic")
        use_semantic = request.get("use_semantic", True)

        if not text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")

        logger.info(f"Knowledge semantic add text request: {title} ({len(text)} chars)")

        metadata = {
            "title": title,
            "source": source,
            "type": "text",
            "content_type": "semantic_chunked_entry",
            "processing_method": "semantic_chunking" if use_semantic else "traditional",
        }

        if use_semantic and hasattr(knowledge_base, 'add_text_with_semantic_chunking'):
            # Use the new semantic chunking method
            result = await knowledge_base.add_text_with_semantic_chunking(text, metadata)
        else:
            # Fallback to traditional method
            result = await knowledge_base.store_fact(text, metadata)
            result["semantic_chunking"] = False
            result["chunks_created"] = 1

        return {
            "status": result.get("status"),
            "message": result.get("message", "Text processed successfully"),
            "text_length": len(text),
            "title": title,
            "source": source,
            "chunks_created": result.get("chunks_created", 1),
            "semantic_chunking": result.get("semantic_chunking", False),
            "processing_method": metadata["processing_method"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding semantic text to knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding semantic text to knowledge: {str(e)}"
        )


@router.post("/add_url")
async def add_url_to_knowledge(request: dict):
    """Add URL to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        url = request.get("url", "")
        method = request.get("method", "fetch")

        if not url.strip():
            raise HTTPException(status_code=400, detail="URL is required")

        logger.info(f"Knowledge add URL request: {url} (method: {method})")

        if method == "fetch":
            # For now, store as reference - actual fetching would require
            # additional implementation
            metadata = {
                "url": url,
                "source": "URL",
                "type": "url_reference",
                "method": method,
                "content_type": "url",
            }

            content = f"URL Reference: {url}"
            result = await knowledge_base.store_fact(content, metadata)

            return {
                "status": result.get("status"),
                "message": result.get(
                    "message", "URL reference added to knowledge base"
                ),
                "fact_id": result.get("fact_id"),
                "url": url,
                "method": method,
            }
        else:
            # Store as reference only
            metadata = {
                "url": url,
                "source": "URL Reference",
                "type": "url_reference",
                "method": method,
                "content_type": "url",
            }

            content = f"URL Reference: {url}"
            result = await knowledge_base.store_fact(content, metadata)

            return {
                "status": result.get("status"),
                "message": result.get("message", "URL reference stored successfully"),
                "fact_id": result.get("fact_id"),
                "url": url,
                "method": method,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding URL to knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding URL to knowledge: {str(e)}"
        )


@router.post("/add_file")
async def add_file_to_knowledge(file: UploadFile = File(...)):
    """Add file to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        logger.info(
            f"Knowledge add file request: {file.filename} ({file.content_type})"
        )

        # Check if filename exists
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        # Get file extension
        file_ext = os_module.path.splitext(file.filename)[1].lower()
        supported_extensions = [".txt", ".pd", ".csv", ".docx", ".md"]

        if file_ext not in supported_extensions:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {file_ext}. "
                    f"Supported types: {', '.join(supported_extensions)}"
                ),
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
                "type": "document",
            }

            result = await knowledge_base.add_file(temp_file_path, file_type, metadata)

            return {
                "status": result.get("status"),
                "message": result.get(
                    "message", "File added to knowledge base successfully"
                ),
                "filename": file.filename,
                "file_type": file_type,
                "file_size": len(content),
            }
        finally:
            # Clean up temporary file
            try:
                os_module.unlink(temp_file_path)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to clean up temporary file {temp_file_path}: "
                    f"{cleanup_error}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding file to knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding file to knowledge: {str(e)}"
        )


@router.get("/export")
async def export_knowledge():
    """Export knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return JSONResponse(
                content={"message": "Knowledge base not available"},
                media_type="application/json",
            )

        logger.info("Knowledge export request")

        # Get all facts and data
        export_data = await knowledge_base.export_all_data()

        # Create export object with metadata
        export_object = {
            "export_timestamp": datetime.now().isoformat(),
            "total_entries": len(export_data),
            "version": "1.0",
            "data": export_data,
        }

        return JSONResponse(content=export_object, media_type="application/json")
    except Exception as e:
        logger.error(f"Error exporting knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error exporting knowledge: {str(e)}"
        )


@router.post("/cleanup")
async def cleanup_knowledge():
    """Cleanup knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        logger.info("Knowledge cleanup request")

        # Default to 30 days cleanup
        days_to_keep = 30
        result = await knowledge_base.cleanup_old_entries(days_to_keep)

        return {
            "status": result.get("status"),
            "message": result.get("message", "Knowledge base cleanup completed"),
            "removed_count": result.get("removed_count", 0),
            "days_kept": days_to_keep,
        }
    except Exception as e:
        logger.error(f"Error cleaning up knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error cleaning up knowledge: {str(e)}"
        )


@router.get("/stats")
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
                "message": "Knowledge base not available",
            }

        logger.info("Knowledge stats request")

        stats = await knowledge_base.get_stats()

        return stats
    except Exception as e:
        logger.error(f"Error getting knowledge stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting knowledge stats: {str(e)}"
        )


@router.get("/detailed_stats")
async def get_detailed_knowledge_stats():
    """Get detailed knowledge base statistics"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "message": "Knowledge base not available",
                "implementation_status": "unavailable",
            }

        logger.info("Detailed knowledge stats request")

        detailed_stats = await knowledge_base.get_detailed_stats()

        return detailed_stats
    except Exception as e:
        logger.error(f"Error getting detailed knowledge stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting detailed knowledge stats: {str(e)}"
        )


@router.get("/entries")
async def get_all_entries(collection: Optional[str] = None):
    """Get all knowledge entries, optionally filtered by collection"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {"success": True, "entries": []}

        if collection:
            entries = await knowledge_base.get_all_facts(collection)
        else:
            entries = await knowledge_base.get_all_facts("all")

        return {"success": True, "entries": entries}
    except Exception as e:
        logger.error(f"Error getting entries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entries")
async def create_knowledge_entry(entry: dict):
    """Create a new knowledge entry"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        # Support both old and new formats
        content = entry.get("content", entry.get("text", ""))
        metadata = entry.get("metadata", {})
        collection = entry.get("collection", "default")

        # Add additional fields from entry to metadata
        if "title" in entry:
            metadata["title"] = entry["title"]
        if "category" in entry:
            metadata["category"] = entry["category"]
        if "tags" in entry:
            metadata["tags"] = entry["tags"]

        if not content:
            raise HTTPException(status_code=400, detail="Content is required")

        # Add timestamp and collection to metadata
        metadata["created_at"] = datetime.now().isoformat()
        metadata["collection"] = collection

        # Store the fact
        result = await knowledge_base.store_fact(content, metadata)

        # Get the fact_id - try both possible keys
        fact_id = result.get("fact_id") or result.get("id")

        return {
            "success": True,
            "id": fact_id,  # Return 'id' for consistency with frontend expectations
            "entry_id": fact_id,  # Keep for backward compatibility
            "message": "Knowledge entry created successfully",
        }
    except Exception as e:
        logger.error(f"Error creating knowledge entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/entries/{entry_id}")
async def update_knowledge_entry(entry_id: str, entry: dict):
    """Update an existing knowledge entry"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        content = entry.get("content", "")
        metadata = entry.get("metadata", {})
        collection = entry.get("collection", "default")

        if not content:
            raise HTTPException(status_code=400, detail="Content is required")

        # Add updated timestamp and collection to metadata
        metadata["updated_at"] = datetime.now().isoformat()
        metadata["collection"] = collection

        # Update the entry
        success = await knowledge_base.update_fact(int(entry_id), content, metadata)

        if not success:
            raise HTTPException(status_code=404, detail="Entry not found")

        return {"success": True, "message": "Knowledge entry updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating knowledge entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entries/{entry_id}")
async def delete_knowledge_entry(entry_id: str):
    """Delete a knowledge entry"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        # Delete the entry
        success = await knowledge_base.delete_fact(int(entry_id))

        if not success:
            raise HTTPException(status_code=404, detail="Entry not found")

        return {"success": True, "message": "Knowledge entry deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting knowledge entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entries/{entry_id}")
async def get_knowledge_entry(entry_id: str):
    """Get a specific knowledge entry"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        # Get facts with the specific ID
        facts = await knowledge_base.get_fact(fact_id=int(entry_id))

        if not facts or len(facts) == 0:
            raise HTTPException(status_code=404, detail="Entry not found")

        return {"success": True, "entry": facts[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving knowledge entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crawl_url")
async def crawl_url(request: dict):
    """Crawl a URL and update knowledge base entry with extracted content"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")

        entry_id = request.get("entry_id")
        url = request.get("url")
        replace_content = request.get("replace_content", True)

        if not entry_id or not url:
            raise HTTPException(status_code=400, detail="entry_id and url are required")

        # Get existing entry
        facts = await knowledge_base.get_fact(fact_id=int(entry_id))

        if not facts or len(facts) == 0:
            raise HTTPException(
                status_code=404, detail=f"Entry with id {entry_id} not found"
            )

        entry = facts[0]

        # Import requests for web crawling
        try:
            import time

            import requests
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="Required libraries not available for web crawling",
            )

        # Crawl the URL
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                )
            }

            # Validate URL to prevent SSRF attacks
            from backend.services.url_validator import URLValidator

            validator = URLValidator()
            is_safe, error_msg = validator.is_safe_url(url)

            if not is_safe:
                return JSONResponse(
                    status_code=400, content={"error": f"Invalid URL: {error_msg}"}
                )

            # PERFORMANCE FIX: Convert blocking HTTP to async to prevent timeouts
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    response_content = await response.read()
                    content_type = response.headers.get("content-type", "")

            # Extract text content from HTML
            if "text/html" in content_type:
                try:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(response_content, "html.parser")

                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()

                    # Get text content
                    text_content = soup.get_text()

                    # Clean up text
                    lines = (line.strip() for line in text_content.splitlines())
                    chunks = (
                        phrase.strip() for line in lines for phrase in line.split("  ")
                    )
                    crawled_content = "\n".join(chunk for chunk in chunks if chunk)

                except ImportError:
                    # Fallback to raw text if BeautifulSoup not available
                    crawled_content = response_content.decode('utf-8', errors='ignore')

                # Limit content size (max 10000 characters)
                if len(crawled_content) > 10000:
                    crawled_content = (
                        crawled_content[:10000] + "... [Content truncated]"
                    )

            else:
                # For non-HTML content, use the raw text
                response_text = response_content.decode('utf-8', errors='ignore')
                crawled_content = response_text[:10000]
                if len(response_text) > 10000:
                    crawled_content += "... [Content truncated]"

            # Update the entry
            original_content = entry.get("content", "")
            original_metadata = entry.get("metadata", {})

            if replace_content:
                new_content = crawled_content
                new_metadata = {
                    **original_metadata,
                    "source": f"Crawled from {url}",
                    "url": url,
                    "crawled_at": time.time(),
                    "original_content": original_content,
                    "type": "crawled_content",
                }
            else:
                # Append to existing content
                new_content = (
                    f"{original_content}\n\n"
                    f"--- Crawled Content from {url} ---\n"
                    f"{crawled_content}"
                )
                new_metadata = {
                    **original_metadata,
                    "url": url,
                    "crawled_at": time.time(),
                    "type": "crawled_content",
                }

            # Update the entry in knowledge base
            success = await knowledge_base.update_fact(
                int(entry_id), new_content, new_metadata
            )

            if not success:
                raise HTTPException(
                    status_code=500, detail="Failed to update entry in knowledge base"
                )

            return {
                "success": True,
                "message": f"Successfully crawled content from {url}",
                "content_length": len(crawled_content),
                "url": url,
                "entry_id": entry_id,
            }

        except requests.exceptions.RequestException as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to fetch URL: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error crawling URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_knowledge_categories():
    """Get knowledge base categories with statistics"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "categories": [],
                "count": 0,
                "status": "error",
                "message": "Knowledge base not available",
            }

        logger.info("Knowledge categories request")

        # Get all entries and categorize them
        entries = await knowledge_base.get_all_facts("all")
        categories = {}

        for entry in entries:
            metadata = entry.get("metadata", {})
            collection = entry.get("collection", metadata.get("collection", "default"))

            if collection not in categories:
                categories[collection] = {
                    "name": collection,
                    "description": f"Entries in {collection} category",
                    "icon": "📁",
                    "count": 0,
                    "last_updated": None,
                    "metadata": {},
                }

            categories[collection]["count"] += 1

            # Update last_updated with most recent entry
            entry_date = metadata.get("created_at") or metadata.get("updated_at")
            if entry_date:
                if (
                    not categories[collection]["last_updated"]
                    or entry_date > categories[collection]["last_updated"]
                ):
                    categories[collection]["last_updated"] = entry_date

        # Convert to list format expected by frontend
        categories_list = list(categories.values())

        return {
            "categories": categories_list,
            "count": len(categories_list),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error getting knowledge categories: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting knowledge categories: {str(e)}"
        )


@router.get("/system_knowledge/documentation")
async def get_system_documentation():
    """Get all system documentation entries"""
    try:
        if knowledge_base is None or system_knowledge_manager is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "documentation": [],
                "count": 0,
                "status": "error",
                "message": "Knowledge base not available",
            }

        logger.info("System documentation request")

        # Get system documentation from knowledge base
        # Query for entries with system source or documentation type
        try:
            system_docs_entries = await knowledge_base.search(
                "type:system_documentation OR source:system", limit=100
            )
        except Exception:
            # Fallback to getting all entries and filtering
            all_entries = await knowledge_base.get_all_facts("all")
            system_docs_entries = []
            for entry in all_entries:
                metadata = entry.get("metadata", {})
                if (
                    metadata.get("type") == "system_documentation"
                    or metadata.get("source") == "system"
                    or "system" in metadata.get("tags", [])
                ):
                    system_docs_entries.append(entry)

        # Format for frontend consumption
        formatted_docs = []
        for entry in system_docs_entries:
            metadata = entry.get("metadata", {})
            formatted_doc = {
                "id": entry.get("id", "unknown"),
                "title": metadata.get("title", entry.get("content", "")[:50] + "..."),
                "name": metadata.get("name", metadata.get("title", "System Document")),
                "content": entry.get("content", ""),
                "description": metadata.get("description", "System documentation"),
                "type": metadata.get("type", "documentation"),
                "source": metadata.get("source", "system"),
                "version": metadata.get("version", "1.0"),
                "status": metadata.get("status", "active"),
                "immutable": metadata.get("immutable", True),
                "updated_at": metadata.get("updated_at"),
                "created_at": metadata.get("created_at"),
                "metadata": metadata,
            }
            formatted_docs.append(formatted_doc)

        return {
            "documentation": formatted_docs,
            "count": len(formatted_docs),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error retrieving system documentation: {e}")
        return {
            "documentation": [],
            "count": 0,
            "status": "error",
            "message": f"Failed to retrieve system documentation: {str(e)}",
        }


@router.get("/system_knowledge/prompts")
async def get_system_prompts():
    """Get all system prompts and templates"""
    try:
        if knowledge_base is None or system_knowledge_manager is None:
            await init_knowledge_base()

        if knowledge_base is None:
            return {
                "prompts": [],
                "count": 0,
                "status": "error",
                "message": "Knowledge base not available",
            }

        logger.info("System prompts request")

        # Get system prompts from knowledge base
        try:
            system_prompts_entries = await knowledge_base.search(
                "type:system_prompt OR type:prompt_template OR category:prompt",
                limit=100,
            )
        except Exception:
            # Fallback to getting all entries and filtering
            all_entries = await knowledge_base.get_all_facts("all")
            system_prompts_entries = []
            for entry in all_entries:
                metadata = entry.get("metadata", {})
                if (
                    metadata.get("type") in ["system_prompt", "prompt_template"]
                    or metadata.get("category") == "prompt"
                    or "prompt" in metadata.get("tags", [])
                ):
                    system_prompts_entries.append(entry)

        # Format for frontend consumption
        formatted_prompts = []
        for entry in system_prompts_entries:
            metadata = entry.get("metadata", {})
            formatted_prompt = {
                "id": entry.get("id", "unknown"),
                "name": metadata.get("name", metadata.get("title", "System Prompt")),
                "title": metadata.get("title", metadata.get("name", "System Prompt")),
                "description": metadata.get("description", "System prompt or template"),
                "template": entry.get("content", ""),
                "content": entry.get("content", ""),
                "category": metadata.get("category", "general"),
                "tags": metadata.get("tags", []),
                "version": metadata.get("version", "1.0"),
                "usage_count": metadata.get("usage_count", 0),
                "immutable": metadata.get("immutable", True),
                "created_at": metadata.get("created_at"),
                "updated_at": metadata.get("updated_at"),
                "metadata": metadata,
            }
            formatted_prompts.append(formatted_prompt)

        return {
            "prompts": formatted_prompts,
            "count": len(formatted_prompts),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error retrieving system prompts: {e}")
        return {
            "prompts": [],
            "count": 0,
            "status": "error",
            "message": f"Failed to retrieve system prompts: {str(e)}",
        }


@router.post("/system_knowledge/import_documentation")
async def import_system_documentation():
    """Import system documentation from templates and files"""
    try:
        if knowledge_base is None or system_knowledge_manager is None:
            await init_knowledge_base()

        if system_knowledge_manager is None:
            return {
                "status": "error",
                "message": "System knowledge manager not available",
                "count": 0,
            }

        logger.info("System documentation import request")

        # Initialize system knowledge (this will import documentation)
        await system_knowledge_manager.initialize_system_knowledge(
            force_reinstall=False
        )

        return {
            "status": "success",
            "message": "System documentation imported successfully",
            "count": 1,
        }

    except Exception as e:
        logger.error(f"Error importing system documentation: {e}")
        return {
            "status": "error",
            "message": f"Failed to import system documentation: {str(e)}",
            "count": 0,
        }


@router.post("/system_knowledge/import_prompts")
async def import_system_prompts():
    """Import system prompts from templates and files"""
    try:
        if knowledge_base is None or system_knowledge_manager is None:
            await init_knowledge_base()

        if system_knowledge_manager is None:
            return {
                "status": "error",
                "message": "System knowledge manager not available",
                "count": 0,
            }

        logger.info("System prompts import request")

        # Initialize system knowledge (this will import prompts)
        await system_knowledge_manager.initialize_system_knowledge(
            force_reinstall=False
        )

        return {
            "status": "success",
            "message": "System prompts imported successfully",
            "count": 1,
        }

    except Exception as e:
        logger.error(f"Error importing system prompts: {e}")
        return {
            "status": "error",
            "message": f"Failed to import system prompts: {str(e)}",
            "count": 0,
        }


# ====================================================================
# ATOMIC FACTS EXTRACTION API ENDPOINTS (RAG Optimization Phase 10)
# ====================================================================

@router.post("/extract_facts")
async def extract_facts_from_text(request: dict):
    """Extract atomic facts from text content using advanced RAG techniques"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        text = request.get("text", "")
        source = request.get("source", "manual_input")
        metadata = request.get("metadata", {})

        if not text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")

        logger.info(f"Atomic facts extraction request: {source} ({len(text)} chars)")

        # Extract and store atomic facts
        result = await fact_extraction_service.extract_and_store_facts(
            content=text,
            source=source,
            metadata=metadata
        )

        return {
            "status": result["status"],
            "message": result.get("message", "Facts extracted successfully"),
            "facts_extracted": result["facts_extracted"],
            "facts_stored": result["facts_stored"],
            "storage_errors": result.get("storage_errors", 0),
            "processing_time": result["processing_time"],
            "average_confidence": result.get("average_confidence", 0),
            "distributions": {
                "fact_types": result.get("fact_type_distribution", {}),
                "temporal_types": result.get("temporal_type_distribution", {}),
            },
            "text_length": len(text),
            "source": source
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting facts: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error extracting facts: {str(e)}"
        )


@router.post("/extract_facts_from_chunks")
async def extract_facts_from_semantic_chunks(request: dict):
    """Extract atomic facts from semantic chunks using parallel processing"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        chunks = request.get("chunks", [])
        source = request.get("source", "chunk_input")
        metadata = request.get("metadata", {})

        if not chunks:
            raise HTTPException(status_code=400, detail="Chunks are required")

        logger.info(f"Atomic facts extraction from chunks: {source} ({len(chunks)} chunks)")

        # Extract facts from semantic chunks
        result = await fact_extraction_service.extract_facts_from_chunks(
            chunks=chunks,
            source=source,
            metadata=metadata
        )

        return {
            "status": result["status"],
            "message": result.get("message", "Facts extracted from chunks successfully"),
            "facts_extracted": result["facts_extracted"],
            "facts_stored": result["facts_stored"],
            "storage_errors": result.get("storage_errors", 0),
            "chunks_processed": result["chunks_processed"],
            "successful_chunks": result.get("successful_chunks", 0),
            "processing_time": result["processing_time"],
            "average_confidence": result.get("average_confidence", 0),
            "distributions": result.get("fact_distributions", {}),
            "source": source
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting facts from chunks: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error extracting facts from chunks: {str(e)}"
        )


@router.get("/atomic_facts")
async def get_atomic_facts(
    source: Optional[str] = None,
    fact_type: Optional[str] = None,
    temporal_type: Optional[str] = None,
    min_confidence: Optional[float] = None,
    active_only: bool = True,
    limit: int = 100
):
    """Get atomic facts based on filtering criteria"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        # Convert string enums to enum objects
        fact_type_enum = None
        temporal_type_enum = None
        
        if fact_type:
            try:
                fact_type_enum = FactType(fact_type.upper())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid fact_type: {fact_type}")
        
        if temporal_type:
            try:
                temporal_type_enum = TemporalType(temporal_type.upper())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid temporal_type: {temporal_type}")

        logger.info(f"Atomic facts query: source={source}, type={fact_type}, temporal={temporal_type}")

        # Retrieve facts using criteria
        facts = await fact_extraction_service.get_facts_by_criteria(
            source=source,
            fact_type=fact_type_enum,
            temporal_type=temporal_type_enum,
            min_confidence=min_confidence,
            active_only=active_only,
            limit=limit
        )

        # Convert facts to dictionaries for JSON response
        facts_data = []
        for fact in facts:
            fact_dict = fact.to_dict()
            # Add readable statement
            fact_dict["statement"] = f"{fact.subject} {fact.predicate} {fact.object}"
            facts_data.append(fact_dict)

        return {
            "success": True,
            "facts": facts_data,
            "total_returned": len(facts_data),
            "filters_applied": {
                "source": source,
                "fact_type": fact_type,
                "temporal_type": temporal_type,
                "min_confidence": min_confidence,
                "active_only": active_only
            },
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving atomic facts: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving atomic facts: {str(e)}"
        )


@router.get("/facts/statistics")
async def get_fact_extraction_statistics():
    """Get statistics about atomic fact extraction operations"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        logger.info("Fact extraction statistics request")

        # Get comprehensive statistics
        stats = await fact_extraction_service.get_extraction_statistics()

        return {
            "success": True,
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting fact extraction statistics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting fact extraction statistics: {str(e)}"
        )


@router.post("/add_text_with_facts")
async def add_text_with_automatic_fact_extraction(request: dict):
    """Add text to knowledge base with automatic atomic fact extraction"""
    try:
        if knowledge_base is None or fact_extraction_service is None:
            await init_knowledge_base()

        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")
        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        text = request.get("text", "")
        title = request.get("title", "")
        source = request.get("source", "Manual Entry with Facts")
        extract_facts = request.get("extract_facts", True)

        if not text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")

        logger.info(f"Knowledge add text with facts: {title} ({len(text)} chars)")

        metadata = {
            "title": title,
            "source": source,
            "type": "text_with_facts",
            "content_type": "enhanced_entry",
            "facts_extraction_enabled": extract_facts,
        }

        # Store text using semantic chunking
        if hasattr(knowledge_base, 'add_text_with_semantic_chunking'):
            kb_result = await knowledge_base.add_text_with_semantic_chunking(text, metadata)
        else:
            kb_result = await knowledge_base.store_fact(text, metadata)
            kb_result["semantic_chunking"] = False
            kb_result["chunks_created"] = 1

        # Extract atomic facts if requested
        fact_result = {}
        if extract_facts:
            fact_result = await fact_extraction_service.extract_and_store_facts(
                content=text,
                source=f"{source}_facts",
                metadata=metadata
            )

        return {
            "status": "success",
            "message": "Text added with atomic facts extraction",
            "text_length": len(text),
            "title": title,
            "source": source,
            # Knowledge base results
            "kb_result": {
                "chunks_created": kb_result.get("chunks_created", 1),
                "semantic_chunking": kb_result.get("semantic_chunking", False),
            },
            # Fact extraction results
            "fact_extraction": {
                "enabled": extract_facts,
                "facts_extracted": fact_result.get("facts_extracted", 0),
                "facts_stored": fact_result.get("facts_stored", 0),
                "processing_time": fact_result.get("processing_time", 0),
                "average_confidence": fact_result.get("average_confidence", 0),
            } if extract_facts else {"enabled": False}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding text with facts: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error adding text with facts: {str(e)}"
        )


# ====================================================================  
# ENTITY RESOLUTION API ENDPOINTS (RAG Optimization Phase 10)
# ====================================================================

@router.post("/resolve_entities")
async def resolve_entity_names(request: dict):
    """Resolve a list of entity names to canonical entities using semantic similarity"""
    try:
        entity_names = request.get("entity_names", [])
        context = request.get("context", {})

        if not entity_names:
            raise HTTPException(status_code=400, detail="Entity names list is required")

        logger.info(f"Entity resolution request: {len(entity_names)} entities")

        # Resolve entities using the entity resolver
        result = await entity_resolver.resolve_entities(
            entity_names=entity_names,
            context=context
        )

        # Convert to JSON-serializable format
        canonical_entities_data = []
        for mapping in result.canonical_entities:
            canonical_entities_data.append(mapping.to_dict())

        return {
            "success": True,
            "original_entities": result.original_entities,
            "resolved_mappings": result.resolved_mappings,
            "canonical_entities": canonical_entities_data,
            "resolution_summary": result.get_resolution_summary(),
            "processing_time": result.processing_time,
            "similarity_method": result.similarity_method.value,
            "confidence_threshold": result.confidence_threshold
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving entities: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error resolving entities: {str(e)}"
        )


@router.get("/entity_mappings")
async def get_entity_mappings(
    entity_type: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100
):
    """Get entity mappings with optional filtering"""
    try:
        logger.info(f"Entity mappings request: type={entity_type}, min_confidence={min_confidence}")

        # Get resolution statistics which includes mapping information
        stats = await entity_resolver.get_resolution_statistics()
        
        # For now, return the statistics as we don't have a direct method to get mappings
        # In a full implementation, we would add a get_entity_mappings method to EntityResolver
        return {
            "success": True,
            "statistics": stats,
            "message": "Entity mappings accessible through resolution operations",
            "filters": {
                "entity_type": entity_type,
                "min_confidence": min_confidence,
                "limit": limit
            }
        }
    except Exception as e:
        logger.error(f"Error getting entity mappings: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting entity mappings: {str(e)}"
        )


@router.get("/entity_resolution/statistics")
async def get_entity_resolution_statistics():
    """Get comprehensive statistics about entity resolution operations"""
    try:
        logger.info("Entity resolution statistics request")

        # Get statistics from the entity resolver
        stats = await entity_resolver.get_resolution_statistics()

        return {
            "success": True,
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting entity resolution statistics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting entity resolution statistics: {str(e)}"
        )


@router.post("/facts/resolve_entities")
async def resolve_entities_in_facts(request: dict):
    """Apply entity resolution to existing atomic facts"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        # Get parameters
        source = request.get("source")
        limit = request.get("limit", 100)
        min_confidence = request.get("min_confidence")

        logger.info(f"Resolving entities in facts: source={source}, limit={limit}")

        # Get facts to process
        facts = await fact_extraction_service.get_facts_by_criteria(
            source=source,
            min_confidence=min_confidence,
            limit=limit
        )

        if not facts:
            return {
                "success": True,
                "message": "No facts found matching criteria",
                "facts_processed": 0,
                "entities_resolved": 0
            }

        # Apply entity resolution to facts
        original_count = len(facts)
        resolved_facts = await entity_resolver.resolve_facts_entities(facts)

        # Count unique entities before and after resolution
        original_entities = set()
        resolved_entities = set()
        
        for fact in facts:
            original_entities.update(fact.entities)
            original_entities.add(fact.subject)
            original_entities.add(fact.object)
            
        for fact in resolved_facts:
            resolved_entities.update(fact.entities)
            resolved_entities.add(fact.subject)
            resolved_entities.add(fact.object)

        return {
            "success": True,
            "message": "Entity resolution applied to facts",
            "facts_processed": original_count,
            "entities_before": len(original_entities),
            "entities_after": len(resolved_entities),
            "entities_resolved": len(original_entities) - len(resolved_entities),
            "resolution_rate": round((len(original_entities) - len(resolved_entities)) / len(original_entities) * 100, 1) if original_entities else 0,
            "filters": {
                "source": source,
                "min_confidence": min_confidence,
                "limit": limit
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving entities in facts: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error resolving entities in facts: {str(e)}"
        )


# ====================================================================
# TEMPORAL KNOWLEDGE INVALIDATION API ENDPOINTS (RAG Optimization Phase 10)
# ====================================================================

@router.post("/temporal/invalidation/sweep")
async def run_temporal_invalidation_sweep(request: dict):
    """Run a temporal knowledge invalidation sweep"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        # Get parameters
        source_filter = request.get("source_filter")
        dry_run = request.get("dry_run", True)  # Default to dry run for safety

        logger.info(f"Temporal invalidation sweep: source={source_filter}, dry_run={dry_run}")

        # Get temporal invalidation service
        temporal_service = get_temporal_invalidation_service(fact_extraction_service)

        # Run invalidation sweep
        result = await temporal_service.run_invalidation_sweep(
            source_filter=source_filter,
            dry_run=dry_run
        )

        return {
            "success": True,
            "invalidation_sweep": result,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running temporal invalidation sweep: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error running temporal invalidation sweep: {str(e)}"
        )


@router.get("/temporal/invalidation/statistics")
async def get_temporal_invalidation_statistics():
    """Get comprehensive temporal invalidation statistics"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        logger.info("Temporal invalidation statistics request")

        # Get temporal invalidation service
        temporal_service = get_temporal_invalidation_service(fact_extraction_service)

        # Get statistics
        stats = await temporal_service.get_invalidation_statistics()

        return {
            "success": True,
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting temporal invalidation statistics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting temporal invalidation statistics: {str(e)}"
        )


@router.post("/temporal/invalidation/initialize_rules")
async def initialize_temporal_invalidation_rules():
    """Initialize default temporal invalidation rules"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        logger.info("Initializing temporal invalidation rules")

        # Get temporal invalidation service
        temporal_service = get_temporal_invalidation_service(fact_extraction_service)

        # Initialize rules
        result = await temporal_service.initialize_rules()

        return {
            "success": True,
            "initialization_result": result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error initializing temporal invalidation rules: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error initializing temporal invalidation rules: {str(e)}"
        )


@router.post("/temporal/invalidation/contradiction_check")
async def check_fact_contradictions(request: dict):
    """Check for contradictions between facts and invalidate conflicting ones"""
    try:
        if fact_extraction_service is None:
            await init_knowledge_base()

        if fact_extraction_service is None:
            raise HTTPException(status_code=503, detail="Fact extraction service not available")

        # Get parameters
        fact_id = request.get("fact_id")
        if not fact_id:
            raise HTTPException(status_code=400, detail="fact_id is required")

        logger.info(f"Checking contradictions for fact: {fact_id}")

        # Get the fact to check
        facts = await fact_extraction_service.get_facts_by_criteria(limit=1000)
        target_fact = None
        for fact in facts:
            if fact.fact_id == fact_id:
                target_fact = fact
                break

        if not target_fact:
            raise HTTPException(status_code=404, detail="Fact not found")

        # Get temporal invalidation service
        temporal_service = get_temporal_invalidation_service(fact_extraction_service)

        # Check for contradictions
        result = await temporal_service.invalidate_contradictory_facts(target_fact)

        return {
            "success": True,
            "fact_id": fact_id,
            "contradiction_check": result,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking fact contradictions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error checking fact contradictions: {str(e)}"
        )
