import asyncio
import glob
import logging
import os
import shutil
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agents import get_kb_librarian
from src.agents.librarian_assistant_agent import LibrarianAssistantAgent
from src.agents.llm_failsafe_agent import get_robust_llm_response
from src.conversation import conversation_manager
from src.error_handler import log_error, safe_api_error
from src.exceptions import (
    AutoBotError,
    InternalError,
    ResourceNotFoundError,
    ValidationError,
    get_error_code,
)
from src.source_attribution import (
    SourceReliability,
    SourceType,
    clear_sources,
    source_manager,
    track_source,
)

# Import workflow automation for terminal integration
try:
    from backend.api.workflow_automation import workflow_manager

    WORKFLOW_AUTOMATION_AVAILABLE = True
except ImportError:
    workflow_manager = None
    WORKFLOW_AUTOMATION_AVAILABLE = False

router = APIRouter()


@router.get("/chat/llm-status")
async def get_llm_status():
    """Get the current status of all LLM tiers"""
    try:
        # PERFORMANCE FIX: Use lightweight status check to avoid blocking
        # Get basic config-based status without expensive health checks
        from src.config import config as global_config_manager

        llm_config = global_config_manager.get_llm_config()
        provider_type = llm_config.get("provider_type", "local")

        # Create lightweight status based on configuration
        lightweight_status = {
            "tier_health": {
                "primary": True,  # Assume healthy if configured
                "secondary": True,
                "fallback": True,
            },
            "tier_statistics": {
                "primary": {
                    "requests": 0,
                    "failures": 0,
                    "failure_rate": 0.0,
                    "avg_response_time": 0.0,
                },
                "secondary": {
                    "requests": 0,
                    "failures": 0,
                    "failure_rate": 0.0,
                    "avg_response_time": 0.0,
                },
                "fallback": {
                    "requests": 0,
                    "failures": 0,
                    "failure_rate": 0.0,
                    "avg_response_time": 0.0,
                },
            },
            "overall_stats": {
                "total_requests": 0,
                "total_failures": 0,
                "overall_success_rate": 1.0,
                "active_tier": "primary",
            },
            "provider_info": {
                "provider_type": provider_type,
                "local_provider": llm_config.get("local", {}).get("provider", "ollama"),
                "cloud_provider": llm_config.get("cloud", {}).get("provider", "openai"),
                "status_method": "lightweight_config_based",
            },
        }

        return JSONResponse(status_code=200, content=lightweight_status)
    except Exception as e:
        logger.error(f"Failed to get LLM status: {e}")
        # Fallback to basic status
        return JSONResponse(
            status_code=200,
            content={
                "tier_health": {
                    "primary": False,
                    "secondary": False,
                    "fallback": False,
                },
                "overall_stats": {"active_tier": "none", "overall_success_rate": 0.0},
                "error": f"Status check failed: {str(e)}",
            },
        )


logger = logging.getLogger(__name__)


def generate_request_id() -> str:
    """Generate a unique request ID for tracking."""
    return str(uuid.uuid4())


def _should_research_web(message: str) -> bool:
    """Determine if a message should trigger web research."""
    # Research keywords that suggest current/recent information is needed
    research_keywords = [
        "latest",
        "recent",
        "current",
        "new",
        "update",
        "2024",
        "2025",
        "today",
        "now",
        "this year",
        "this month",
        "breaking",
        "news",
        "announcement",
        "release",
        "launch",
        "trending",
    ]

    # Avoid research for certain topics
    avoid_keywords = [
        "how to",
        "tutorial",
        "guide",
        "definition",
        "what is",
        "explain",
        "example",
        "calculate",
        "formula",
        "code",
    ]

    message_lower = message.lower()

    # Don't research if it looks like a how-to or basic definition request
    if any(avoid in message_lower for avoid in avoid_keywords):
        return False

    # Research if it contains current/recent information keywords
    if any(keyword in message_lower for keyword in research_keywords):
        return True

    # Research for factual questions about specific topics, companies, products
    factual_patterns = [
        r"\b(who is|what happened to|where is|when did|why did)\b",
        r"\b(price of|cost of|value of)\b",
        r"\b(stock|market|cryptocurrency|crypto)\b",
        r"\b(company|startup|business|corporation)\b",
    ]

    import re

    if any(re.search(pattern, message_lower) for pattern in factual_patterns):
        return True

    return False


