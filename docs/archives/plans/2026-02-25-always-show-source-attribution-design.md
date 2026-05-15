# Design: Always-Visible Source Attribution

**Date:** 2026-02-25
**Author:** mrveiss
**Status:** Approved

## Problem

AutoBot already tracks information sources (KB entries, web research, LLM training data) in
`source_attribution.py` and in `chat_workflow/manager.py`. However, the frontend citation panel
only renders when `used_knowledge == true && citations.length > 0`. For pure LLM responses
(no KB hit, no web research), `citations` is always `[]` and `used_knowledge` is `false` —
so users see no indication of where the answer came from.

Users want to always know what any response is based on: training data, a KB document, a live
web search result, etc. — and whether that source can be trusted.

## Goal

Every assistant message shows a collapsible "Sources" panel indicating:
- Where the information came from (KB, LLM training, web)
- Which specific document/URL/model was used
- Reliability level (High / Medium / Low)

## Architecture

### Chat path (primary)

```
POST /api/chats/{chat_id}/message
  → chat_workflow/manager.py  (builds WorkflowMessage with metadata)
    → SSE stream
      → frontend ChatInterface → ChatMessages / MessageItem
```

`metadata.citations` is the existing field used to populate the panel.
Currently: `rag_citations if used_knowledge else []`
After: always a non-empty list with at least one source entry.

## Backend Changes — `chat_workflow/manager.py`

### New helper: `_build_source_list()`

Extract a helper called from all `_build_*_message` / `_build_chunk_message` methods.

```python
def _build_source_list(
    self,
    used_knowledge: bool,
    rag_citations: List[Dict],
    selected_model: str,
    research_sources: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Always return ≥1 source entry for frontend attribution panel."""
    sources = []
    if used_knowledge and rag_citations:
        for c in rag_citations:
            sources.append({**c, "type": "knowledge_base", "reliability": "high"})
    if research_sources:
        for r in research_sources:
            sources.append({
                "type": "web",
                "title": r.get("title", r.get("url", "Web")),
                "url": r.get("url"),
                "reliability": "medium",
                "source": r.get("url", ""),
            })
    sources.append({
        "type": "llm_training",
        "title": "AI Training Data",
        "model": selected_model,
        "reliability": "medium",
        "source": "LLM",
    })
    return sources
```

### Affected methods (all call `_build_source_list`)

| Method | Lines (approx) |
|--------|---------------|
| `_build_chunk_message` | ~301–312 |
| `_build_complete_message` (streaming done) | ~441–461 |
| `_build_complete_message` (non-streaming) | ~487–501 |
| `_build_non_streaming_message` | ~539–556 |
| Additional complete message builders | ~610–628 |

Change each from:
```python
"citations": rag_citations if used_knowledge else [],
```
To:
```python
"citations": self._build_source_list(used_knowledge, rag_citations, selected_model),
```

The `used_knowledge` field stays in metadata for backwards compat.

## Frontend Changes

### `MessageItem.vue` — citation panel visibility

```typescript
// Before
const showCitations = computed(() =>
  props.message.metadata?.used_knowledge &&
  (props.message.metadata?.citations?.length || 0) > 0
)

// After
const showCitations = computed(() =>
  props.message.sender === 'assistant' &&
  (props.message.metadata?.citations?.length || 0) > 0
)
```

### `ChatMessages.vue` — inline citation block condition

```html
<!-- Before -->
v-if="message.sender === 'assistant' && message.metadata?.used_knowledge && message.metadata?.citations?.length > 0"

<!-- After -->
v-if="message.sender === 'assistant' && message.metadata?.citations?.length > 0"
```

### Source panel UI updates (ChatMessages.vue + MessageItem.vue)

- Panel header: "Knowledge Sources" → "Sources"
- Per-source icon based on `type`:
  - `knowledge_base` → 📚
  - `llm_training` → 🤖
  - `web` → 🌐
- Per-source reliability badge (pill):
  - `high` / `verified` → green
  - `medium` → amber
  - `low` → red/orange
- Web sources: `title` renders as `<a>` link when `url` is present
- LLM entry: shows model name in citation-meta

### CitationsDisplay.vue — extended rendering

Update to handle the three source types (currently only renders KB shape):
- Add `type` and `reliability` fields to the `Citation` TypeScript interface
- Render icon prefix from `type`
- Render reliability badge
- Conditionally render URL link for web type

## What Does NOT Change

- `source_attribution.py` — untouched (separate path for `conversation.py` endpoint)
- `conversation.py` — untouched
- `used_knowledge` field — kept in metadata, not removed

## Source Data Shape (after)

```typescript
interface Citation {
  // existing
  id?: string
  content?: string
  score?: number
  rank?: number
  // existing KB fields
  source?: string   // file path or URL
  title?: string
  // new
  type?: 'knowledge_base' | 'llm_training' | 'web'
  reliability?: 'verified' | 'high' | 'medium' | 'low'
  model?: string    // for llm_training
  url?: string      // for web
}
```

## Testing

- Query with KB hit → panel shows KB entries + LLM entry
- Query with no KB hit (simple chat) → panel shows LLM entry only
- Query triggering web research (weather/price) → panel shows web entries + LLM entry
- Panel collapses/expands correctly
- Reliability badges render correct colours
- Web URLs open in new tab

## GitHub Issue

To be created: `feat(chat): always show source attribution for every assistant response`
