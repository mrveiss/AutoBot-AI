# Context Overflow Protection Integration Guide

Issue #9043

## Overview

The context overflow protection system automatically monitors token usage and prevents conversations from exceeding model context limits. It provides three modes:

- **auto**: Warns at 80%, auto-summarizes at 90%
- **warn_only**: Warns at 80%, no auto-summarization
- **disabled**: No protection

## Quick Start

### 1. Configuration

Set the default mode via environment variable:

```bash
export AUTOBOT_CONTEXT_OVERFLOW_MODE=auto  # or warn_only, disabled
```

### 2. Integration in Chat Endpoints

Add this after each LLM completion:

```python
from chat_history.overflow_integration import (
    handle_message_completion,
    create_summary_message,
)

# After LLM completion
async def handle_chat_completion(session_id: str, model: str, messages: List[Dict]):
    # Get LLM response
    response = await llm_gateway.chat_completion(
        messages=messages,
        model=model,
    )

    # Check for context overflow
    status = await handle_message_completion(
        session_id=session_id,
        model_name=model,
        llm_response=response,
        messages=messages,  # Full history for summarization
    )

    # Handle warning (emit event to frontend)
    if status["warning_triggered"]:
        await websocket_manager.send_event(
            session_id,
            {
                "type": "context_warning",
                "fill_percentage": status["current_fill_percentage"],
                "total_tokens": status["total_tokens"],
                "context_limit": status["context_limit"],
            },
        )

    # Handle auto-summarization (inject summary message)
    if status["summary_created"]:
        summary_msg = await create_summary_message(status["summary_text"])
        await chat_history.add_message(
            sender="system",
            text=summary_msg["text"],
            message_type="context_summary",
            raw_data=summary_msg["metadata"],
            session_id=session_id,
        )

        # Inform user
        await websocket_manager.send_event(
            session_id,
            {
                "type": "context_compressed",
                "summary": status["summary_text"],
            },
        )

    return response
```

### 3. LLC Agent Support

For long-running agents, compress between tool call batches:

```python
from chat_history.overflow_integration import handle_message_completion

async def llc_heartbeat_loop(agent_id: str, session_id: str):
    while has_work:
        # Execute tool calls
        response = await execute_tool_batch()

        # Check overflow after each batch
        status = await handle_message_completion(
            session_id=session_id,
            model_name=agent_config.model,
            llm_response=response,
            messages=get_full_history(session_id),
            mode="auto",  # Always auto-compress for agents
        )

        if status["summary_created"]:
            logger.info("LLC agent %s: context compressed", agent_id)
            # Original history preserved in DB, working context now compressed
```

## API Reference

### `handle_message_completion()`

Main integration point. Call after every LLM completion.

**Parameters:**
- `session_id` (str): Chat session ID
- `model_name` (str): Active model name
- `llm_response` (LLMResponse): Response object with `usage` field
- `messages` (List[Dict], optional): Full message history
- `mode` (str, optional): Override default mode

**Returns:**
- `warning_triggered` (bool): True if >80% full
- `summary_created` (bool): True if auto-compressed
- `summary_text` (str): Summary content if created
- `current_fill_percentage` (float): 0-1 context fill
- `total_tokens` (int): Cumulative tokens
- `context_limit` (int): Model context window

### `create_summary_message()`

Format summary for injection into chat history.

**Parameters:**
- `summary_text` (str): Generated summary

**Returns:**
- Message dict compatible with `ChatHistoryManager.add_message()`

### `get_overflow_protection()`

Get singleton protection instance (advanced usage).

**Returns:**
- `ContextOverflowProtection` instance

### `set_protection_mode(mode: str)`

Change protection mode at runtime.

**Parameters:**
- `mode` (str): "auto", "warn_only", or "disabled"

## Testing

Run tests:

```bash
pytest autobot-backend/chat_history/context_overflow_test.py -v
```

## Acceptance Criteria Mapping

- ✅ Token count tracked per message (SessionTokenTracker)
- ✅ Warning at 80% (ContextOverflowProtection.warning_threshold)
- ✅ Auto-summarize at 90% (ContextOverflowProtection.compress_threshold)
- ✅ Summary as system message (create_summary_message)
- ✅ Original history preserved (summarization doesn't modify DB records)
- ✅ LLC agent support (handle_message_completion in heartbeat loop)

## Future Enhancements

- Frontend UI for context fill indicator (delegated to frontend team)
- User preferences for protection modes (settings endpoint)
- Configurable thresholds per model (context_windows.yaml)
- Summary quality improvements (fine-tuned summarization prompts)
