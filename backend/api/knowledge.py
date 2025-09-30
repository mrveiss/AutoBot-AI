"""Knowledge Base API endpoints for content management and search with RAG integration."""
import logging
import asyncio
import json
import subprocess
import sys
from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from backend.knowledge_factory import get_or_create_knowledge_base

# Import RAG Agent for enhanced search capabilities
try:
    from src.agents.rag_agent import get_rag_agent
    from src.agents.agent_orchestrator import get_agent_orchestrator
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logging.warning("RAG Agent not available - enhanced search features disabled")

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/stats")
async def get_knowledge_stats(req: Request):
    """Get knowledge base statistics - FIXED to use proper instance"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "total_documents": 0,
                "total_chunks": 0,
                "total_facts": 0,
                "total_vectors": 0,
                "categories": [],
                "db_size": 0,
                "status": "offline",
                "last_updated": None,
                "redis_db": None,
                "index_name": None,
                "initialized": False,
                "rag_available": RAG_AVAILABLE
            }

        stats = await kb_to_use.get_stats()
        stats["rag_available"] = RAG_AVAILABLE
        return stats

    except Exception as e:
        logger.error(f"Error getting knowledge stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stats failed: {str(e)}")


@router.get("/stats/basic")
async def get_knowledge_stats_basic(req: Request):
    """Get basic knowledge base statistics for quick display"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "total_facts": 0,
                "total_vectors": 0,
                "status": "offline"
            }

        stats = await kb_to_use.get_stats()

        # Return lightweight basic stats
        return {
            "total_facts": stats.get("total_facts", 0),
            "total_vectors": stats.get("total_vectors", 0),
            "categories": stats.get("categories", []),
            "status": "online" if stats.get("initialized", False) else "offline"
        }

    except Exception as e:
        logger.error(f"Error getting basic knowledge stats: {str(e)}")
        return {
            "total_facts": 0,
            "total_vectors": 0,
            "status": "error"
        }


@router.get("/categories")
async def get_knowledge_categories(req: Request):
    """Get all knowledge base categories with fact counts"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "categories": [],
                "total": 0
            }

        # Get stats - call sync method directly (no await)
        stats = kb_to_use.get_stats() if hasattr(kb_to_use, 'get_stats') else {}
        categories_list = stats.get("categories", [])

        # Get all facts to count by category - sync redis operation
        try:
            all_facts_data = kb_to_use.redis_client.hgetall("knowledge_base:facts")
        except Exception as redis_err:
            logger.debug(f"Redis error getting facts: {redis_err}")
            all_facts_data = {}

        category_counts = {}
        for fact_json in all_facts_data.values():
            try:
                fact = json.loads(fact_json)
                category = fact.get("metadata", {}).get("category", "uncategorized")
                category_counts[category] = category_counts.get(category, 0) + 1
            except:
                continue

        # Format for frontend with counts
        categories = [
            {
                "name": cat,
                "count": category_counts.get(cat, 0),
                "id": cat
            }
            for cat in categories_list
        ]

        return {
            "categories": categories,
            "total": len(categories)
        }

    except Exception as e:
        logger.error(f"Error getting categories: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "categories": [],
            "total": 0
        }


@router.post("/add_text")
async def add_text_to_knowledge(request: dict, req: Request):
    """Add text to knowledge base - FIXED to use proper instance"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors"
            }

        text = request.get("text", "")
        title = request.get("title", "")
        source = request.get("source", "manual")
        category = request.get("category", "general")

        if not text:
            raise HTTPException(status_code=400, detail="Text content is required")

        logger.info(f"Adding text to knowledge: title='{title}', source='{source}', length={len(text)}")

        # Use the store_fact method for KnowledgeBaseV2 or add_fact for compatibility
        if hasattr(kb_to_use, 'store_fact'):
            # KnowledgeBaseV2
            result = await kb_to_use.store_fact(
                content=text,
                metadata={
                    "title": title,
                    "source": source,
                    "category": category
                }
            )
            fact_id = result.get("fact_id")
        else:
            # Original KnowledgeBase
            result = await kb_to_use.store_fact(
                text=text,
                metadata={
                    "title": title,
                    "source": source,
                    "category": category
                }
            )
            fact_id = result.get("fact_id")

        return {
            "status": "success",
            "message": "Fact stored successfully",
            "fact_id": fact_id,
            "text_length": len(text),
            "title": title,
            "source": source
        }

    except Exception as e:
        logger.error(f"Error adding text to knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Add text failed: {str(e)}")