async def _send_typed_message(
    existing_history: List[Dict],
    message_type: str,
    content: str,
    chat_history_manager,
    chat_id: str,
):
    """Send a typed message as a separate chat message."""
    typed_message = {
        "sender": "bot",
        "text": content,
        "messageType": message_type,
        "rawData": None,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    existing_history.append(typed_message)
    # Save immediately to ensure message appears
    # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
    await asyncio.to_thread(
        chat_history_manager.save_session, chat_id, messages=existing_history
    )


async def _enhanced_knowledge_search(
    query: str,
    knowledge_base,
    chat_history_manager,
    chat_id: str,
    existing_history: List[Dict],
) -> Dict[str, Any]:
    """Enhanced knowledge search: KB first, then web research with user approval."""

    # Step 1: Search knowledge base first
    logger.info(f"Searching knowledge base for: {query}")
    kb_results = await knowledge_base.search(query, n_results=3)

    if kb_results and len(kb_results) > 0:
        # Found in knowledge base
        logger.info(f"Found {len(kb_results)} results in knowledge base")
        return {
            "source": "knowledge_base",
            "results": kb_results,
            "needs_approval": False,
        }

    # Step 2: Not found in KB, search web
    logger.info("No results in knowledge base, initiating web research")
    await _send_typed_message(
        existing_history,
        "info",
        "🔍 Information not found in knowledge base. Searching the web for latest information...",
        chat_history_manager,
        chat_id,
    )

    try:
        # Initialize librarian assistant
        librarian = LibrarianAssistantAgent()

        # Search web but don't auto-store yet
        research_results = await librarian.research_query(
            query, store_quality_content=False
        )

        if not research_results.get("search_results"):
            await _send_typed_message(
                existing_history,
                "warning",
                "❌ No web results found for your query.",
                chat_history_manager,
                chat_id,
            )
            return {"source": "none", "results": [], "needs_approval": False}

        # Extract quality sources for user approval
        quality_sources = []
        for result in research_results.get("content_extracted", []):
            if result.get("quality_score", 0) >= 0.6:  # Quality threshold
                source_info = {
                    "title": result.get("title", "Unknown Title"),
                    "url": result.get("url", ""),
                    "content_preview": result.get("content", "")[:200] + "...",
                    "quality_score": result.get("quality_score", 0),
                    "full_content": result.get("content", ""),
                }
                quality_sources.append(source_info)

        if quality_sources:
            # Present sources to user for approval
            sources_text = "📚 **Found information from these sources:**\n\n"
            for i, source in enumerate(quality_sources, 1):
                sources_text += f"**{i}. {source['title']}** (Quality: {source['quality_score']:.1f}/1.0)\n"
                sources_text += f"   🔗 {source['url']}\n"
                sources_text += f"   📄 {source['content_preview']}\n\n"

            sources_text += "**Would you like me to add this information to the knowledge base for future reference?**\n"
            sources_text += (
                "Reply with 'yes' to approve these sources, or 'no' to decline."
            )

            await _send_typed_message(
                existing_history,
                "source_approval",
                sources_text,
                chat_history_manager,
                chat_id,
            )

            return {
                "source": "web_research",
                "results": research_results,
                "quality_sources": quality_sources,
                "needs_approval": True,
                "librarian": librarian,
            }
        else:
            await _send_typed_message(
                existing_history,
                "warning",
                "⚠️ Found web results but they don't meet quality standards for knowledge base storage.",
                chat_history_manager,
                chat_id,
            )
            return {
                "source": "web_research",
                "results": research_results,
                "needs_approval": False,
            }

    except Exception as e:
        logger.error(f"Web research failed: {e}")
        await _send_typed_message(
            existing_history,
            "error",
            f"❌ Web research failed: {str(e)}",
            chat_history_manager,
            chat_id,
        )
        return {"source": "error", "results": [], "needs_approval": False}


async def _handle_source_approval(
    user_response: str,
    quality_sources: List[Dict],
    librarian: LibrarianAssistantAgent,
    knowledge_base,
    chat_history_manager,
    chat_id: str,
    existing_history: List[Dict],
) -> bool:
    """Handle user approval for storing web research sources in knowledge base."""

    user_response_lower = user_response.lower().strip()

    if user_response_lower in ["yes", "y", "approve", "add", "store"]:
        try:
            stored_count = 0
            for source in quality_sources:
                # Store each approved source
                success = await librarian.store_in_knowledge_base(
                    content=source["full_content"],
                    metadata={
                        "title": source["title"],
                        "url": source["url"],
                        "quality_score": source["quality_score"],
                        "stored_by": "enhanced_chat_workflow",
                        "user_approved": True,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
                if success:
                    stored_count += 1

            await _send_typed_message(
                existing_history,
                "success",
                f"✅ Successfully added {stored_count} sources to the knowledge base. This information will be available for future queries!",
                chat_history_manager,
                chat_id,
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store approved sources: {e}")
            await _send_typed_message(
                existing_history,
                "error",
                f"❌ Failed to store sources in knowledge base: {str(e)}",
                chat_history_manager,
                chat_id,
            )
            return False

    elif user_response_lower in ["no", "n", "decline", "reject", "skip"]:
        await _send_typed_message(
            existing_history,
            "info",
            "📝 Sources not added to knowledge base as requested. The information is still available in this conversation.",
            chat_history_manager,
            chat_id,
        )
        return True

    else:
        # Invalid response, ask again
        await _send_typed_message(
            existing_history,
            "clarification",
            "Please respond with 'yes' to add the sources to knowledge base, or 'no' to decline.",
            chat_history_manager,
            chat_id,
        )
        return False


async def _check_if_command_needed(message: str, llm_interface) -> dict:
    """
    SECURITY FIX: Check if a user message requires executing a system command.

    This function has been secured to prevent prompt injection attacks by:
    1. Removing LLM-based command extraction
    2. Using a predefined safelist of allowed commands
    3. Blocking dangerous command patterns
    """
    try:
        # Import the secure command validator
        from src.security.command_validator import get_command_validator

        validator = get_command_validator()

        # Use the secure validator instead of LLM extraction
        command_info = validator.validate_command_request(message)

        if command_info:
            if command_info.get("type") == "blocked":
                # Log security event for blocked commands
                logger.warning(
                    f"SECURITY: Blocked command request from message: {message}"
                )
                return None

            # Return the validated command info
            return {
                "type": command_info["type"],
                "command": command_info["command"],
                "explanation": command_info["description"],
                "purpose": command_info["description"],
                "risk_level": command_info.get("risk_level", "UNKNOWN"),
                "alternatives": command_info.get("alternatives", []),
            }

        return None

    except Exception as e:
        logger.error(f"Secure command validation failed: {e}")
        # Fail securely - return None instead of allowing potentially dangerous commands
        return None


async def _interpret_command_output(command: str, output: str, llm_interface) -> str:
    """Use LLM to interpret command output in user-friendly language."""

    # Clean up escape characters and control sequences
    import re

    cleaned_output = output

    # Remove ANSI escape sequences (colors, cursor control, etc.)
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    cleaned_output = ansi_escape.sub("", cleaned_output)

    # Remove other common escape sequences
    cleaned_output = re.sub(r"\x1b\[[0-9;]*m", "", cleaned_output)  # Color codes
    cleaned_output = re.sub(r"\r\n", "\n", cleaned_output)  # Windows line endings
    cleaned_output = re.sub(r"\r", "\n", cleaned_output)  # Mac line endings
    cleaned_output = re.sub(r"\x00", "", cleaned_output)  # Null bytes
    cleaned_output = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", cleaned_output
    )  # Other control chars

    # Remove excessive whitespace
    cleaned_output = re.sub(r"\n\s*\n", "\n\n", cleaned_output)  # Multiple blank lines
    cleaned_output = cleaned_output.strip()

    try:
        messages = [
            {
                "role": "system",
                "content": "You are a system administrator assistant. Interpret the command output in simple, user-friendly language. Focus on the most important information. Be concise but informative.",
            },
            {
                "role": "user",
                "content": f"Command: {command}\n\nOutput:\n{cleaned_output}\n\nPlease explain what this output means in simple terms:",
            },
        ]

        response = await llm_interface.chat_completion(
            messages, llm_type="task", max_tokens=300, temperature=0.7
        )

        if response and "message" in response:
            return response["message"]["content"]
        else:
            return "Command executed successfully, but interpretation unavailable."

    except Exception as e:
        logger.error(f"Output interpretation failed: {e}")
        return f"Command executed successfully. Raw output: {output[:200]}..."


def _extract_text_from_complex_json(data, max_length=500):
    """
    Extract meaningful text content from complex JSON structures.
    Looks for text fields and concatenates them into a readable response.
    """
    text_parts = []

    def extract_recursive(obj, depth=0):
        if depth > 3:  # Limit recursion depth
            return
        if isinstance(obj, str) and obj.strip() and len(obj) > 10:
            # Only include strings that look like actual text (not short keys/IDs)
            text_parts.append(obj.strip())
        elif isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in [
                    "text",
                    "message",
                    "content",
                    "response",
                    "description",
                ]:
                    if isinstance(value, str) and value.strip():
                        text_parts.append(value.strip())
                    elif isinstance(value, list):
                        for item in value:
                            extract_recursive(item, depth + 1)
                else:
                    extract_recursive(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                extract_recursive(item, depth + 1)

    extract_recursive(data)
    if text_parts:
        # Join the text parts and limit length
        combined_text = " ".join(text_parts)
        if len(combined_text) > max_length:
            combined_text = combined_text[:max_length] + "..."
        return combined_text
    return None


class ChatMessage(BaseModel):
    message: str


class ChatSave(BaseModel):
    messages: list


@router.post("/chats/new")
async def create_new_chat(request: Request):
    """Create a new chat session ID (POST method)."""
    try:
        # Try to get chat_history_manager from app.state
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)

        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(
                status_code=500,
                content={"error": "Chat history manager not initialized"},
            )

        chat_id = str(uuid.uuid4())
        # Create initial message for new chat
        initial_message = {
            "sender": "bot",
            "text": "Hello! How can I assist you today?",
            "messageType": "response",
            "rawData": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        name = f"Chat {chat_id[:8]}"
        # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
        await asyncio.to_thread(
            chat_history_manager.save_session,
            chat_id,
            messages=[initial_message],
            name=name,
        )
        return JSONResponse(
            status_code=200, content={"chatId": chat_id, "status": "success"}
        )
    except Exception as e:
        logging.error(f"Error creating new chat: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500, content={"error": f"Error creating new chat: {str(e)}"}
        )


@router.get("/chats")
async def list_chats(request: Request):
    """List all available chat sessions with improved error handling."""
    request_id = generate_request_id()

    try:
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            raise InternalError(
                "Chat history manager not initialized",
                details={"component": "chat_history_manager"},
            )

        try:
            # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
            sessions = await asyncio.to_thread(chat_history_manager.list_sessions)
            return JSONResponse(status_code=200, content={"chats": sessions})
        except AttributeError as e:
            raise InternalError(
                "Chat history manager is misconfigured",
                details={"missing_method": "list_sessions"},
            ) from e
        except Exception as e:
            logger.critical(
                f"Unexpected error listing chat sessions: {type(e).__name__}",
                exc_info=True,
                extra={"request_id": request_id},
            )
            raise InternalError("Failed to retrieve chat sessions") from e

    except AutoBotError as e:
        log_error(e, context="list_chats", include_traceback=False)
        return JSONResponse(
            status_code=get_error_code(e), content=safe_api_error(e, request_id)
        )
    except Exception as e:
        log_error(e, context="list_chats")
        return JSONResponse(
            status_code=500,
            content=safe_api_error(
                InternalError("An unexpected error occurred"), request_id
            ),
        )


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    """Get a specific chat session with improved error handling."""
    request_id = generate_request_id()

    try:
        # Validate chat_id format
        if not chat_id or len(chat_id) > 100:
            raise ValidationError(
                "Invalid chat ID format",
                field="chat_id",
                value=chat_id[:50] if chat_id else None,  # Truncate for safety
            )

        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            raise InternalError("Chat history manager not initialized")

        try:
            # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
            history = await asyncio.to_thread(
                chat_history_manager.load_session, chat_id
            )

            if history is None:
                raise ResourceNotFoundError(
                    "Chat session not found", resource_type="chat", resource_id=chat_id
                )

            return JSONResponse(
                status_code=200, content={"chat_id": chat_id, "history": history}
            )

        except FileNotFoundError:
            raise ResourceNotFoundError(
                "Chat session file not found", resource_type="chat", resource_id=chat_id
            )
        except PermissionError as e:
            logger.error(f"Permission denied accessing chat {chat_id}: {e}")
            raise InternalError("Unable to access chat session")
        except ValueError as e:
            logger.error(f"Corrupted chat data for {chat_id}: {e}")
            raise InternalError("Chat session data is corrupted")

    except AutoBotError as e:
        log_error(e, context=f"get_chat:{chat_id}", include_traceback=False)
        return JSONResponse(
            status_code=get_error_code(e), content=safe_api_error(e, request_id)
        )
    except Exception as e:
        log_error(e, context=f"get_chat:{chat_id}")
        return JSONResponse(
            status_code=500,
            content=safe_api_error(
                InternalError("An unexpected error occurred"), request_id
            ),
        )


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    """Delete a specific chat session with improved error handling."""
    request_id = generate_request_id()

    try:
        # Validate input
        if not chat_id:
            raise ValidationError("Chat ID is required", field="chat_id")

        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            raise InternalError("Chat history manager not initialized")

        # Attempt deletion with specific error handling
        try:
            # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
            success = await asyncio.to_thread(
                chat_history_manager.delete_session, chat_id
            )

            if not success:
                # Try legacy format matching before giving up
                try:
                    # PERFORMANCE FIX: Convert blocking file I/O to async
                    all_sessions = await asyncio.to_thread(
                        chat_history_manager.list_sessions
                    )
                    matching_session = None

                    for session in all_sessions:
                        session_id = session.get("chatId", session.get("sessionId", ""))
                        if session_id == chat_id or (
                            chat_id in session_id or session_id in chat_id
                        ):
                            matching_session = session_id
                            break

                    if matching_session and await asyncio.to_thread(
                        chat_history_manager.delete_session, matching_session
                    ):
                        success = True
                    else:
                        # Session not found
                        raise ResourceNotFoundError(
                            "Chat session not found",
                            resource_type="chat",
                            resource_id=chat_id,
                        )
                except Exception as lookup_error:
                    logger.warning(
                        f"Error during chat lookup for {chat_id}: {lookup_error}"
                    )
                    raise ResourceNotFoundError(
                        "Chat session not found",
                        resource_type="chat",
                        resource_id=chat_id,
                    )

            return JSONResponse(
                status_code=200,
                content={"success": True, "message": "Chat deleted successfully"},
            )

        except PermissionError:
            logger.error(f"Permission denied deleting chat {chat_id}")
            raise InternalError("Insufficient permissions to delete chat")
        except OSError as e:
            logger.error(f"OS error deleting chat {chat_id}: {e}")
            raise InternalError("System error while deleting chat")

    except AutoBotError as e:
        log_error(e, context=f"delete_chat:{chat_id}", include_traceback=False)
        return JSONResponse(
            status_code=get_error_code(e), content=safe_api_error(e, request_id)
        )
    except Exception as e:
        log_error(e, context=f"delete_chat:{chat_id}")
        return JSONResponse(
            status_code=500,
            content=safe_api_error(
                InternalError("An unexpected error occurred"), request_id
            ),
        )


@router.post("/chats/{chat_id}")
async def save_chat_messages(chat_id: str, messages: list, request: Request):
    """Save messages for a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
        await asyncio.to_thread(
            chat_history_manager.save_session, chat_id, messages=messages
        )
        return JSONResponse(status_code=200, content={"status": "success"})
    except Exception as e:
        logger.error(f"Error saving chat messages for {chat_id}: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error saving chat messages: {str(e)}"}
        )


@router.post("/chats/{chat_id}/save")
async def save_chat(chat_id: str, chat_data: ChatSave, request: Request):
    """Save chat data for a specific session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
        await asyncio.to_thread(
            chat_history_manager.save_session, chat_id, messages=chat_data.messages
        )
        return JSONResponse(status_code=200, content={"status": "success"})
    except Exception as e:
        logger.error(f"Error saving chat data for {chat_id}: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error saving chat: {str(e)}"}
        )


@router.post("/chats/{chat_id}/reset")
async def reset_chat(chat_id: str, request: Request):
    """Reset a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        initial_message = {
            "sender": "bot",
            "text": "Hello! How can I assist you today?",
            "messageType": "response",
            "rawData": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
        await asyncio.to_thread(
            chat_history_manager.save_session, chat_id, messages=[initial_message]
        )
        return JSONResponse(status_code=200, content={"status": "success"})
    except Exception as e:
        logger.error(f"Error resetting chat {chat_id}: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error resetting chat: {str(e)}"}
        )


@router.post("/chat/conversation")
async def conversation_chat_message(chat_message: dict, request: Request):
    """Enhanced chat endpoint using the new Conversation class with KB integration."""
    try:
        logger.info("=== CONVERSATION CHAT ENDPOINT STARTED ===")

        # Extract chat_id and message from the request
        chat_id = chat_message.get("chatId")
        message = chat_message.get("message")

        if not chat_id or not message:
            return JSONResponse(
                status_code=400, content={"error": "chatId and message are required"}
            )

        # Get or create conversation
        conversation = conversation_manager.get_or_create_conversation(chat_id)

        # Process the message through the conversation
        result = await conversation.process_user_message(message)

        # Save to chat history if manager available
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager:
            try:
                # Save user message
                chat_history_manager.add_message_to_session(
                    chat_id,
                    {
                        "role": "user",
                        "content": message,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "messageType": "chat",
                    },
                )

                # Save assistant response
                chat_history_manager.add_message_to_session(
                    chat_id,
                    {
                        "role": "assistant",
                        "content": result["response"],
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "messageType": "response",
                        "rawData": {
                            "sources": result.get("sources", ""),
                            "classification": result.get("classification"),
                            "kb_results_count": result.get("kb_results_count", 0),
                            "processing_time": result.get("processing_time", 0),
                        },
                    },
                )

                # Save sources if available
                if result.get("sources"):
                    chat_history_manager.add_message_to_session(
                        chat_id,
                        {
                            "role": "system",
                            "content": result["sources"],
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "messageType": "source",
                        },
                    )

            except Exception as e:
                logger.error(f"Failed to save to chat history: {e}")

        # Return response in expected format
        response_data = {
            "role": "assistant",
            "content": result["response"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "messageType": "response",
            "rawData": {
                "sources": result.get("sources", ""),
                "classification": result.get("classification"),
                "conversation_id": result.get("conversation_id"),
                "processing_time": result.get("processing_time", 0),
            },
        }

        logger.info(
            f"Conversation response completed in {result.get('processing_time', 0):.2f}s"
        )
        return JSONResponse(status_code=200, content=response_data)

    except Exception as e:
        logger.error(f"Conversation chat error: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")

        return JSONResponse(
            status_code=500,
            content={
                "role": "assistant",
                "content": f"I encountered an error processing your message: {str(e)}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messageType": "error",
                "error": str(e),
            },
        )


@router.post("/chat/direct")
async def send_direct_chat_message(chat_message: dict, request: Request):
    """Direct chat endpoint that bypasses orchestration for simple responses."""
    try:
        logger.info("=== DIRECT CHAT ENDPOINT STARTED ===")
        logger.info(f"Received chat_message: {chat_message}")

        # Extract chat_id and message from the request
        chat_id = chat_message.get("chatId")
        message = chat_message.get("message")

        logger.info(f"Extracted chat_id: {chat_id}, message: {message}")

        if not chat_id:
            logger.info("Missing chatId, returning 400")
            return JSONResponse(
                status_code=400, content={"error": "chatId is required"}
            )
        if not message:
            logger.info("Missing message, returning 400")
            return JSONResponse(
                status_code=400, content={"error": "message is required"}
            )

        logger.error(
            f"DEBUG: Direct chat request - Chat ID: {chat_id}, Message: {message}"
        )

        # Get chat history manager for saving conversation
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)

        # Try to get LLM interface from app state first
        llm_interface = None
        orchestrator = getattr(request.app.state, "orchestrator", None)
        if orchestrator and hasattr(orchestrator, "llm_interface"):
            llm_interface = orchestrator.llm_interface
            logger.info("Using LLM interface from orchestrator")

        # If not available, create a new one
        if llm_interface is None:
            try:
                from src.llm_interface import LLMInterface

                llm_interface = LLMInterface()
                logger.info("Created new LLM interface for direct chat")
            except Exception as llm_init_error:
                logger.error(f"Failed to initialize LLM interface: {llm_init_error}")
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")
                # Fallback to basic response
                response_data = {
                    "role": "assistant",
                    "content": f"I'm having trouble initializing the AI system right now. Your message '{message}' was received but I can't process it.",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "messageType": "response",
                    "rawData": None,
                }
                return JSONResponse(status_code=200, content=response_data)

        # Get knowledge base for enhanced search
        knowledge_base = getattr(request.app.state, "knowledge_base", None)

        # Load existing chat history
        existing_history = []
        if chat_history_manager:
            try:
                # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
                existing_history = (
                    await asyncio.to_thread(chat_history_manager.load_session, chat_id)
                    or []
                )
                logger.error(
                    f"DEBUG: Loaded {len(existing_history)} messages from chat history for {chat_id}"
                )
                if existing_history:
                    logger.error(f"DEBUG: Last message: {existing_history[-1]}")
            except Exception as e:
                logger.warning(f"Could not load chat history for {chat_id}: {e}")
                existing_history = []
        else:
            logger.error(
                "DEBUG: No chat_history_manager available - this is the problem!"
            )

        # Check if user is responding to source approval request
        is_approval_response = False
        if existing_history:
            last_message = existing_history[-1] if existing_history else {}
            if last_message.get("messageType") == "source_approval":
                is_approval_response = True
                # Look for pending approval data (would be stored in a state manager in production)
                # For now, we'll skip the approval handling and proceed with normal flow

        # Check if user is responding to command approval request
        is_command_approval_response = False
        is_command_feedback = False
        if existing_history:
            last_message = existing_history[-1] if existing_history else {}
            logger.error(f"DEBUG: Last message in history: {last_message}")
            logger.error(
                f"DEBUG: Last message type: {last_message.get('messageType', 'None')}"
            )
            if last_message.get("messageType") in [
                "command_approval",
                "command_permission_request",
            ]:
                logger.error("DEBUG: Detected command approval response needed")
                is_command_approval_response = True

                # Check if this is command feedback rather than approval/denial
                if message.lower().startswith("command feedback:"):
                    is_command_feedback = True

                # Handle command approval response
                user_response_lower = message.lower().strip()
                if user_response_lower in [
                    "yes",
                    "y",
                    "approve",
                    "run",
                    "execute",
                    "ok",
                ]:
                    # User approved command execution
                    # Try both old and new command storage formats
                    command_to_run = last_message.get("command", "")
                    if not command_to_run and "rawData" in last_message:
                        # New format - command stored in rawData
                        command_to_run = last_message.get("rawData", {}).get(
                            "command", ""
                        )
                    if command_to_run:
                        try:
                            # Execute the approved command via chat terminal
                            # Import the terminal execution function
                            from pydantic import BaseModel

                            from backend.api.terminal import execute_single_command

                            class CommandRequest(BaseModel):
                                command: str
                                timeout: Optional[float] = 30.0

                            # Create a command request
                            cmd_request = CommandRequest(
                                command=command_to_run, timeout=30.0
                            )

                            # Execute command through terminal endpoint
                            terminal_result = await execute_single_command(cmd_request)

                            # The terminal function returns a JSONResponse or dict
                            if hasattr(terminal_result, "body"):
                                # It's a JSONResponse, extract the content
                                import json

                                result_data = json.loads(terminal_result.body)
                            else:
                                # It's already a dict
                                result_data = terminal_result

                            # Check if command succeeded
                            if (
                                result_data.get("status") == "success"
                                or result_data.get("exit_code") == 0
                            ):
                                output = result_data.get("output", "No output")

                                # Interpret the command output for the user
                                interpretation = await _interpret_command_output(
                                    command_to_run, output, llm_interface
                                )

                                response_data = {
                                    "role": "assistant",
                                    "content": f"✅ Command executed successfully!\n\n**Command**: `{command_to_run}`\n**Output**: ```\n{output}\n```\n\n**Interpretation**: {interpretation}",
                                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "messageType": "command_result",
                                    "rawData": result_data,
                                }
                                return JSONResponse(
                                    status_code=200, content=response_data
                                )
                            else:
                                error_msg = result_data.get(
                                    "message", "Command execution failed"
                                )
                                output = result_data.get("output", "")
                                response_data = {
                                    "role": "assistant",
                                    "content": f"❌ {error_msg}\n\nOutput: ```\n{output}\n```",
                                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "messageType": "error",
                                    "rawData": result_data,
                                }
                                return JSONResponse(
                                    status_code=200, content=response_data
                                )

                        except Exception as cmd_error:
                            logger.error(f"Command execution failed: {cmd_error}")
                            response_data = {
                                "role": "assistant",
                                "content": f"❌ Failed to execute command: {str(cmd_error)}",
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "messageType": "error",
                                "rawData": None,
                            }
                            return JSONResponse(status_code=200, content=response_data)

                elif user_response_lower in ["no", "n", "decline", "cancel", "skip"]:
                    # User declined command execution
                    response_data = {
                        "role": "assistant",
                        "content": "👌 Command execution cancelled. Is there anything else I can help you with?",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "messageType": "info",
                        "rawData": None,
                    }
                    return JSONResponse(status_code=200, content=response_data)
                else:
                    # Invalid response, ask again
                    response_data = {
                        "role": "assistant",
                        "content": "Please respond with 'yes' to execute the command, or 'no' to cancel.",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "messageType": "clarification",
                        "rawData": None,
                    }
                    return JSONResponse(status_code=200, content=response_data)

        # Handle command feedback
        if is_command_feedback:
            # Extract the feedback from the message
            feedback_text = message[len("command feedback:") :].strip()
            original_command = last_message.get("rawData", {}).get(
                "command", "unknown command"
            )

            response_data = {
                "role": "assistant",
                "content": f"Thank you for the feedback on the command `{original_command}`!\n\n**Your feedback**: {feedback_text}\n\nI'll take this into consideration. Would you like me to:\n1. Try a different command based on your suggestion\n2. Explain alternative approaches\n3. Skip this operation entirely\n\nPlease let me know how you'd like to proceed.",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messageType": "feedback_response",
                "rawData": {
                    "original_command": original_command,
                    "user_feedback": feedback_text,
                    "options": [
                        "try_different",
                        "explain_alternatives",
                        "skip_operation",
                    ],
                },
            }

            return JSONResponse(status_code=200, content=response_data)

        # Check if this is a system/technical query that needs command execution
        command_needed = await _check_if_command_needed(message, llm_interface)
        if command_needed and not is_command_approval_response:
            # Return special response to trigger command permission dialog
            response_data = {
                "role": "assistant",
                "content": f"🔧 **Command Required**: {command_needed['explanation']}\n\n**Command**: `{command_needed['command']}`\n\n**Purpose**: {command_needed['purpose']}\n\n**Do you want me to execute this command?** (Reply 'yes' to proceed or 'no' to cancel)",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messageType": "command_permission_request",
                "commandData": {
                    "command": command_needed["command"],
                    "purpose": command_needed["purpose"],
                    "explanation": command_needed["explanation"],
                    "riskLevel": command_needed.get("risk_level", "LOW"),
                    "originalMessage": message,
                },
                "rawData": command_needed,
            }

            # Save this request to chat history with the command data
            approval_message = {
                "sender": "bot",
                "text": response_data["content"],
                "messageType": "command_permission_request",
                "rawData": command_needed,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            existing_history.append(approval_message)
            if chat_history_manager:
                # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
                await asyncio.to_thread(
                    chat_history_manager.save_session,
                    chat_id,
                    messages=existing_history,
                )

            return JSONResponse(status_code=200, content=response_data)

        # Enhanced knowledge search workflow
        if (
            knowledge_base
            and not is_approval_response
            and not is_command_approval_response
        ):
            try:
                # Check if this seems like a query that should trigger knowledge/web search
                should_search = (
                    len(message.split()) > 2
                    and any(  # More than 2 words
                        word in message.lower()
                        for word in [
                            "what",
                            "how",
                            "why",
                            "when",
                            "where",
                            "who",
                            "explain",
                            "tell me",
                            "information",
                            "about",
                            "details",
                            "learn",
                        ]
                    )
                    and not command_needed  # Don't search if command is needed
                )

                if should_search:
                    logger.info(f"Triggering enhanced knowledge search for: {message}")
                    search_result = await _enhanced_knowledge_search(
                        message,
                        knowledge_base,
                        chat_history_manager,
                        chat_id,
                        existing_history,
                    )

                    if search_result["source"] == "knowledge_base":
                        # Found in KB, use that information
                        kb_content = (
                            search_result["results"][0]["content"]
                            if search_result["results"]
                            else ""
                        )
                        enhanced_message = f"Based on knowledge base: {message}\n\nRelevant information: {kb_content[:1000]}"

                        # Get LLM response with KB context
                        messages = [
                            {
                                "role": "system",
                                "content": "Answer based on the provided knowledge base information. Be helpful and informative.",
                            },
                            {"role": "user", "content": enhanced_message},
                        ]
                    elif search_result[
                        "source"
                    ] == "web_research" and search_result.get("needs_approval"):
                        # Web research found, approval requested - return early
                        return JSONResponse(
                            status_code=200,
                            content={
                                "role": "assistant",
                                "content": "Information sourced from the web. Please check the source approval message above.",
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "messageType": "info",
                                "rawData": None,
                            },
                        )
                    else:
                        # Use regular message flow
                        messages = [{"role": "user", "content": message}]
                else:
                    # Regular message, no knowledge search needed
                    messages = [{"role": "user", "content": message}]

            except Exception as kb_error:
                logger.error(f"Knowledge base search failed: {kb_error}")
                # Fall back to regular message flow
                messages = [{"role": "user", "content": message}]
        else:
            # No knowledge base available or approval response, use regular flow
            messages = [{"role": "user", "content": message}]

        # Get a response using LLM interface with hybrid acceleration
        try:
            logger.info(f"Sending message to LLM with failsafe system: {message}")

            # Use the robust failsafe LLM system that guarantees a response
            context = {
                "chat_id": chat_id,
                "message_history": messages,
                "timestamp": time.time(),
                "endpoint": "direct_chat",
            }

            failsafe_response = await get_robust_llm_response(message, context)

            logger.info(
                f"Got failsafe LLM response using tier: {failsafe_response.tier_used.value}"
            )
            logger.info(f"Response confidence: {failsafe_response.confidence}")
            logger.info(f"Model used: {failsafe_response.model_used}")

            if failsafe_response.warnings:
                logger.warning(f"LLM warnings: {failsafe_response.warnings}")

            # The failsafe system always returns content
            content = failsafe_response.content
            logger.info(f"Extracted content: {content[:200]}...")

            # Create a compatible response structure for downstream processing
            _ = {
                "message": {"role": "assistant", "content": content},
                "tier_used": failsafe_response.tier_used.value,
                "model": failsafe_response.model_used,
                "confidence": failsafe_response.confidence,
                "warnings": failsafe_response.warnings,
            }

            logger.info(
                f"About to process chat history saving with content: {content[:100]}..."
            )

            # QUICK TEST: Return immediately after LLM call to see if it's hanging after this point
            response_data = {
                "role": "assistant",
                "content": content,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messageType": "response",
                "rawData": None,
            }
            logger.info(f"Returning response data: {response_data}")
            return JSONResponse(status_code=200, content=response_data)

            # Save conversation to chat history if chat_history_manager is available
            if chat_history_manager:
                try:
                    # Create user message
                    user_message = {
                        "sender": "user",
                        "text": message,
                        "messageType": "user",
                        "rawData": None,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    # Create assistant response
                    assistant_message = {
                        "sender": "bot",
                        "text": content,
                        "messageType": "response",
                        "rawData": None,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    # Load existing history - PERFORMANCE FIX: Convert to async
                    existing_history = (
                        await asyncio.to_thread(
                            chat_history_manager.load_session, chat_id
                        )
                        or []
                    )

                    # Add new messages
                    existing_history.extend([user_message, assistant_message])

                    # Save updated history - PERFORMANCE FIX: Convert to async
                    await asyncio.to_thread(
                        chat_history_manager.save_session,
                        chat_id,
                        messages=existing_history,
                    )

                    logger.info(f"Saved conversation to chat history for {chat_id}")

                except Exception as save_error:
                    logger.error(f"Failed to save chat history: {save_error}")
                    # Don't fail the request if history saving fails

            # Format response for API
            response_data = {
                "role": "assistant",
                "content": content,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messageType": "response",
                "rawData": None,
            }

            return JSONResponse(status_code=200, content=response_data)

        except Exception as llm_error:
            logger.error(f"Direct LLM error: {llm_error}")
            import traceback

            logger.error(f"LLM error traceback: {traceback.format_exc()}")
            # Fallback to a simple response
            fallback_response = {
                "role": "assistant",
                "content": f"I'm having trouble processing your request right now. Your message '{message}' was received but I encountered an error.",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messageType": "response",
                "rawData": None,
            }
            return JSONResponse(status_code=200, content=fallback_response)

    except Exception as e:
        logger.error(f"Error in direct chat endpoint: {str(e)}")
        import traceback

        logger.error(f"Direct chat error traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500, content={"error": f"Error processing message: {str(e)}"}
        )


@router.post("/chat")
async def send_chat_message_legacy(chat_message: dict, request: Request):
    """Send a message to a chat (legacy endpoint for frontend compatibility)."""
    try:
        # Route to new conversation endpoint with full KB integration and source tracking
        logger.info(
            "Routing /chat request to /chat/conversation for enhanced KB integration"
        )
        return await conversation_chat_message(chat_message, request)

    except Exception as e:
        logging.error(f"Error in legacy chat endpoint: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error processing message: {str(e)}"}
        )


@router.post("/chats/{chat_id}/message")
async def send_chat_message(chat_id: str, chat_message: ChatMessage, request: Request):
    """Send a message to a specific chat and get a response."""
    logging.info(f"DEBUG: send_chat_message called for chat_id: {chat_id}")
    try:
        # Clear previous sources for new request
        clear_sources()

        # Get the orchestrator and chat_history_manager from app state
        logging.info(
            "DEBUG: Getting orchestrator and chat_history_manager from app state..."
        )
        orchestrator = getattr(request.app.state, "orchestrator", None)
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        logging.info(
            f"DEBUG: Got orchestrator: {orchestrator is not None}, chat_history_manager: {chat_history_manager is not None}"
        )

        # Get chat knowledge manager if available
        chat_knowledge_manager = None
        try:
            logging.info("DEBUG: Importing chat knowledge manager...")
            from backend.api.chat_knowledge import chat_knowledge_manager as ckm

            chat_knowledge_manager = ckm
            logging.info("DEBUG: Chat knowledge manager imported successfully")
        except ImportError:
            logging.info("Chat knowledge manager not available")

        if orchestrator is None:
            logging.error("orchestrator not found in app.state")
            return JSONResponse(
                status_code=500, content={"error": "Orchestrator not initialized"}
            )

        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(
                status_code=500,
                content={"error": "Chat history manager not initialized"},
            )

        message = chat_message.message
        logging.info(f"Received chat message for chat {chat_id}: {message}")

        # Add user message to chat history
        user_message = {
            "sender": "user",
            "text": message,
            "messageType": "user",
            "rawData": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Load existing chat history - PERFORMANCE FIX: Convert to async
        existing_history = (
            await asyncio.to_thread(chat_history_manager.load_session, chat_id) or []
        )
        existing_history.append(user_message)

        # Update chat knowledge context if available
        logger.info("DEBUG: Starting chat knowledge context processing...")
        enhanced_message = message
        if chat_knowledge_manager:
            logger.info(
                "DEBUG: Chat knowledge manager available, processing context..."
            )
            try:
                # Get or create context for this chat
                context = chat_knowledge_manager.chat_contexts.get(chat_id)
                logger.info(
                    f"DEBUG: Got context for chat {chat_id}: {context is not None}"
                )
                if not context:
                    # Extract topic from first few messages
                    topic = (
                        f"Chat about: {message[:50]}..."
                        if len(message) > 50
                        else message
                    )
                    logger.info(
                        f"DEBUG: Creating new context for chat {chat_id} with topic: {topic}"
                    )
                    context = await chat_knowledge_manager.create_or_update_context(
                        chat_id=chat_id, topic=topic
                    )
                    logger.info(
                        f"DEBUG: Context created successfully for chat {chat_id}"
                    )

                # Add temporary knowledge from this message
                if len(message) > 100:  # Only store substantial messages
                    await chat_knowledge_manager.add_temporary_knowledge(
                        chat_id=chat_id,
                        content=message,
                        metadata={
                            "type": "user_message",
                            "timestamp": user_message["timestamp"],
                        },
                    )

                # TEMPORARY FIX: Disable chat knowledge search to prevent hanging
                # TODO: Fix chat_knowledge_manager.search_chat_knowledge hanging issue
                # chat_context = await chat_knowledge_manager.search_chat_knowledge(
                #     query=message,
                #     chat_id=chat_id,
                #     include_temporary=True
                # )
                chat_context = []  # Empty context for now

                # Enhance message with context for better responses
                if chat_context and len(chat_context) > 0:
                    _ = "\n".join(
                        [
                            f"- {item['content'][:100]}..."
                            for item in chat_context[:3]  # Top 3 relevant contexts
                        ]
                    )
                    enhanced_message = """Based on our previous conversation context:
{context_summary}

Current question: {message}"""
                    logging.info(
                        f"Enhanced message with {len(chat_context)} context items"
                    )

            except Exception as e:
                logging.error(f"Failed to update chat knowledge context: {e}")

        logger.info(
            "DEBUG: Finished chat knowledge context processing, starting KB Librarian..."
        )

        # PHASE 2: Knowledge Base First Approach - Always search KB for grounded responses
        logger.info("DEBUG: Starting Knowledge Base search with timeout protection...")
        kb_result = {
            "documents_found": 0,
            "is_question": False,
            "answer": "",
            "sources": [],
            "bypassed": False,
        }

        try:
            # Get KB librarian with timeout protection
            kb_librarian = get_kb_librarian()
            if kb_librarian:
                # Add timeout to prevent hanging (10 second limit)
                kb_search_task = asyncio.create_task(
                    kb_librarian.process_query(enhanced_message)
                )
                kb_result = await asyncio.wait_for(kb_search_task, timeout=10.0)

                # Add source attribution with tracking
                if kb_result.get("documents_found", 0) > 0:
                    # Track KB sources
                    kb_docs = kb_result.get("documents", [])
                    for doc in kb_docs[:3]:  # Track top 3 relevant docs
                        source_manager.add_kb_source(
                            content=doc.get("content", "")[:200],
                            entry_id=doc.get("id", "unknown"),
                            confidence=doc.get("score", 0.8),
                            metadata={
                                "category": doc.get("category"),
                                "title": doc.get("title"),
                            },
                        )

                    # Send attribution message if sources toggle is on
                    attribution_msg = source_manager.format_attribution_block()
                    if attribution_msg:
                        await _send_typed_message(
                            existing_history,
                            "source",
                            attribution_msg,
                            chat_history_manager,
                            chat_id,
                        )
                logger.info(
                    f"DEBUG: KB search completed - found {kb_result.get('documents_found', 0)} documents"
                )
            else:
                logger.warning("DEBUG: KB Librarian not available")

        except asyncio.TimeoutError:
            logger.warning(
                "DEBUG: KB search timed out after 10 seconds - continuing without KB results"
            )
            kb_result["timeout"] = True
        except Exception as e:
            logger.error(f"DEBUG: KB search failed: {e}")
            kb_result["error"] = str(e)

        # TEMPORARY FIX: Disable web research to prevent hanging
        web_research_result = None
        # if (
        #     kb_result.get("is_question", False)
        #     and kb_result.get("documents_found", 0) == 0
        #     and _should_research_web(message)
        # ):
        #     try:
        #         librarian_assistant = get_librarian_assistant()
        #         web_research_result = await librarian_assistant.research_query(message)
        #         logger.info(f"Web research completed for query: {message}")
        #     except Exception as e:
        #         logger.error(f"Web research failed: {e}")
        #         web_research_result = {"error": str(e)}

        # USE LIGHTWEIGHT ORCHESTRATOR for intelligent routing without blocking
        logger.info("DEBUG: Using LightweightOrchestrator for request routing...")
        from src.lightweight_orchestrator import lightweight_orchestrator

        # Check if we should bypass full orchestration
        request_path = request.url.path
        routing_decision = await lightweight_orchestrator.route_request(
            request_path, enhanced_message
        )
        logger.info(f"DEBUG: Routing decision: {routing_decision}")

        if routing_decision["bypass_orchestration"]:
            # Use lightweight orchestrator response
            simple_response = routing_decision.get("simple_response")
            if simple_response:
                logger.info(
                    f"DEBUG: Using simple response from lightweight orchestrator: {simple_response}"
                )
                orchestrator_result = {
                    "response_text": simple_response,
                    "status": "success",
                    "routing_method": "lightweight_pattern_match",
                }
            else:
                # Default fallback for bypassed requests
                orchestrator_result = {
                    "response_text": "I'm ready to help! What would you like me to assist you with?",
                    "status": "success",
                    "routing_method": "lightweight_fallback",
                }
        else:
            # For complex requests that need full orchestration
            complexity = routing_decision["complexity"]
            logger.info(
                f"DEBUG: Request requires full orchestration (complexity: {complexity})"
            )

            # TEMPORARY: Still bypass full orchestrator until blocking issues are resolved
            # TODO: Re-enable full orchestrator once Redis pubsub blocking is fixed
            logger.info(
                "DEBUG: TEMPORARILY using robust LLM response instead of full orchestrator"
            )
            try:
                # Use the LLM failsafe agent for complex responses with KB context
                from src.agents.llm_failsafe_agent import get_robust_llm_response

                # Build enhanced context with KB results
                kb_context = ""
                if kb_result.get("documents_found", 0) > 0:
                    kb_context = f"\n\nKnowledge Base Context:\n{kb_result.get('answer', 'Relevant information found in knowledge base.')}"

                enhanced_context = f"""Chat ID: {chat_id}
Knowledge Base documents found: {kb_result.get('documents_found', 0)}
{kb_context}

IMPORTANT: Always cite sources when using information from the Knowledge Base.
If no KB documents were found, clearly state this and provide general knowledge responses."""

                response = await get_robust_llm_response(
                    user_input=enhanced_message,
                    context=enhanced_context,
                    response_type="chat",
                )

                # Track LLM source
                if kb_result.get("documents_found", 0) == 0:
                    # No KB documents, so this is purely from LLM training
                    track_source(
                        SourceType.LLM_TRAINING,
                        "Response generated from model training knowledge",
                        reliability=SourceReliability.MEDIUM,
                        metadata={"model": "artifish/llama3.2-uncensored:latest"},
                    )

                orchestrator_result = {
                    "response_text": response.get(
                        "response",
                        "I'm processing your request. Please wait a moment...",
                    ),
                    "status": "success",
                    "routing_method": "llm_failsafe_temporary",
                }
            except Exception as e:
                logger.error(f"LLM failsafe failed: {e}")
                orchestrator_result = {
                    "response_text": f"I received your message: '{message}'. I'm currently optimizing my response capabilities. Please try again in a moment.",
                    "status": "fallback",
                    "routing_method": "error_fallback",
                }

        logger.info(
            "DEBUG: Finished orchestrator execution, continuing to workflow check..."
        )

        # Check if this should trigger an automated workflow
        if WORKFLOW_AUTOMATION_AVAILABLE and workflow_manager:
            try:
                # Check if message indicates need for automated execution
                automation_keywords = [
                    "install",
                    "setup",
                    "configure",
                    "deploy",
                    "update",
                    "upgrade",
                    "build",
                    "compile",
                    "run steps",
                    "execute workflow",
                    "automate",
                    "step by step",
                    "automatically",
                    "batch",
                    "sequence",
                ]

                if any(keyword in message.lower() for keyword in automation_keywords):
                    # Create workflow from chat request
                    workflow_id = (
                        await workflow_manager.create_workflow_from_chat_request(
                            message, chat_id
                        )
                    )

                    if workflow_id:
                        logger.info(
                            f"Created automated workflow {workflow_id} for chat {chat_id}"
                        )

                        # Add workflow info to orchestrator result
                        if isinstance(orchestrator_result, dict):
                            orchestrator_result["workflow_id"] = workflow_id
                            orchestrator_result["workflow_triggered"] = True

            except Exception as e:
                logger.error(f"Failed to create workflow from chat: {e}")

        # Process the result similar to the /goal endpoint
        if isinstance(orchestrator_result, dict):
            result_dict = orchestrator_result
        else:
            result_dict = {"message": str(orchestrator_result)}

        # Debug logging for empty responses
        logging.info(f"Orchestrator result for chat {chat_id}: {result_dict}")
        response_message = "An unexpected response format was received."
        tool_name = result_dict.get("tool_name")
        tool_args = result_dict.get("tool_args", {})

        # Debug logging for tool detection
        logging.info(f"🔍 DEBUG tool_name detected: '{tool_name}'")

        # Ensure tool_args is a dictionary
        if not isinstance(tool_args, dict):
            tool_args = {}

        if tool_name == "respond_conversationally":
            response_text = tool_args.get("response_text", "No response text provided.")
            result_response_text = result_dict.get("response_text")
            logging.info(
                "🔍 DEBUG respond_conversationally: "
                f"response_text={response_text}, "
                f"result_response_text={result_response_text}"
            )
            # Handle empty string, None, or whitespace-only responses
            if result_response_text and result_response_text.strip():
                # Try to extract plain text from JSON response if it's JSON
                try:
                    import json

                    parsed_response = json.loads(result_response_text)
                    if isinstance(parsed_response, dict):
                        # Try common text fields in JSON response
                        extracted_text = (
                            parsed_response.get("text")
                            or parsed_response.get("message")
                            or parsed_response.get("content")
                            or parsed_response.get("response")
                            or parsed_response.get("user")
                            or parsed_response.get("user")
                            or parsed_response.get("hello")  # Handle "hello" field
                        )

                        # If no common field found, try sophisticated extraction
                        if not extracted_text:
                            extracted_text = _extract_text_from_complex_json(
                                parsed_response
                            )

                        # If we found a text field, use it
                        if extracted_text and isinstance(extracted_text, str):
                            response_message = extracted_text
                        else:
                            # If no text field found, log structure and return raw JSON
                            logging.info(
                                "JSON response without recognizable text field: "
                                f"{parsed_response}"
                            )
                            # Return JSON as-is to see structure
                            response_message = result_response_text
                    else:
                        response_message = result_response_text
                except json.JSONDecodeError:
                    # If it's not JSON, use it as-is
                    response_message = result_response_text
            elif response_text and response_text.strip():
                # Apply same JSON extraction logic to response_text
                try:
                    import json

                    parsed_response = json.loads(response_text)
                    if isinstance(parsed_response, dict):
                        extracted_text = (
                            parsed_response.get("text")
                            or parsed_response.get("message")
                            or parsed_response.get("content")
                            or parsed_response.get("response")
                            or parsed_response.get("user")
                            or parsed_response.get("hello")
                        )

                        # If no common field found, try sophisticated extraction
                        if not extracted_text:
                            extracted_text = _extract_text_from_complex_json(
                                parsed_response
                            )
                        if extracted_text and isinstance(extracted_text, str):
                            response_message = extracted_text
                        else:
                            response_message = response_text
                    else:
                        response_message = response_text
                except json.JSONDecodeError:
                    response_message = response_text
            else:
                response_message = (
                    "I apologize, but I wasn't able to generate a proper response. "
                    "Could you please rephrase your question?"
                )
            logging.info(
                "🔍 DEBUG respond_conversationally final "
                f"response_message: {response_message}"
            )
        # Send KB findings as separate utility message if available
        if (
            kb_result.get("is_question")
            and kb_result.get("documents_found", 0) > 0
            and "summary" in kb_result
        ):
            kb_summary = kb_result["summary"]
            kb_utility_message = f"📚 **Knowledge Base Information:**\n{kb_summary}"
            await _send_typed_message(
                existing_history,
                "utility",
                kb_utility_message,
                chat_history_manager,
                chat_id,
            )
            logging.info(
                f"Sent KB findings as separate utility message: {kb_result['documents_found']} documents"
            )
        elif kb_result.get("is_question") and kb_result.get("documents_found", 0) == 0:
            # Send "no KB info" as utility message when it's a question but no results found
            kb_utility_message = "📚 **Knowledge Base Information:** None"
            await _send_typed_message(
                existing_history,
                "utility",
                kb_utility_message,
                chat_history_manager,
                chat_id,
            )

        # Send web research results as separate utility message if available
        elif (
            web_research_result
            and web_research_result.get("summary")
            and not web_research_result.get("error")
        ):
            web_summary = web_research_result["summary"]
            sources = web_research_result.get("sources", [])

            # Format sources
            sources_text = ""
            if sources:
                sources_text = "\n\n**Sources:**\n" + "\n".join(
                    [
                        f"• {source['title']} ({source['domain']}) - "
                        f"Quality: {source.get('quality_score', 'N/A')}"
                        for source in sources[:3]
                    ]
                )

            # Send web research as separate utility message
            web_utility_message = (
                f"🌐 **Web Research Results:**\n{web_summary}{sources_text}"
            )
            await _send_typed_message(
                existing_history,
                "utility",
                web_utility_message,
                chat_history_manager,
                chat_id,
            )

            # Send storage note as separate utility message
            stored_count = len(web_research_result.get("stored_in_kb", []))
            if stored_count > 0:
                storage_note = f"*Note: {stored_count} high-quality sources were added to the knowledge base for future reference.*"
                await _send_typed_message(
                    existing_history,
                    "utility",
                    storage_note,
                    chat_history_manager,
                    chat_id,
                )

            logging.info(
                f"Sent web research as separate utility messages: {len(sources)} sources found, "
                f"{stored_count} stored in KB"
            )

        elif tool_name == "execute_system_command":
            command_output = tool_args.get("output", "")
            command_error = tool_args.get("error", "")
            command_status = tool_args.get("status", "unknown")

            if command_status == "success":
                response_message = (
                    f"Command executed successfully.\nOutput:\n{command_output}"
                )
            else:
                response_message = (
                    f"Command failed ({command_status}).\nError:\n{command_error}"
                    f"\nOutput:\n{command_output}"
                )
        elif tool_name == "workflow_orchestrator":
            # Handle workflow orchestration results - send separate messages
            logging.info(
                f"🚀 WORKFLOW ORCHESTRATOR HANDLER ACTIVATED for chat {chat_id}"
            )
            workflow_details = result_dict.get("workflow_details", {})
            tool_args = result_dict.get("tool_args", {})

            # Send planning message
            planning_info = """Classification: {tool_args.get('message_classification', 'unknown')}
Agents Involved: {', '.join(tool_args.get('agents_involved', []))}
Planned Steps: {tool_args.get('planned_steps', 0)}
Estimated Duration: {tool_args.get('estimated_duration', 'unknown')}
User Approvals Needed: {tool_args.get('user_approvals_needed', 0)}"""

            await _send_typed_message(
                existing_history,
                "planning",
                planning_info,
                chat_history_manager,
                chat_id,
            )

            # Send thoughts message about workflow execution
            thoughts_text = f"Analyzing request complexity and determining optimal agent coordination strategy. This {tool_args.get('message_classification', 'unknown')} request requires {tool_args.get('planned_steps', 0)} coordinated steps across {len(tool_args.get('agents_involved', []))} specialized agents."

            await _send_typed_message(
                existing_history,
                "thought",
                thoughts_text,
                chat_history_manager,
                chat_id,
            )

            # Send utility messages for each agent step
            agent_results = workflow_details.get("agent_results", [])
            for result in agent_results:
                utility_text = f"Step {result['step']}: {result['agent']} agent completed '{result['action']}' in {result['duration']} - {result['result']}"
                await _send_typed_message(
                    existing_history,
                    "utility",
                    utility_text,
                    chat_history_manager,
                    chat_id,
                )

                # Send debug message for each step execution
                debug_text = f"Agent: {result['agent']} | Action: {result['action']} | Duration: {result['duration']} | Status: completed"
                await _send_typed_message(
                    existing_history, "debug", debug_text, chat_history_manager, chat_id
                )

            # Send JSON output with technical details
            json_output = {
                "workflow_executed": result_dict.get("workflow_executed", False),
                "classification": tool_args.get("message_classification"),
                "agents_coordinated": len(tool_args.get("agents_involved", [])),
                "steps_executed": workflow_details.get("steps_executed", 0),
                "execution_status": workflow_details.get("execution_status"),
                "total_duration": (
                    sum(float(r["duration"].replace("s", "")) for r in agent_results)
                    if agent_results
                    else 0
                ),
            }

            await _send_typed_message(
                existing_history,
                "json",
                json.dumps(json_output, indent=2),
                chat_history_manager,
                chat_id,
            )

            # Main response message
            response_message = workflow_details.get(
                "response_text",
                result_dict.get(
                    "response_text",
                    "Multi-agent workflow coordination completed successfully.",
                ),
            )
        elif tool_name:
            tool_output_content = tool_args.get(
                "output", tool_args.get("message", str(tool_args))
            )
            response_message = f"Tool Used: {tool_name}\nOutput: {tool_output_content}"
        elif result_dict.get("output"):
            response_message = result_dict["output"]
        elif result_dict.get("message"):
            response_message = result_dict["message"]
        else:
            # Handle completely empty or invalid responses
            if not result_dict or result_dict == {}:
                response_message = (
                    "I'm sorry, I encountered an issue processing your request. "
                    "Please try asking your question in a different way."
                )
                logging.warning(
                    f"Empty orchestrator result for chat {chat_id}, "
                    f"message: {message}"
                )
            else:
                response_message = str(result_dict)

        # Add bot response to chat history (skip for workflow orchestrator since separate messages already sent)
        if tool_name != "workflow_orchestrator":
            # Add final source attribution summary
            final_attribution = source_manager.format_attribution_block()
            if final_attribution and kb_result.get("documents_found", 0) > 0:
                response_message += f"\n\n{final_attribution}"

            bot_message = {
                "sender": "bot",
                "text": response_message,
                "messageType": "response",
                "rawData": result_dict,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "sources": [
                    s.to_dict() for s in source_manager.current_response_sources
                ],
            }
            # Add KB search results to metadata if available
            if kb_result.get("is_question") and kb_result.get("documents_found", 0) > 0:
                bot_message["kb_search_performed"] = True
                bot_message["kb_documents_found"] = kb_result["documents_found"]
                bot_message["kb_documents"] = kb_result.get("documents", [])

            # Add web research results to metadata if available
            if web_research_result and not web_research_result.get("error"):
                bot_message["web_research_performed"] = True
                bot_message["web_sources_found"] = len(
                    web_research_result.get("sources", [])
                )
                bot_message["web_sources"] = web_research_result.get("sources", [])
                bot_message["web_stored_in_kb"] = len(
                    web_research_result.get("stored_in_kb", [])
                )

            existing_history.append(bot_message)

        # Save updated chat history - PERFORMANCE FIX: Convert to async
        await asyncio.to_thread(
            chat_history_manager.save_session, chat_id, messages=existing_history
        )

        return JSONResponse(
            status_code=200,
            content={
                "response": response_message,
                "status": "success",
                "chat_id": chat_id,
                "message_count": len(existing_history),
            },
        )

    except Exception as e:
        logging.error(f"Error processing chat message for {chat_id}: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500, content={"error": f"Error processing message: {str(e)}"}
        )


@router.post("/chats/cleanup_messages")
async def cleanup_messages():
    """Clean up all leftover message files including json_output,
    llm_response, planning and debug messages"""
    try:
        cleaned_files = []
        freed_space = 0

        # Enhanced file patterns to catch ALL leftover files mentioned in the task
        file_patterns = [
            # Specific patterns mentioned in the task
            "json_output*",
            "llm_response*",
            "planning*",
            "debug*",
            # Variations and related patterns
            "*json_output*",
            "*llm_response*",
            "*planning*",
            "*debug*",
            "json_output",
            "llm_response",
            "planning",
            "debug",
            # Common temporary and output files
            "*.tmp",
            "*.log",
            "*.cache",
            "*.bak",
            "*.out",
            "*_response*",
            "*_output*",
            "*_debug*",
            "*_planning*",
            "response_*",
            "output_*",
            "debug_*",
            "planning_*",
            # Chat-related temporary files
            "chat_temp*",
            "temp_*",
            "*.temp",
            # Any .txt files that match leftover patterns
            # Will be filtered to exclude legitimate chat files
            "*.txt",
        ]

        # Specific patterns found in search results
        specific_patterns = [
            "*_json_output.json",
            "*_planning_debug.json",
            "*_llm_response.json",
            "*_planning*.json",
            "*_debug*.json",
            "*_output*.json",
        ]

        # ONLY scan data/messages/ directory - NEVER touch prompts/ or
        # other system directories
        messages_dir = "data/messages"
        if os.path.exists(messages_dir):
            logging.info(f"Scanning messages directory: {messages_dir}")
            # PERFORMANCE FIX: Convert blocking directory scan to async
            chat_folders = await asyncio.to_thread(os.listdir, messages_dir)
            for chat_folder in chat_folders:
                chat_folder_path = os.path.join(messages_dir, chat_folder)
                if os.path.isdir(chat_folder_path):
                    logging.info(f"Processing chat folder: {chat_folder_path}")
                    folder_cleaned = False

                    # Look for leftover files in each chat folder - ONLY in
                    # data/messages/
                    for file_pattern in file_patterns:
                        for filepath in glob.glob(
                            os.path.join(chat_folder_path, file_pattern)
                        ):
                            if os.path.isfile(filepath):
                                filename = os.path.basename(filepath)

                                # SAFETY CHECK: Only process files in data/messages/
                                if not filepath.startswith("data/messages/"):
                                    continue

                                # Special handling for .txt files - only remove
                                # if they match leftover patterns
                                if filename.endswith(".txt"):
                                    # Only remove .txt files that match
                                    # leftover patterns
                                    patterns = [
                                        "json_output",
                                        "llm_response",
                                        "planning",
                                        "debug",
                                        "temp",
                                    ]
                                    if any(
                                        pattern in filename.lower()
                                        for pattern in patterns
                                    ):
                                        pass  # Will be removed
                                    else:
                                        continue  # Skip legitimate .txt files
                                try:
                                    file_size = os.path.getsize(filepath)
                                    os.remove(filepath)
                                    cleaned_files.append(filepath)
                                    freed_space += file_size
                                    folder_cleaned = True
                                    logging.info(f"Removed leftover file: {filepath}")
                                except Exception as e:
                                    logging.error(
                                        f"Error removing file {filepath}: {str(e)}"
                                    )

                    # Also check for any files with specific names mentioned in the task
                    specific_leftover_files = [
                        "json_output",
                        "llm_response",
                        "planning",
                        "debug",
                    ]
                    for specific_file in specific_leftover_files:
                        specific_filepath = os.path.join(
                            chat_folder_path, specific_file
                        )
                        if os.path.exists(specific_filepath):
                            try:
                                if os.path.isfile(specific_filepath):
                                    file_size = os.path.getsize(specific_filepath)
                                    os.remove(specific_filepath)
                                    cleaned_files.append(specific_filepath)
                                    freed_space += file_size
                                    folder_cleaned = True
                                    logging.info(
                                        "Removed specific leftover file: "
                                        f"{specific_filepath}"
                                    )
                                elif os.path.isdir(specific_filepath):
                                    # Remove entire leftover directory
                                    # PERFORMANCE FIX: Convert blocking directory traversal to async
                                    def calculate_dir_size(path):
                                        return sum(
                                            os.path.getsize(
                                                os.path.join(dirpath, filename)
                                            )
                                            for dirpath, dirnames, filenames in os.walk(
                                                path
                                            )
                                            for filename in filenames
                                        )

                                    dir_size = await asyncio.to_thread(
                                        calculate_dir_size, specific_filepath
                                    )
                                    shutil.rmtree(specific_filepath)
                                    cleaned_files.append(
                                        "Removed leftover directory: "
                                        f"{specific_filepath}"
                                    )
                                    freed_space += dir_size
                                    folder_cleaned = True
                                    logging.info(
                                        "Removed leftover directory: "
                                        f"{specific_filepath}"
                                    )
                            except Exception as e:
                                logging.error(
                                    "Error removing specific leftover file/dir "
                                    f"{specific_filepath}: {str(e)}"
                                )

                    # Scan for specific patterns found in search results
                    for pattern in specific_patterns:
                        for filepath in glob.glob(
                            os.path.join(chat_folder_path, pattern)
                        ):
                            if os.path.isfile(filepath):
                                try:
                                    file_size = os.path.getsize(filepath)
                                    os.remove(filepath)
                                    cleaned_files.append(filepath)
                                    freed_space += file_size
                                    folder_cleaned = True
                                    logging.info(
                                        f"Removed specific pattern file: {filepath}"
                                    )
                                except Exception as e:
                                    logging.error(
                                        "Error removing specific pattern file "
                                        f"{filepath}: {str(e)}"
                                    )

                    # Remove empty chat folders or folders that only contained
                    # leftover files
                    try:
                        remaining_files = os.listdir(chat_folder_path)
                        if not remaining_files:
                            os.rmdir(chat_folder_path)
                            cleaned_files.append(f"Empty folder: {chat_folder_path}")
                            logging.info(
                                f"Removed empty chat folder: {chat_folder_path}"
                            )
                        elif folder_cleaned:
                            logging.info(
                                "Cleaned files from chat folder: "
                                f"{chat_folder_path}, remaining files: "
                                f"{remaining_files}"
                            )
                    except Exception as e:
                        logging.error(
                            f"Error removing empty folder {chat_folder_path}: {str(e)}"
                        )

        # Also clean up any leftover files in the main chat data directory
        chat_data_dir = "data/chats"
        if os.path.exists(chat_data_dir):
            logging.info(f"Scanning main chat data directory: {chat_data_dir}")
            for file_pattern in file_patterns:
                pattern_path = os.path.join(chat_data_dir, file_pattern)
                for filepath in glob.glob(pattern_path):
                    if os.path.isfile(filepath):
                        # Skip legitimate chat JSON files
                        filename = os.path.basename(filepath)
                        if filename.startswith("chat_") and filename.endswith(".json"):
                            continue
                        try:
                            file_size = os.path.getsize(filepath)
                            os.remove(filepath)
                            cleaned_files.append(filepath)
                            freed_space += file_size
                            logging.info(f"Removed leftover file: {filepath}")
                        except Exception as e:
                            logging.error(f"Error removing file {filepath}: {str(e)}")

        message = (
            f"Cleaned up {len(cleaned_files)} leftover files"
            if cleaned_files
            else "No leftover files found to clean up"
        )
        logging.info(f"Cleanup completed: {message}")

        return {
            "status": "success",
            "message": message,
            "cleaned_files": cleaned_files,
            "freed_space_bytes": freed_space,
        }

    except Exception as e:
        logging.error(f"Error during cleanup: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error during cleanup: {str(e)}"}
        )


@router.get("/history")
async def get_chat_history_api(request: Request):
    """Retrieves the conversation history from the ChatHistoryManager."""
    chat_history_manager = request.app.state.chat_history_manager
    history = chat_history_manager.get_all_messages()
    total_tokens = sum(len(msg.get("text", "").split()) for msg in history)
    return {"history": history, "tokens": total_tokens}


@router.post("/reset")
async def reset_chat_api(request: Request, user_role: str = Form("user")):
    """Clears the entire chat history."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log(
            "reset_chat", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403, content={"message": "Permission denied to reset chat."}
        )

    chat_history_manager.clear_history()
    # Import event_manager here to avoid circular imports
    from src.event_manager import event_manager

    await event_manager.publish("chat_reset", {"message": "Chat history cleared."})
    return {"message": "Chat history cleared successfully."}


@router.post("/new")
async def new_chat_session_api(request: Request, user_role: str = Form("user")):
    """Starts a new chat session by clearing the current history."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log(
            "new_chat", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403, content={"message": "Permission denied to start new chat."}
        )

    chat_history_manager.clear_history()
    from src.event_manager import event_manager

    await event_manager.publish(
        "new_chat_session", {"message": "New chat session started."}
    )
    return {"message": "New chat session started successfully."}


@router.get("/list_sessions")
async def list_chat_sessions_api(request: Request, user_role: str = Query("user")):
    """Lists available chat sessions."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log(
            "list_chat_sessions", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to list chat sessions."},
        )

    # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
    sessions = await asyncio.to_thread(chat_history_manager.list_sessions)
    return {"sessions": sessions}


@router.get("/load_session/{session_id}")
async def load_chat_session_api(
    session_id: str, request: Request, user_role: str = Query("user")
):
    """Loads a specific chat session."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log(
            "load_chat_session",
            user_role,
            "denied",
            {"session_id": session_id, "reason": "permission_denied"},
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to load chat session."},
        )

    # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
    history = await asyncio.to_thread(chat_history_manager.load_session, session_id)
    if history:
        from src.event_manager import event_manager

        await event_manager.publish(
            "chat_session_loaded",
            {"session_id": session_id, "message": "Chat session loaded."},
        )
        return {
            "message": f"Session '{session_id}' loaded successfully.",
            "history": history,
        }
    else:
        return JSONResponse(
            status_code=404, content={"message": f"Session '{session_id}' not found."}
        )


@router.post("/save_session")
async def save_chat_session_api(
    request: Request,
    session_id: str = Form("default_session"),
    user_role: str = Form("user"),
):
    """Saves the current chat history as a named session."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log(
            "save_chat_session",
            user_role,
            "denied",
            {"session_id": session_id, "reason": "permission_denied"},
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to save chat session."},
        )

    # PERFORMANCE FIX: Convert blocking file I/O to async to prevent timeouts
    await asyncio.to_thread(chat_history_manager.save_session, session_id)
    from src.event_manager import event_manager

    await event_manager.publish(
        "chat_session_saved", {"session": session_id, "message": "Chat session saved."}
    )
    return {"message": f"Current chat session saved as '{session_id}'."}


