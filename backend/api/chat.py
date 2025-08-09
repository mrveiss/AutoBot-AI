from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import uuid
import time
import logging
import traceback
import glob
import shutil
from src.agents import get_kb_librarian, get_librarian_assistant

router = APIRouter()

logger = logging.getLogger(__name__)


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
        chat_history_manager.save_session(
            chat_id, messages=[initial_message], name=name
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
    """List all available chat sessions."""
    try:
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(
                status_code=500,
                content={"error": "Chat history manager not initialized"},
            )

        sessions = chat_history_manager.list_sessions()
        return JSONResponse(status_code=200, content={"chats": sessions})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    """Get a specific chat session."""
    try:
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)
        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(
                status_code=500,
                content={"error": "Chat history manager not initialized"},
            )

        history = chat_history_manager.load_session(chat_id)
        if history is not None:
            return JSONResponse(
                status_code=200, content={"chat_id": chat_id, "history": history}
            )
        else:
            return JSONResponse(status_code=404, content={"error": "Chat not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    """Delete a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        if chat_history_manager.delete_session(chat_id):
            return JSONResponse(
                status_code=200, content={"message": "Chat deleted successfully"}
            )
        else:
            return JSONResponse(status_code=404, content={"error": "Chat not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/chats/{chat_id}")
async def save_chat_messages(chat_id: str, messages: list, request: Request):
    """Save messages for a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        chat_history_manager.save_session(chat_id, messages=messages)
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
        chat_history_manager.save_session(chat_id, messages=chat_data.messages)
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
        chat_history_manager.save_session(chat_id, messages=[initial_message])
        return JSONResponse(status_code=200, content={"status": "success"})
    except Exception as e:
        logger.error(f"Error resetting chat {chat_id}: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error resetting chat: {str(e)}"}
        )


@router.post("/chat")
async def send_chat_message_legacy(chat_message: dict, request: Request):
    """Send a message to a chat (legacy endpoint for frontend compatibility)."""
    try:
        # Extract chat_id and message from the request
        chat_id = chat_message.get("chatId")
        message = chat_message.get("message")

        if not chat_id:
            return JSONResponse(
                status_code=400, content={"error": "chatId is required"}
            )

        if not message:
            return JSONResponse(
                status_code=400, content={"error": "message is required"}
            )

        # Convert to ChatMessage object
        chat_msg = ChatMessage(message=message)

        # Call the existing endpoint logic
        return await send_chat_message(chat_id, chat_msg, request)

    except Exception as e:
        logging.error(f"Error in legacy chat endpoint: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Error processing message: {str(e)}"}
        )


@router.post("/chats/{chat_id}/message")
async def send_chat_message(chat_id: str, chat_message: ChatMessage, request: Request):
    """Send a message to a specific chat and get a response."""
    try:
        # Get the orchestrator and chat_history_manager from app state
        orchestrator = getattr(request.app.state, "orchestrator", None)
        chat_history_manager = getattr(request.app.state, "chat_history_manager", None)

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

        # Load existing chat history
        existing_history = chat_history_manager.load_session(chat_id) or []
        existing_history.append(user_message)

        # First, check knowledge base using the KB Librarian Agent
        kb_librarian = get_kb_librarian()
        kb_result = await kb_librarian.process_query(message)

        # If KB search found no results for a question, try web research
        web_research_result = None
        if (
            kb_result.get("is_question", False)
            and kb_result.get("documents_found", 0) == 0
            and _should_research_web(message)
        ):
            try:
                librarian_assistant = get_librarian_assistant()
                web_research_result = await librarian_assistant.research_query(message)
                logger.info(f"Web research completed for query: {message}")
            except Exception as e:
                logger.error(f"Web research failed: {e}")
                web_research_result = {"error": str(e)}

        # Execute the goal using the orchestrator
        orchestrator_result = await orchestrator.execute_goal(
            message, [{"role": "user", "content": message}]
        )

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

        # Ensure tool_args is a dictionary
        if not isinstance(tool_args, dict):
            tool_args = {}

        if tool_name == "respond_conversationally":
            response_text = tool_args.get("response_text", "No response text provided.")
            result_response_text = result_dict.get("response_text")
            logging.info(
                f"🔍 DEBUG respond_conversationally: "
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
                                f"JSON response without recognizable text field: "
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
                f"🔍 DEBUG respond_conversationally final "
                f"response_message: {response_message}"
            )
        # Enhance response with KB findings if available
        if (
            kb_result.get("is_question")
            and kb_result.get("documents_found", 0) > 0
            and "summary" in kb_result
        ):
            # Prepend KB findings to the response
            kb_summary = kb_result["summary"]
            response_message = (
                f"📚 **Knowledge Base Information:**\n{kb_summary}\n\n"
                f"**Response:**\n{response_message}"
            )
            logging.info(
                f"Enhanced response with {kb_result['documents_found']} KB documents"
            )

        # Enhance response with web research results if available
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

            # Prepend web research to response
            response_message = (
                f"🌐 **Web Research Results:**\n{web_summary}{sources_text}\n\n"
                f"**Response:**\n{response_message}"
            )

            # Note about knowledge base storage
            stored_count = len(web_research_result.get("stored_in_kb", []))
            if stored_count > 0:
                response_message += (
                    f"\n\n*Note: {stored_count} high-quality sources were added "
                    "to the knowledge base for future reference.*"
                )

            logging.info(
                f"Enhanced response with web research: {len(sources)} sources found, "
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

        # Add bot response to chat history
        bot_message = {
            "sender": "bot",
            "text": response_message,
            "messageType": "response",
            "rawData": result_dict,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
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

        # Save updated chat history
        chat_history_manager.save_session(chat_id, messages=existing_history)

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
            for chat_folder in os.listdir(messages_dir):
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
                                        f"Removed specific leftover file: "
                                        f"{specific_filepath}"
                                    )
                                elif os.path.isdir(specific_filepath):
                                    # Remove entire leftover directory
                                    dir_size = sum(
                                        os.path.getsize(os.path.join(dirpath, filename))
                                        for dirpath, dirnames, filenames in os.walk(
                                            specific_filepath
                                        )
                                        for filename in filenames
                                    )
                                    shutil.rmtree(specific_filepath)
                                    cleaned_files.append(
                                        f"Removed leftover directory: "
                                        f"{specific_filepath}"
                                    )
                                    freed_space += dir_size
                                    folder_cleaned = True
                                    logging.info(
                                        f"Removed leftover directory: "
                                        f"{specific_filepath}"
                                    )
                            except Exception as e:
                                logging.error(
                                    f"Error removing specific leftover file/dir "
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
                                        f"Error removing specific pattern file "
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
                                f"Cleaned files from chat folder: "
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

    sessions = chat_history_manager.list_sessions()
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

    history = chat_history_manager.load_session(session_id)
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

    chat_history_manager.save_session(session_id)
    from src.event_manager import event_manager

    await event_manager.publish(
        "chat_session_saved", {"session": session_id, "message": "Chat session saved."}
    )
    return {"message": f"Current chat session saved as '{session_id}'."}