@router.post("/search")
async def search_knowledge(request: dict, req: Request):
    """Search knowledge base with optional RAG enhancement - FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "results": [],
                "total_results": 0,
                "message": "Knowledge base not initialized - please check logs for errors"
            }

        query = request.get("query", "")
        top_k = request.get("top_k", 10)
        limit = request.get("limit", 10)  # Also accept 'limit' for compatibility
        mode = request.get("mode", "auto")
        use_rag = request.get("use_rag", False)  # New parameter for RAG enhancement

        # Use limit if provided, otherwise use top_k
        search_limit = limit if request.get("limit") is not None else top_k

        logger.info(f"Knowledge search request: '{query}' (top_k={search_limit}, mode={mode}, use_rag={use_rag})")

        # FIXED: Check which knowledge base implementation we're using and call with correct parameters
        kb_class_name = kb_to_use.__class__.__name__

        if kb_class_name == "KnowledgeBaseV2":
            # KnowledgeBaseV2 uses 'top_k' parameter
            results = await kb_to_use.search(
                query=query,
                top_k=search_limit
            )
        else:
            # Original KnowledgeBase uses 'similarity_top_k' parameter
            results = await kb_to_use.search(
                query=query,
                similarity_top_k=search_limit,
                mode=mode
            )

        # Enhanced search with RAG if requested and available
        if use_rag and RAG_AVAILABLE and results:
            try:
                rag_enhancement = await _enhance_search_with_rag(query, results)
                return {
                    "results": results,
                    "total_results": len(results),
                    "query": query,
                    "mode": mode,
                    "kb_implementation": kb_class_name,
                    "rag_enhanced": True,
                    "rag_analysis": rag_enhancement
                }
            except Exception as e:
                logger.error(f"RAG enhancement failed: {e}")
                # Continue with regular results if RAG fails

        return {
            "results": results,
            "total_results": len(results),
            "query": query,
            "mode": mode,
            "kb_implementation": kb_class_name,
            "rag_enhanced": False
        }

    except Exception as e:
        logger.error(f"Error searching knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/rag_search")
async def rag_enhanced_search(request: dict, req: Request):
    """RAG-enhanced knowledge search for comprehensive document synthesis"""
    try:
        if not RAG_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="RAG functionality not available - AI Stack may not be running"
            )

        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "synthesized_response": "",
                "results": [],
                "message": "Knowledge base not initialized - please check logs for errors"
            }

        query = request.get("query", "")
        top_k = request.get("top_k", 10)
        limit = request.get("limit", 10)
        reformulate_query = request.get("reformulate_query", True)

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Use limit if provided, otherwise use top_k
        search_limit = limit if request.get("limit") is not None else top_k

        logger.info(f"RAG-enhanced search request: '{query}' (top_k={search_limit}, reformulate={reformulate_query})")

        # Step 1: Query reformulation if requested
        original_query = query
        reformulated_queries = [query]

        if reformulate_query:
            try:
                rag_agent = get_rag_agent()
                reformulation_result = await rag_agent.reformulate_query(query)

                if reformulation_result.get("status") == "success":
                    additional_queries = reformulation_result.get("reformulated_queries", [])
                    reformulated_queries.extend(additional_queries[:3])  # Limit to avoid too many queries

            except Exception as e:
                logger.warning(f"Query reformulation failed: {e}")

        # Step 2: Search with all queries
        all_results = []
        seen_content = set()

        for search_query in reformulated_queries:
            try:
                # Get search results
                kb_class_name = kb_to_use.__class__.__name__

                if kb_class_name == "KnowledgeBaseV2":
                    query_results = await kb_to_use.search(
                        query=search_query,
                        top_k=search_limit
                    )
                else:
                    query_results = await kb_to_use.search(
                        query=search_query,
                        similarity_top_k=search_limit
                    )

                # Deduplicate results
                for result in query_results:
                    content = result.get("content", "")
                    if content and content not in seen_content:
                        seen_content.add(content)
                        result["source_query"] = search_query
                        all_results.append(result)

            except Exception as e:
                logger.error(f"Search failed for query '{search_query}': {e}")

        # Step 3: Limit total results
        all_results = all_results[:search_limit]

        # Step 4: RAG processing for synthesis
        if all_results:
            try:
                rag_agent = get_rag_agent()

                # Convert results to RAG-compatible format
                documents = []
                for result in all_results:
                    documents.append({
                        "content": result.get("content", ""),
                        "metadata": {
                            "filename": result.get("metadata", {}).get("title", "Unknown"),
                            "source": result.get("metadata", {}).get("source", "knowledge_base"),
                            "category": result.get("metadata", {}).get("category", "general"),
                            "score": result.get("score", 0.0),
                            "source_query": result.get("source_query", original_query)
                        }
                    })

                # Process with RAG agent
                rag_result = await rag_agent.process_document_query(
                    query=original_query,
                    documents=documents,
                    context={"reformulated_queries": reformulated_queries}
                )

                return {
                    "status": "success",
                    "synthesized_response": rag_result.get("synthesized_response", ""),
                    "confidence_score": rag_result.get("confidence_score", 0.0),
                    "document_analysis": rag_result.get("document_analysis", {}),
                    "sources_used": rag_result.get("sources_used", []),
                    "results": all_results,
                    "total_results": len(all_results),
                    "original_query": original_query,
                    "reformulated_queries": reformulated_queries[1:] if len(reformulated_queries) > 1 else [],
                    "kb_implementation": kb_to_use.__class__.__name__,
                    "agent_metadata": rag_result.get("metadata", {}),
                    "rag_enhanced": True
                }

            except Exception as e:
                logger.error(f"RAG processing failed: {e}")
                # Return search results without synthesis
                return {
                    "status": "partial_success",
                    "synthesized_response": f"Found {len(all_results)} relevant documents but synthesis failed: {str(e)}",
                    "results": all_results,
                    "total_results": len(all_results),
                    "original_query": original_query,
                    "reformulated_queries": reformulated_queries[1:] if len(reformulated_queries) > 1 else [],
                    "error": str(e),
                    "rag_enhanced": False
                }
        else:
            return {
                "status": "success",
                "synthesized_response": f"No relevant documents found for query: '{original_query}'",
                "results": [],
                "total_results": 0,
                "original_query": original_query,
                "reformulated_queries": reformulated_queries[1:] if len(reformulated_queries) > 1 else [],
                "rag_enhanced": True
            }

    except Exception as e:
        logger.error(f"Error in RAG-enhanced search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"RAG search failed: {str(e)}")


@router.post("/similarity_search")
async def similarity_search(request: dict, req: Request):
    """Perform similarity search with optional RAG enhancement - FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "results": [],
                "total_results": 0,
                "message": "Knowledge base not initialized - please check logs for errors"
            }

        query = request.get("query", "")
        top_k = request.get("top_k", 10)
        threshold = request.get("threshold", 0.7)
        use_rag = request.get("use_rag", False)

        logger.info(f"Similarity search request: '{query}' (top_k={top_k}, threshold={threshold}, use_rag={use_rag})")

        # FIXED: Check which knowledge base implementation we're using and call with correct parameters
        kb_class_name = kb_to_use.__class__.__name__

        if kb_class_name == "KnowledgeBaseV2":
            # KnowledgeBaseV2 uses 'top_k' parameter
            results = await kb_to_use.search(
                query=query,
                top_k=top_k
            )
        else:
            # Original KnowledgeBase uses 'similarity_top_k' parameter
            results = await kb_to_use.search(
                query=query,
                similarity_top_k=top_k
            )

        # Filter by threshold if specified
        if threshold > 0:
            filtered_results = []
            for result in results:
                if result.get("score", 0) >= threshold:
                    filtered_results.append(result)
            results = filtered_results

        # Enhanced search with RAG if requested and available
        if use_rag and RAG_AVAILABLE and results:
            try:
                rag_enhancement = await _enhance_search_with_rag(query, results)
                return {
                    "results": results,
                    "total_results": len(results),
                    "query": query,
                    "threshold": threshold,
                    "kb_implementation": kb_class_name,
                    "rag_enhanced": True,
                    "rag_analysis": rag_enhancement
                }
            except Exception as e:
                logger.error(f"RAG enhancement failed: {e}")
                # Continue with regular results if RAG fails

        return {
            "results": results,
            "total_results": len(results),
            "query": query,
            "threshold": threshold,
            "kb_implementation": kb_class_name,
            "rag_enhanced": False
        }

    except Exception as e:
        logger.error(f"Error in similarity search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Similarity search failed: {str(e)}")