# PARALLEL OPERATIONS SUPPORT
# ===========================


class BatchChatRequest(BaseModel):
    """Request model for batch chat operations"""

    operations: List[Dict[str, Any]]
    parallel: bool = True


class BatchChatResponse(BaseModel):
    """Response model for batch chat operations"""

    results: List[Dict[str, Any]]
    success_count: int
    error_count: int
    execution_time_ms: float


@router.post("/chats/batch")
async def batch_chat_operations(request: BatchChatRequest, http_request: Request):
    """
    Execute multiple chat operations in parallel for improved performance.

    Supported operations:
    - list_chats: List all chat sessions
    - get_chat: Get specific chat by ID
    - delete_chat: Delete specific chat by ID
    - save_chat: Save chat with messages
    """
    start_time = time.time()
    request_id = generate_request_id()

    try:
        chat_history_manager = getattr(
            http_request.app.state, "chat_history_manager", None
        )
        if chat_history_manager is None:
            raise InternalError("Chat history manager not initialized")

        results = []

        if request.parallel and len(request.operations) > 1:
            # Execute operations in parallel
            tasks = []
            for op in request.operations:
                task = asyncio.create_task(
                    _execute_single_chat_operation(op, chat_history_manager, request_id)
                )
                tasks.append(task)

            # Wait for all operations to complete
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(parallel_results):
                if isinstance(result, Exception):
                    results.append(
                        {
                            "operation": request.operations[i],
                            "success": False,
                            "error": str(result),
                            "error_type": type(result).__name__,
                        }
                    )
                else:
                    results.append(result)
        else:
            # Execute operations sequentially
            for op in request.operations:
                result = await _execute_single_chat_operation(
                    op, chat_history_manager, request_id
                )
                results.append(result)

        # Calculate statistics
        success_count = sum(1 for r in results if r.get("success", False))
        error_count = len(results) - success_count
        execution_time = (time.time() - start_time) * 1000

        return BatchChatResponse(
            results=results,
            success_count=success_count,
            error_count=error_count,
            execution_time_ms=execution_time,
        )

    except Exception as e:
        logger.error(f"Batch chat operations error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Batch operation failed: {str(e)}",
                "request_id": request_id,
            },
        )


