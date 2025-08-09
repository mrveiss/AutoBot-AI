"""
System Knowledge Bridge API - Maps knowledge base facts to system knowledge format.
This bridges the gap between populated facts and frontend expectations.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
from datetime import datetime

from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/knowledge_base/system_knowledge", tags=["system_knowledge"]
)


@router.get("/documentation")
async def get_system_documentation() -> Dict[str, Any]:
    """
    Get system documentation from knowledge base facts.
    Maps facts with source 'project-documentation' to documentation format.
    """
    try:
        kb = KnowledgeBase()
        await kb.ainit()

        # Get all facts
        all_facts = await kb.get_all_facts()

        # Filter for documentation facts
        documentation_facts = [
            fact
            for fact in all_facts
            if fact.get("metadata", {}).get("source")
            in ["project-documentation", "project-docs"]
        ]

        # Format for frontend consumption
        formatted_docs = []
        for fact in documentation_facts:
            metadata = fact.get("metadata", {})
            content = fact.get("content", "")

            # Extract title from content or use filename
            title = metadata.get("filename", "Unknown Document")
            if "TITLE:" in content:
                try:
                    title_line = [
                        line
                        for line in content.split("\n")
                        if line.startswith("TITLE:")
                    ][0]
                    title = title_line.replace("TITLE:", "").strip()
                except IndexError:
                    pass

            # Determine document type from category or file extension
            doc_type = metadata.get("category", "documentation")
            if doc_type == "project-overview":
                doc_type = "readme"
            elif doc_type == "developer-docs":
                doc_type = "developer"
            elif doc_type == "user-guide":
                doc_type = "guide"

            formatted_doc = {
                "id": str(fact.get("id", 0)),
                "title": title,
                "name": metadata.get("relative_path", title),
                "content": content,
                "description": (
                    f"Project documentation: "
                    f"{metadata.get('relative_path', 'Unknown')}"
                ),
                "type": doc_type,
                "source": "project-docs",
                "version": "1.0",
                "status": "active",
                "immutable": False,  # Facts can be updated
                "updated_at": metadata.get("sync_time"),
                "created_at": fact.get("timestamp"),
                "metadata": {
                    "relative_path": metadata.get("relative_path"),
                    "filename": metadata.get("filename"),
                    "category": metadata.get("category"),
                    "file_size": metadata.get("file_size"),
                    "fact_id": fact.get("id"),
                },
            }
            formatted_docs.append(formatted_doc)

        # Sort by title for consistent display
        formatted_docs.sort(key=lambda x: x["title"])

        logger.info(f"Found {len(formatted_docs)} documentation facts")

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
    Get system prompts from knowledge base facts.
    Maps facts with prompts-related content to prompts format.
    """
    try:
        kb = KnowledgeBase()
        await kb.ainit()

        # Get all facts
        all_facts = await kb.get_all_facts()

        # Filter for prompt-related facts
        prompt_facts = [
            fact
            for fact in all_facts
            if "prompt" in fact.get("content", "").lower()
            or fact.get("metadata", {}).get("category") == "prompts"
            or "prompts/" in fact.get("metadata", {}).get("relative_path", "")
        ]

        # Format for frontend consumption
        formatted_prompts = []
        for fact in prompt_facts:
            metadata = fact.get("metadata", {})
            content = fact.get("content", "")

            # Extract title from content or use filename
            title = metadata.get("filename", "System Prompt")
            if "TITLE:" in content:
                try:
                    title_line = [
                        line
                        for line in content.split("\n")
                        if line.startswith("TITLE:")
                    ][0]
                    title = title_line.replace("TITLE:", "").strip()
                except IndexError:
                    pass

            # Extract prompt template from content
            template = content
            if "CONTENT:" in content:
                try:
                    content_start = content.find("CONTENT:") + 8
                    template = content[content_start:].strip()
                except IndexError:
                    pass

            formatted_prompt = {
                "id": str(fact.get("id", 0)),
                "name": title,
                "title": title,
                "description": (
                    f"System prompt from "
                    f"{metadata.get('relative_path', 'knowledge base')}"
                ),
                "template": template,
                "content": template,
                "category": metadata.get("category", "system"),
                "tags": ["system", "documentation"],
                "version": "1.0",
                "usage_count": 0,
                "immutable": False,
                "created_at": fact.get("timestamp"),
                "updated_at": metadata.get("sync_time"),
                "metadata": {
                    "relative_path": metadata.get("relative_path"),
                    "filename": metadata.get("filename"),
                    "source": metadata.get("source"),
                    "fact_id": fact.get("id"),
                },
            }
            formatted_prompts.append(formatted_prompt)

        # Sort by name for consistent display
        formatted_prompts.sort(key=lambda x: x["name"])

        logger.info(f"Found {len(formatted_prompts)} prompt facts")

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
    Import system documentation by running the sync script.
    """
    try:
        import subprocess
        import sys

        logger.info("Importing system documentation via sync script")

        # Run the sync script
        result = subprocess.run(
            [sys.executable, "scripts/sync_kb_docs.py"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            logger.info("Documentation sync completed successfully")
            return {
                "status": "success",
                "message": "System documentation imported successfully",
                "count": "Multiple documents imported",
                "details": {
                    "method": "sync_script",
                    "output": result.stdout[-500:] if result.stdout else "No output",
                },
            }
        else:
            logger.error(f"Documentation sync failed: {result.stderr}")
            raise HTTPException(
                status_code=500, detail=f"Import failed: {result.stderr}"
            )

    except subprocess.TimeoutExpired:
        logger.error("Documentation import timed out")
        raise HTTPException(
            status_code=500, detail="Import operation timed out after 5 minutes"
        )
    except Exception as e:
        logger.error(f"Error importing system documentation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to import system documentation: {str(e)}"
        )


@router.post("/import_prompts")
async def import_system_prompts() -> Dict[str, Any]:
    """
    Import system prompts from prompt files in the repository.
    """
    try:
        kb = KnowledgeBase()
        await kb.ainit()

        import os
        import glob

        # Find prompt files
        prompt_patterns = [
            "/home/kali/Desktop/AutoBot/prompts/**/*.md",
            "/home/kali/Desktop/AutoBot/prompts/**/*.txt",
        ]

        prompt_files = []
        for pattern in prompt_patterns:
            files = glob.glob(pattern, recursive=True)
            prompt_files.extend(files)

        imported_count = 0
        for file_path in prompt_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if not content.strip():
                    continue

                # Create enhanced searchable content
                rel_path = os.path.relpath(file_path, "/home/kali/Desktop/AutoBot")
                searchable_text = (
                    f"FILE: {rel_path}\n"
                    f"TITLE: {os.path.basename(file_path)}\n"
                    f"CONTENT:\n{content}"
                )

                metadata = {
                    "source": "project-documentation",
                    "category": "prompts",
                    "relative_path": rel_path,
                    "filename": os.path.basename(file_path),
                    "sync_time": datetime.now().isoformat(),
                    "file_size": len(content),
                }

                # Store as searchable fact
                result = await kb.store_fact(searchable_text, metadata)

                if result["status"] == "success":
                    imported_count += 1
                    logger.info(f"Imported prompt: {rel_path}")

            except Exception as e:
                logger.warning(f"Failed to import prompt {file_path}: {e}")
                continue

        return {
            "status": "success",
            "message": "System prompts imported successfully",
            "count": imported_count,
            "details": {
                "method": "direct_import",
                "files_processed": len(prompt_files),
                "successfully_imported": imported_count,
            },
        }

    except Exception as e:
        logger.error(f"Error importing system prompts: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to import system prompts: {str(e)}"
        )


@router.get("/categories")
async def get_knowledge_categories() -> Dict[str, Any]:
    """
    Get knowledge base categories from fact metadata.
    """
    try:
        kb = KnowledgeBase()
        await kb.ainit()

        # Get all facts
        all_facts = await kb.get_all_facts()

        # Aggregate categories from metadata
        categories = {}
        for fact in all_facts:
            metadata = fact.get("metadata", {})
            category = metadata.get("category", "uncategorized")

            if category not in categories:
                categories[category] = {
                    "name": category,
                    "description": f"Documents in {category} category",
                    "icon": get_category_icon(category),
                    "count": 0,
                    "last_updated": None,
                    "metadata": {},
                }

            categories[category]["count"] += 1

            # Update last updated time
            sync_time = metadata.get("sync_time")
            if sync_time and (
                not categories[category]["last_updated"]
                or sync_time > categories[category]["last_updated"]
            ):
                categories[category]["last_updated"] = sync_time

        formatted_categories = list(categories.values())

        logger.info(f"Found {len(formatted_categories)} categories from facts")

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


def get_category_icon(category: str) -> str:
    """Get appropriate icon for category."""
    icon_map = {
        "project-overview": "📋",
        "developer-docs": "👩‍💻",
        "user-guide": "📖",
        "reports": "📊",
        "documentation": "📄",
        "prompts": "💬",
        "guides": "🗺️",
        "api": "🔌",
        "configuration": "⚙️",
        "security": "🔒",
        "uncategorized": "📂",
    }
    return icon_map.get(category, "📁")


@router.get("/stats")
async def get_system_knowledge_stats() -> Dict[str, Any]:
    """
    Get system knowledge statistics from knowledge base.
    """
    try:
        kb = KnowledgeBase()
        await kb.ainit()

        # Get basic stats
        stats = await kb.get_stats()
        detailed_stats = await kb.get_detailed_stats()

        # Get facts breakdown
        all_facts = await kb.get_all_facts()
        doc_facts = len(
            [
                f
                for f in all_facts
                if f.get("metadata", {}).get("source") == "project-documentation"
            ]
        )
        prompt_facts = len(
            [
                f
                for f in all_facts
                if "prompt" in f.get("content", "").lower()
                or f.get("metadata", {}).get("category") == "prompts"
            ]
        )

        system_stats = {
            "total_documents": doc_facts,
            "total_prompts": prompt_facts,
            "total_facts": stats.get("total_facts", 0),
            "total_categories": len(stats.get("categories", [])),
            "total_size_bytes": detailed_stats.get("total_size", 0),
            "average_document_size": detailed_stats.get("avg_chunk_size", 0),
            "last_updated": detailed_stats.get("last_updated", "N/A"),
            "storage_type": "facts-based",
            "search_enabled": True,
        }

        return {"stats": system_stats, "status": "success"}

    except Exception as e:
        logger.error(f"Error retrieving system knowledge stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve system knowledge stats: {str(e)}",
        )