@router.get("/health")
async def get_knowledge_health(req: Request):
    """Get knowledge base health status with RAG capability status - FIXED to use proper instance"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "unhealthy",
                "initialized": False,
                "redis_connected": False,
                "vector_store_available": False,
                "rag_available": RAG_AVAILABLE,
                "rag_status": "disabled" if not RAG_AVAILABLE else "unknown",
                "message": "Knowledge base not initialized"
            }

        # Try to get stats to verify health
        stats = await kb_to_use.get_stats()

        # Check RAG Agent health if available
        rag_status = "disabled"
        if RAG_AVAILABLE:
            try:
                rag_agent = get_rag_agent()
                # Simple test to verify RAG agent works
                rag_status = "healthy"
            except Exception as e:
                rag_status = f"error: {str(e)}"

        return {
            "status": "healthy",
            "initialized": stats.get("initialized", False),
            "redis_connected": True,
            "vector_store_available": stats.get("index_available", False),
            "total_facts": stats.get("total_facts", 0),
            "db_size": stats.get("db_size", 0),
            "kb_implementation": kb_to_use.__class__.__name__,
            "rag_available": RAG_AVAILABLE,
            "rag_status": rag_status
        }

    except Exception as e:
        logger.error(f"Error checking knowledge health: {str(e)}")
        return {
            "status": "unhealthy",
            "initialized": False,
            "redis_connected": False,
            "vector_store_available": False,
            "rag_available": RAG_AVAILABLE,
            "rag_status": "disabled" if not RAG_AVAILABLE else f"error: {str(e)}",
            "error": str(e)
        }


# === NEW REPOPULATE ENDPOINTS ===

@router.post("/populate_system_commands")
async def populate_system_commands(request: dict, req: Request):
    """Populate knowledge base with common system commands and usage examples"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors",
                "items_added": 0
            }

        logger.info("Starting system commands population...")

        # Define common system commands with descriptions and examples
        system_commands = [
            {
                "command": "curl",
                "description": "Command line tool for transferring data with URLs",
                "usage": "curl [options] <url>",
                "examples": [
                    "curl https://api.example.com/data",
                    "curl -X POST -d 'data' https://api.example.com",
                    "curl -H 'Authorization: Bearer token' https://api.example.com",
                    "curl -o output.html https://example.com"
                ],
                "options": [
                    "-X: HTTP method (GET, POST, PUT, DELETE)",
                    "-H: Add header",
                    "-d: Data to send",
                    "-o: Output to file",
                    "-v: Verbose output",
                    "--json: Send JSON data"
                ]
            },
            {
                "command": "grep",
                "description": "Search text patterns in files",
                "usage": "grep [options] pattern [file...]",
                "examples": [
                    "grep 'error' /var/log/syslog",
                    "grep -r 'function' /path/to/code/",
                    "grep -i 'warning' *.log",
                    "ps aux | grep python"
                ],
                "options": [
                    "-r: Recursive search",
                    "-i: Case insensitive",
                    "-n: Line numbers",
                    "-v: Invert match",
                    "-l: Files with matches only"
                ]
            },
            {
                "command": "ssh",
                "description": "Secure Shell for remote login and command execution",
                "usage": "ssh [options] [user@]hostname [command]",
                "examples": [
                    "ssh user@remote-server",
                    "ssh -i ~/.ssh/key user@server",
                    "ssh -p 2222 user@server",
                    "ssh user@server 'ls -la'"
                ],
                "options": [
                    "-i: Identity file (private key)",
                    "-p: Port number",
                    "-v: Verbose output",
                    "-X: Enable X11 forwarding",
                    "-L: Local port forwarding"
                ]
            },
            {
                "command": "docker",
                "description": "Container platform for building, running and managing applications",
                "usage": "docker [options] COMMAND",
                "examples": [
                    "docker run -it ubuntu bash",
                    "docker build -t myapp .",
                    "docker ps -a",
                    "docker exec -it container_name bash"
                ],
                "options": [
                    "run: Create and run container",
                    "build: Build image from Dockerfile",
                    "ps: List containers",
                    "exec: Execute command in container",
                    "logs: View container logs"
                ]
            },
            {
                "command": "git",
                "description": "Distributed version control system",
                "usage": "git [options] COMMAND [args]",
                "examples": [
                    "git clone https://github.com/user/repo.git",
                    "git add .",
                    "git commit -m 'message'",
                    "git push origin main"
                ],
                "options": [
                    "clone: Clone repository",
                    "add: Stage changes",
                    "commit: Create commit",
                    "push: Upload changes",
                    "pull: Download changes"
                ]
            },
            {
                "command": "find",
                "description": "Search for files and directories",
                "usage": "find [path] [expression]",
                "examples": [
                    "find /path -name '*.py'",
                    "find . -type f -mtime -7",
                    "find /var -size +100M",
                    "find . -perm 755"
                ],
                "options": [
                    "-name: File name pattern",
                    "-type: File type (f=file, d=directory)",
                    "-size: File size",
                    "-mtime: Modification time",
                    "-exec: Execute command on results"
                ]
            },
            {
                "command": "tar",
                "description": "Archive files and directories",
                "usage": "tar [options] archive-file files...",
                "examples": [
                    "tar -czf archive.tar.gz folder/",
                    "tar -xzf archive.tar.gz",
                    "tar -tzf archive.tar.gz",
                    "tar -xzf archive.tar.gz -C /destination/"
                ],
                "options": [
                    "-c: Create archive",
                    "-x: Extract archive",
                    "-z: Gzip compression",
                    "-f: Archive filename",
                    "-t: List contents"
                ]
            },
            {
                "command": "systemctl",
                "description": "Control systemd services",
                "usage": "systemctl [options] COMMAND [service]",
                "examples": [
                    "systemctl status nginx",
                    "systemctl start redis-server",
                    "systemctl enable docker",
                    "systemctl restart apache2"
                ],
                "options": [
                    "start: Start service",
                    "stop: Stop service",
                    "restart: Restart service",
                    "status: Check status",
                    "enable: Auto-start on boot"
                ]
            },
            {
                "command": "ps",
                "description": "Display running processes",
                "usage": "ps [options]",
                "examples": [
                    "ps aux",
                    "ps -ef",
                    "ps aux | grep python",
                    "ps -u username"
                ],
                "options": [
                    "aux: All processes with details",
                    "-ef: Full format listing",
                    "-u: Processes by user",
                    "-C: Processes by command"
                ]
            },
            {
                "command": "chmod",
                "description": "Change file permissions",
                "usage": "chmod [options] mode file...",
                "examples": [
                    "chmod 755 script.sh",
                    "chmod +x program",
                    "chmod -R 644 /path/to/files/",
                    "chmod u+w,g-w file.txt"
                ],
                "options": [
                    "755: rwxr-xr-x (executable)",
                    "644: rw-r--r-- (readable)",
                    "+x: Add execute permission",
                    "-R: Recursive",
                    "u/g/o: user/group/others"
                ]
            }
        ]

        items_added = 0

        # Process commands in batches to avoid timeouts
        batch_size = 5
        for i in range(0, len(system_commands), batch_size):
            batch = system_commands[i:i+batch_size]

            for cmd_info in batch:
                try:
                    # Create comprehensive content for each command
                    content = f"""Command: {cmd_info['command']}

Description: {cmd_info['description']}

Usage: {cmd_info['usage']}

Examples:
{chr(10).join(f"  {example}" for example in cmd_info['examples'])}

Common Options:
{chr(10).join(f"  {option}" for option in cmd_info['options'])}

Category: System Command
Type: Command Reference
"""

                    # Store in knowledge base
                    if hasattr(kb_to_use, 'store_fact'):
                        result = await kb_to_use.store_fact(
                            content=content,
                            metadata={
                                "title": f"{cmd_info['command']} command",
                                "source": "system_commands_population",
                                "category": "commands",
                                "command": cmd_info['command'],
                                "type": "system_command"
                            }
                        )
                    else:
                        result = await kb_to_use.store_fact(
                            text=content,
                            metadata={
                                "title": f"{cmd_info['command']} command",
                                "source": "system_commands_population",
                                "category": "commands",
                                "command": cmd_info['command'],
                                "type": "system_command"
                            }
                        )

                    if result and result.get("fact_id"):
                        items_added += 1
                        logger.info(f"Added command: {cmd_info['command']}")
                    else:
                        logger.warning(f"Failed to add command: {cmd_info['command']}")

                except Exception as e:
                    logger.error(f"Error adding command {cmd_info['command']}: {e}")

            # Small delay between batches to prevent overload
            await asyncio.sleep(0.1)

        logger.info(f"System commands population completed. Added {items_added} commands.")

        return {
            "status": "success",
            "message": f"Successfully populated {items_added} system commands",
            "items_added": items_added,
            "total_commands": len(system_commands)
        }

    except Exception as e:
        logger.error(f"Error populating system commands: {str(e)}")
        raise HTTPException(status_code=500, detail=f"System commands population failed: {str(e)}")