async def _execute_single_chat_operation(
    operation: Dict[str, Any], chat_history_manager, request_id: str
) -> Dict[str, Any]:
    """Execute a single chat operation with parallel processing support."""

    op_type = operation.get("type")
    op_data = operation.get("data", {})

    try:
        if op_type == "list_chats":
            # List all chat sessions
            sessions = await asyncio.to_thread(chat_history_manager.list_sessions)
            return {
                "operation": operation,
                "success": True,
                "result": {"chats": sessions},
                "type": "list_chats",
            }

        elif op_type == "get_chat":
            # Get specific chat
            chat_id = op_data.get("chat_id")
            if not chat_id:
                raise ValueError("chat_id is required for get_chat operation")

            history = await asyncio.to_thread(
                chat_history_manager.load_session, chat_id
            )
            return {
                "operation": operation,
                "success": True,
                "result": {"chat_id": chat_id, "history": history},
                "type": "get_chat",
            }

        elif op_type == "delete_chat":
            # Delete specific chat
            chat_id = op_data.get("chat_id")
            if not chat_id:
                raise ValueError("chat_id is required for delete_chat operation")

            success = await asyncio.to_thread(
                chat_history_manager.delete_session, chat_id
            )
            return {
                "operation": operation,
                "success": success,
                "result": {"deleted": success},
                "type": "delete_chat",
            }

        elif op_type == "save_chat":
            # Save chat with messages
            chat_id = op_data.get("chat_id")
            messages = op_data.get("messages", [])
            name = op_data.get("name", "")

            if not chat_id:
                raise ValueError("chat_id is required for save_chat operation")

            await asyncio.to_thread(
                chat_history_manager.save_session, chat_id, messages=messages, name=name
            )
            return {
                "operation": operation,
                "success": True,
                "result": {"saved": True},
                "type": "save_chat",
            }

        else:
            raise ValueError(f"Unsupported operation type: {op_type}")

    except Exception as e:
        logger.error(f"Single chat operation error for {op_type}: {e}")
        return {
            "operation": operation,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "type": op_type,
        }


