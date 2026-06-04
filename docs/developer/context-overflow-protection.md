---
tags: [type/reference, status/current, component/backend]
date: 2026-06-04
issue: 9043
---

# Context Overflow Protection

Automatically monitors token usage and prevents conversations from exceeding model context limits.

**Module:** `chat_history.overflow_integration`

---

## Modes

| Mode | Behaviour |
|---|---|
| `auto` | Warns at 80%, auto-summarises at 90% |
| `warn_only` | Warns at 80%, no auto-summarisation |
| `disabled` | No protection |

Set the default via environment variable:

```bash
export AUTOBOT_CONTEXT_OVERFLOW_MODE=auto
```

---

## Integration in Chat Endpoints

Call `handle_message_completion` after every LLM response:

```python
from chat_history.overflow_integration import (
    handle_message_completion,
    create_summary_message,
)

async def handle_chat_completion(session_id: str, model: str, messages: list[dict]):
    response = await llm_gateway.chat_completion(messages=messages, model=model)

    status = await handle_message_completion(
        session_id=session_id,
        model_name=model,
        llm_response=response,
        messages=messages,
    )

    if status["warning_triggered"]:
        await websocket_manager.send_event(session_id, {
            "type": "context_warning",
            "fill_percentage": status["current_fill_percentage"],
            "total_tokens": status["total_tokens"],
            "context_limit": status["context_limit"],
        })

    if status["summary_created"]:
        summary_msg = await create_summary_message(status["summary_text"])
        await chat_history.add_message(
            sender="system",
            text=summary_msg["text"],
            message_type="context_summary",
            raw_data=summary_msg["metadata"],
            session_id=session_id,
        )
        await websocket_manager.send_event(session_id, {
            "type": "context_compressed",
            "summary": status["summary_text"],
        })

    return response
```

---

## LLC Agent Support

Compress between tool-call batches:

```python
from chat_history.overflow_integration import handle_message_completion

async def llc_heartbeat_loop(agent_id: str, session_id: str):
    while has_work:
        response = await execute_tool_batch()

        status = await handle_message_completion(
            session_id=session_id,
            model_name=agent_config.model,
            llm_response=response,
            messages=get_full_history(session_id),
            mode="auto",  # always auto-compress for agents
        )

        if status["summary_created"]:
            logger.info("LLC agent %s: context compressed", agent_id)
```

---

## API

### `handle_message_completion(session_id, model_name, llm_response, messages=None, mode=None)`

Main integration point. Call after every LLM completion.

**Returns:**

| Key | Type | Description |
|---|---|---|
| `warning_triggered` | bool | True if > 80% full |
| `summary_created` | bool | True if auto-compressed |
| `summary_text` | str | Summary content if created |
| `current_fill_percentage` | float | 0–1 context fill |
| `total_tokens` | int | Cumulative tokens used |
| `context_limit` | int | Model context window size |

### `create_summary_message(summary_text)`

Format a summary for injection into chat history. Returns a message dict compatible with `ChatHistoryManager.add_message()`.

### `get_overflow_protection()`

Return the singleton `ContextOverflowProtection` instance (advanced use).

### `set_protection_mode(mode: str)`

Change protection mode at runtime. Accepts `"auto"`, `"warn_only"`, or `"disabled"`.

---

## Tests

```bash
pytest autobot-backend/chat_history/context_overflow_test.py -v
```