async def _populate_man_pages_background(kb_to_use):
    """Background task to populate man pages"""
    try:
        logger.info("Starting manual pages population in background...")

        # Common commands to get man pages for
        common_commands = [
            'ls', 'cd', 'cp', 'mv', 'rm', 'mkdir', 'rmdir', 'chmod', 'chown', 'find',
            'grep', 'sed', 'awk', 'sort', 'uniq', 'head', 'tail', 'cat', 'less', 'more',
            'ps', 'top', 'kill', 'jobs', 'nohup', 'crontab', 'systemctl', 'service',
            'curl', 'wget', 'ssh', 'scp', 'rsync', 'tar', 'zip', 'unzip', 'gzip', 'gunzip',
            'git', 'docker', 'npm', 'pip', 'python', 'node', 'java', 'gcc', 'make'
        ]

        items_added = 0

        # Process man pages in batches
        batch_size = 5
        for i in range(0, len(common_commands), batch_size):
            batch = common_commands[i:i+batch_size]

            for command in batch:
                try:
                    # Try to get the man page with reduced timeout
                    result = subprocess.run(
                        ['man', command],
                        capture_output=True,
                        text=True,
                        timeout=3  # Reduced from 10 to 3 seconds
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        # Clean up the man page output
                        man_content = result.stdout.strip()

                        # Remove ANSI escape sequences if present
                        import re
                        man_content = re.sub(r'\x1b\[[0-9;]*m', '', man_content)

                        # Create structured content
                        content = f"""Manual Page: {command}

{man_content}

Source: System Manual Pages
Category: Manual Page
Command: {command}
"""

                        # Store in knowledge base
                        if hasattr(kb_to_use, 'store_fact'):
                            store_result = await kb_to_use.store_fact(
                                content=content,
                                metadata={
                                    "title": f"man {command}",
                                    "source": "manual_pages_population",
                                    "category": "manpages",
                                    "command": command,
                                    "type": "manual_page"
                                }
                            )
                        else:
                            store_result = await kb_to_use.store_fact(
                                text=content,
                                metadata={
                                    "title": f"man {command}",
                                    "source": "manual_pages_population",
                                    "category": "manpages",
                                    "command": command,
                                    "type": "manual_page"
                                }
                            )

                        if store_result and store_result.get("fact_id"):
                            items_added += 1
                            logger.info(f"Added man page: {command}")
                        else:
                            logger.warning(f"Failed to store man page: {command}")

                    else:
                        logger.warning(f"No man page found for command: {command}")

                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout getting man page for: {command}")
                except Exception as e:
                    logger.error(f"Error processing man page for {command}: {e}")

            # Small delay between batches (reduced for faster completion)
            await asyncio.sleep(0.1)

        logger.info(f"Manual pages population completed. Added {items_added} man pages.")
        return items_added

    except Exception as e:
        logger.error(f"Error populating manual pages in background: {str(e)}")
        return 0


@router.post("/populate_man_pages")
async def populate_man_pages(request: dict, req: Request, background_tasks: BackgroundTasks):
    """Populate knowledge base with common manual pages (runs in background)"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors",
                "items_added": 0
            }

        # Start background task
        background_tasks.add_task(_populate_man_pages_background, kb_to_use)

        return {
            "status": "success",
            "message": "Man pages population started in background",
            "items_added": 0,  # Will be updated as background task runs
            "background": True
        }

    except Exception as e:
        logger.error(f"Error starting man pages population: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start man pages population: {str(e)}")


@router.post("/refresh_system_knowledge")
async def refresh_system_knowledge(request: dict, req: Request):
    """
    Refresh ALL system knowledge (man pages + AutoBot docs)
    Use this after system updates, package installations, or documentation changes
    """
    try:
        logger.info("Starting comprehensive system knowledge refresh...")

        # Run the comprehensive indexing script
        result = subprocess.run(
            [sys.executable, 'scripts/utilities/index_all_man_pages.py'],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for comprehensive indexing
        )

        if result.returncode == 0:
            # Parse output for statistics
            output_lines = result.stdout.split('\n')
            indexed_count = 0
            total_facts = 0

            for line in output_lines:
                if 'Successfully indexed:' in line:
                    indexed_count = int(line.split(':')[1].strip())
                elif 'Total facts in KB:' in line:
                    total_facts = int(line.split(':')[1].strip())

            logger.info(f"System knowledge refresh complete: {indexed_count} commands indexed")

            return {
                "status": "success",
                "message": f"System knowledge refreshed successfully",
                "commands_indexed": indexed_count,
                "total_facts": total_facts
            }
        else:
            logger.error(f"System knowledge refresh failed: {result.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"Knowledge refresh failed: {result.stderr[:500]}"
            )

    except subprocess.TimeoutExpired:
        logger.error("System knowledge refresh timed out")
        raise HTTPException(
            status_code=504,
            detail="Knowledge refresh timed out (>10 minutes)"
        )
    except Exception as e:
        logger.error(f"Error refreshing system knowledge: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Knowledge refresh failed: {str(e)}"
        )


@router.post("/populate_autobot_docs")
async def populate_autobot_docs(request: dict, req: Request):
    """Populate knowledge base with AutoBot-specific documentation"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors",
                "items_added": 0
            }

        logger.info("Starting AutoBot documentation population...")

        # Define AutoBot documentation files to process
        autobot_base_path = Path("/home/kali/Desktop/AutoBot")

        doc_files = [
            "CLAUDE.md",
            "README.md",
            "setup.sh",
            "run_autobot.sh",
            "docs/system-state.md",
            "docs/api/COMPREHENSIVE_API_DOCUMENTATION.md",
            "docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md",
            "docs/developer/PHASE_5_DEVELOPER_SETUP.md",
            "docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md",
            "config/config.yaml",
            ".env.example",
            "compose.yml"
        ]

        items_added = 0

        for doc_file in doc_files:
            try:
                file_path = autobot_base_path / doc_file

                if file_path.exists() and file_path.is_file():
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    if content.strip():
                        # Create structured content
                        structured_content = f"""AutoBot Documentation: {doc_file}

File Path: {file_path}

Content:
{content}

Source: AutoBot Documentation
Category: AutoBot
Type: Documentation
"""

                        # Store in knowledge base
                        if hasattr(kb_to_use, 'store_fact'):
                            result = await kb_to_use.store_fact(
                                content=structured_content,
                                metadata={
                                    "title": f"AutoBot: {doc_file}",
                                    "source": "autobot_docs_population",
                                    "category": "autobot",
                                    "filename": doc_file,
                                    "type": "autobot_documentation",
                                    "file_path": str(file_path)
                                }
                            )
                        else:
                            result = await kb_to_use.store_fact(
                                text=structured_content,
                                metadata={
                                    "title": f"AutoBot: {doc_file}",
                                    "source": "autobot_docs_population",
                                    "category": "autobot",
                                    "filename": doc_file,
                                    "type": "autobot_documentation",
                                    "file_path": str(file_path)
                                }
                            )

                        if result and result.get("fact_id"):
                            items_added += 1
                            logger.info(f"Added AutoBot doc: {doc_file}")
                        else:
                            logger.warning(f"Failed to store AutoBot doc: {doc_file}")
                    else:
                        logger.warning(f"Empty file: {doc_file}")
                else:
                    logger.warning(f"File not found: {doc_file}")

            except Exception as e:
                logger.error(f"Error processing AutoBot doc {doc_file}: {e}")

            # Small delay between files
            await asyncio.sleep(0.1)

        # Add AutoBot configuration information
        try:
            config_info = """AutoBot System Configuration

Network Layout:
- Main Machine (WSL): 172.16.168.20 - Backend API (port 8001) + Desktop/Terminal VNC (port 6080)
- VM1 Frontend: 172.16.168.21:5173 - Web interface (SINGLE FRONTEND SERVER)
- VM2 NPU Worker: 172.16.168.22:8081 - Hardware AI acceleration
- VM3 Redis: 172.16.168.23:6379 - Data layer
- VM4 AI Stack: 172.16.168.24:8080 - AI processing
- VM5 Browser: 172.16.168.25:3000 - Web automation (Playwright)

Key Commands:
- Setup: bash setup.sh [--full|--minimal|--distributed]
- Run: bash run_autobot.sh [--dev|--prod] [--build|--no-build] [--desktop|--no-desktop]

Critical Rules:
- NEVER edit code directly on remote VMs (172.16.168.21-25)
- ALL code edits MUST be made locally in /home/kali/Desktop/AutoBot/
- Use ./sync-frontend.sh or sync scripts to deploy changes
- Frontend ONLY runs on VM1 (172.16.168.21:5173)
- NO temporary fixes or workarounds allowed

Source: AutoBot System Configuration
Category: AutoBot
Type: System Configuration
"""

            if hasattr(kb_to_use, 'store_fact'):
                result = await kb_to_use.store_fact(
                    content=config_info,
                    metadata={
                        "title": "AutoBot System Configuration",
                        "source": "autobot_docs_population",
                        "category": "autobot",
                        "type": "system_configuration"
                    }
                )
            else:
                result = await kb_to_use.store_fact(
                    text=config_info,
                    metadata={
                        "title": "AutoBot System Configuration",
                        "source": "autobot_docs_population",
                        "category": "autobot",
                        "type": "system_configuration"
                    }
                )

            if result and result.get("fact_id"):
                items_added += 1
                logger.info("Added AutoBot system configuration")

        except Exception as e:
            logger.error(f"Error adding AutoBot configuration: {e}")

        logger.info(f"AutoBot documentation population completed. Added {items_added} documents.")

        return {
            "status": "success",
            "message": f"Successfully populated {items_added} AutoBot documents",
            "items_added": items_added,
            "total_files": len(doc_files) + 1  # +1 for config info
        }

    except Exception as e:
        logger.error(f"Error populating AutoBot docs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AutoBot docs population failed: {str(e)}")