# ENHANCED PARALLEL CHAT PROCESSING
# =================================


async def _parallel_chat_history_operations(
    chat_id: str,
    chat_history_manager,
    load_history: bool = True,
    save_messages: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Execute multiple chat history operations in parallel when possible.

    This function optimizes common patterns where we need to both load and save
    chat history by executing non-conflicting operations concurrently.
    """

    # If we need to load history and save messages, we can do them in sequence
    # but optimize the file I/O operations
    if load_history and save_messages is not None:
        # Load first, then save (sequential due to dependency)
        existing_history = (
            await asyncio.to_thread(chat_history_manager.load_session, chat_id) or []
        )
        existing_history.extend(save_messages)
        await asyncio.to_thread(
            chat_history_manager.save_session, chat_id, messages=existing_history
        )

        return {
            "loaded_history": existing_history[: -len(save_messages)]
            if save_messages
            else existing_history,
            "saved_messages": save_messages,
            "total_messages": len(existing_history),
        }

    elif load_history:
        # Just load history
        history = (
            await asyncio.to_thread(chat_history_manager.load_session, chat_id) or []
        )
        return {"loaded_history": history, "total_messages": len(history)}

    elif save_messages is not None:
        # Just save messages
        await asyncio.to_thread(
            chat_history_manager.save_session, chat_id, messages=save_messages
        )
        return {"saved_messages": save_messages, "total_messages": len(save_messages)}

    return {}