@router.post("/clear_all")
async def clear_all_knowledge(request: dict, req: Request):
    """Clear all entries from the knowledge base - DESTRUCTIVE OPERATION"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors",
                "items_removed": 0
            }

        logger.warning("Starting DESTRUCTIVE operation: clearing all knowledge base entries")

        # Get current stats before clearing
        try:
            stats_before = await kb_to_use.get_stats()
            items_before = stats_before.get("total_facts", 0)
        except Exception:
            items_before = 0

        # Clear the knowledge base
        if hasattr(kb_to_use, 'clear_all'):
            # Use specific clear_all method if available
            result = await kb_to_use.clear_all()
            items_removed = result.get("items_removed", items_before)
        else:
            # Fallback: try to clear via Redis if that's the implementation
            try:
                if hasattr(kb_to_use, 'redis') and kb_to_use.redis:
                    # For Redis-based implementations
                    keys = await kb_to_use.redis.keys("fact:*")
                    if keys:
                        await kb_to_use.redis.delete(*keys)

                    # Clear any indexes
                    index_keys = await kb_to_use.redis.keys("index:*")
                    if index_keys:
                        await kb_to_use.redis.delete(*index_keys)

                    items_removed = len(keys)
                else:
                    logger.error("No clear method available for knowledge base implementation")
                    raise HTTPException(status_code=500, detail="Knowledge base clearing not supported")

            except Exception as e:
                logger.error(f"Error during knowledge base clearing: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to clear knowledge base: {str(e)}")

        logger.warning(f"Knowledge base cleared. Removed {items_removed} entries.")

        return {
            "status": "success",
            "message": f"Successfully cleared knowledge base. Removed {items_removed} entries.",
            "items_removed": items_removed,
            "items_before": items_before
        }

    except Exception as e:
        logger.error(f"Error clearing knowledge base: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Knowledge base clearing failed: {str(e)}")


# Legacy endpoints for backward compatibility
@router.post("/add_document")
async def add_document_to_knowledge(request: dict, req: Request):
    """Legacy endpoint - redirects to add_text"""
    return await add_text_to_knowledge(request, req)


@router.post("/query")
async def query_knowledge(request: dict, req: Request):
    """Legacy endpoint - redirects to search"""
    return await search_knowledge(request, req)


# Helper function for RAG enhancement
async def _enhance_search_with_rag(query: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Enhance search results with RAG analysis"""
    try:
        rag_agent = get_rag_agent()

        # Convert results to documents for RAG processing
        documents = []
        for result in results:
            documents.append({
                "content": result.get("content", ""),
                "metadata": {
                    "filename": result.get("metadata", {}).get("title", "Unknown"),
                    "source": result.get("metadata", {}).get("source", "knowledge_base"),
                    "score": result.get("score", 0.0)
                }
            })

        # Analyze document relevance
        document_analysis = rag_agent._analyze_document_relevance(query, documents)

        # Rank documents
        ranked_documents = await rag_agent.rank_documents(query, documents)

        return {
            "document_analysis": document_analysis,
            "ranked_documents": ranked_documents[:5],  # Top 5 ranked documents
            "analysis_summary": {
                "total_analyzed": len(documents),
                "high_relevance_count": document_analysis.get("high_relevance", 0),
                "medium_relevance_count": document_analysis.get("medium_relevance", 0),
                "low_relevance_count": document_analysis.get("low_relevance", 0)
            }
        }

    except Exception as e:
        logger.error(f"RAG enhancement error: {e}")
        return {
            "error": str(e),
            "analysis_summary": {"total_analyzed": len(results), "error": "RAG analysis failed"}
        }