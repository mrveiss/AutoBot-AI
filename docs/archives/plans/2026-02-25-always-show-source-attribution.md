# Always-Visible Source Attribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Every assistant message shows a collapsible Sources panel so users always know what information is based on — KB documents, LLM training data, or live web results.

**Architecture:** Add a `_build_source_list()` helper to `chat_workflow/manager.py` that always returns ≥1 source entry; the three existing `"citations": rag_citations if used_knowledge else []` lines call it instead. Then remove the `used_knowledge &&` gate from two frontend components and extend `CitationsDisplay.vue` to render icons, reliability badges, and clickable web URLs.

**Tech Stack:** Python (chat_workflow/manager.py), Vue 3 + TypeScript (CitationsDisplay.vue, MessageItem.vue, ChatMessages.vue)

**GitHub Issue:** #1186

---

### Task 1: Add `_build_source_list()` to `chat_workflow/manager.py`

**Files:**
- Modify: `autobot-backend/chat_workflow/manager.py:263–312`

**Context:**
Three methods currently set `"citations": rag_citations if used_knowledge else []`:
- `_build_chunk_message` (line 310) — old-style chunk builder
- `_build_stream_chunk_message` (line 461) — new-style stream chunk builder
- `_init_streaming_message` (line 501) — stream init

The class is `ChatWorkflowManager`. Add the new helper as an instance method of that class.

**Step 1: Add the helper method**

Insert after line 312 (after `_build_chunk_message`) in `manager.py`:

```python
def _build_source_list(
    self,
    used_knowledge: bool,
    rag_citations: List[Dict[str, Any]],
    selected_model: str,
) -> List[Dict[str, Any]]:
    """Build citation list always containing ≥1 entry. Issue #1186.

    When KB was used, KB citations come first.
    LLM training data entry is always appended last so users
    always see what the response is based on.
    """
    sources: List[Dict[str, Any]] = []
    if used_knowledge and rag_citations:
        for c in rag_citations:
            sources.append({**c, "type": "knowledge_base", "reliability": "high"})
    sources.append(
        {
            "type": "llm_training",
            "title": "AI Training Data",
            "model": selected_model,
            "reliability": "medium",
            "source": "LLM",
            "content": "Response generated using LLM training data.",
            "score": 0.5,
        }
    )
    return sources
```

**Step 2: Replace the three `citations` assignments**

In `_build_chunk_message` (around line 310):
```python
# Before
"citations": rag_citations if used_knowledge else [],
# After
"citations": self._build_source_list(used_knowledge, rag_citations, selected_model),
```

In `_build_stream_chunk_message` (around line 461):
```python
# Before
"citations": rag_citations if used_knowledge else [],
# After
"citations": self._build_source_list(used_knowledge, rag_citations, selected_model),
```

In `_init_streaming_message` (around line 501):
```python
# Before
"citations": rag_citations if used_knowledge else [],
# After
"citations": self._build_source_list(used_knowledge, rag_citations, selected_model),
```

**Step 3: Verify function length**

```bash
cd autobot-backend
grep -n "_build_source_list" chat_workflow/manager.py
```

The helper is ~20 lines — well within the 65-line limit.

**Step 4: Run backend lint check**

```bash
cd autobot-backend
python -m flake8 chat_workflow/manager.py --max-line-length=100
```

Expected: no output (no errors).

**Step 5: Commit**

```bash
git add autobot-backend/chat_workflow/manager.py
git commit -m "feat(chat): always populate citations with _build_source_list (#1186)"
```

---

### Task 2: Extend `CitationsDisplay.vue` to render source types

**Files:**
- Modify: `autobot-frontend/src/components/chat/CitationsDisplay.vue`

**Context:**
`CitationsDisplay.vue` currently only knows how to render KB citations (content + score + file path).
It needs to handle three source types: `knowledge_base`, `llm_training`, `web`.

Each type needs a distinct icon and a reliability badge (green/amber/red).

**Step 1: Update the `Citation` interface**

Replace the existing `interface Citation` block (lines 59–65):

```typescript
interface Citation {
  id?: string
  rank?: number
  content?: string
  score?: number
  source?: string
  // New fields (Issue #1186)
  type?: 'knowledge_base' | 'llm_training' | 'web'
  reliability?: 'verified' | 'high' | 'medium' | 'low'
  title?: string
  model?: string
  url?: string
}
```

**Step 2: Add computed helpers in `<script setup>`**

After `const formatSourcePath = ...` (line 109), add:

```typescript
const sourceIcon = (citation: Citation): string => {
  switch (citation.type) {
    case 'knowledge_base': return 'fas fa-book'
    case 'llm_training':   return 'fas fa-robot'
    case 'web':            return 'fas fa-globe'
    default:               return 'fas fa-file-alt'
  }
}

const reliabilityClass = (reliability: string | undefined): string => {
  switch (reliability) {
    case 'verified':
    case 'high':   return 'reliability-high'
    case 'medium': return 'reliability-medium'
    case 'low':    return 'reliability-low'
    default:       return 'reliability-medium'
  }
}

const reliabilityLabel = (reliability: string | undefined): string => {
  if (!reliability) return 'Medium'
  return reliability.charAt(0).toUpperCase() + reliability.slice(1)
}

const citationTitle = (citation: Citation): string => {
  if (citation.title) return citation.title
  if (citation.type === 'llm_training') return 'AI Training Data'
  if (citation.type === 'web') return citation.url || 'Web Source'
  return citation.source ? formatSourcePath(citation.source) : 'Knowledge Base'
}
```

**Step 3: Update the template**

Replace the entire `<template>` block with:

```html
<template>
  <div class="knowledge-citations">
    <div class="citations-header" @click="toggleExpanded">
      <div class="citations-header-left">
        <i class="fas fa-layer-group text-autobot-primary" aria-hidden="true"></i>
        <span class="citations-label">Sources</span>
        <span class="citations-count">{{ citations.length }}</span>
      </div>
      <i
        :class="isExpanded ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"
        aria-hidden="true"
      ></i>
    </div>
    <Transition name="slide-fade">
      <div v-if="isExpanded" class="citations-list">
        <div
          v-for="(citation, idx) in citations"
          :key="citation.id || idx"
          class="citation-item"
          @click="$emit('citation-click', citation)"
        >
          <div class="citation-rank">
            <i :class="sourceIcon(citation)" aria-hidden="true"></i>
          </div>
          <div class="citation-content">
            <!-- Title or web link -->
            <div class="citation-text">
              <a
                v-if="citation.type === 'web' && citation.url"
                :href="citation.url"
                target="_blank"
                rel="noopener noreferrer"
                class="citation-link"
                @click.stop
              >{{ citationTitle(citation) }}</a>
              <span v-else>{{ citationTitle(citation) }}</span>
            </div>
            <!-- Excerpt for KB entries -->
            <div
              v-if="citation.type === 'knowledge_base' && citation.content"
              class="citation-excerpt"
            >
              {{ truncateContent(citation.content) }}
            </div>
            <!-- Model name for LLM entries -->
            <div
              v-if="citation.type === 'llm_training' && citation.model"
              class="citation-excerpt"
            >
              Model: {{ citation.model }}
            </div>
            <div class="citation-meta">
              <!-- Reliability badge -->
              <span
                class="citation-reliability"
                :class="reliabilityClass(citation.reliability)"
              >
                {{ reliabilityLabel(citation.reliability) }}
              </span>
              <!-- Score for KB entries -->
              <span
                v-if="citation.type === 'knowledge_base' && citation.score != null"
                class="citation-score"
                :class="getScoreClass(citation.score)"
              >
                <i class="fas fa-chart-line" aria-hidden="true"></i>
                {{ formatScore(citation.score) }}%
              </span>
              <!-- File path for KB entries -->
              <span
                v-if="citation.type === 'knowledge_base' && citation.source"
                class="citation-source"
              >
                <i class="fas fa-file-alt" aria-hidden="true"></i>
                {{ formatSourcePath(citation.source) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
```

**Step 4: Add reliability badge CSS**

Add after `.citation-source` block (before `/* Transition */`):

```css
.citation-link {
  color: var(--color-primary-hover);
  text-decoration: underline;
  word-break: break-all;
}

.citation-link:hover {
  color: var(--color-primary);
}

.citation-excerpt {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
  margin-bottom: var(--spacing-1-5);
}

.citation-reliability {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--spacing-1-5);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.reliability-high {
  background: rgba(34, 197, 94, 0.15);
  color: var(--chart-green);
}

.reliability-medium {
  background: rgba(251, 191, 36, 0.15);
  color: var(--color-warning);
}

.reliability-low {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-danger, #ef4444);
}
```

**Step 5: Verify no TypeScript errors**

```bash
cd autobot-frontend
npx tsc --noEmit 2>&1 | grep -i "CitationsDisplay"
```

Expected: no output.

**Step 6: Commit**

```bash
git add autobot-frontend/src/components/chat/CitationsDisplay.vue
git commit -m "feat(chat): extend CitationsDisplay for type/reliability/web (#1186)"
```

---

### Task 3: Remove `used_knowledge` gate from `MessageItem.vue`

**Files:**
- Modify: `autobot-frontend/src/components/chat/MessageItem.vue:258–264`

**Context:**
`hasCitations` computed currently reads:
```typescript
props.message.metadata?.used_knowledge &&
(props.message.metadata?.citations?.length || 0) > 0
```
Since backend now always sends ≥1 citation, we only need the length check.

**Step 1: Update `hasCitations` computed**

Replace lines 258–264:

```typescript
// Before
const hasCitations = computed(() => {
  return (
    props.message.sender === 'assistant' &&
    props.message.metadata?.used_knowledge &&
    (props.message.metadata?.citations?.length || 0) > 0
  )
})

// After
const hasCitations = computed(() => {
  return (
    props.message.sender === 'assistant' &&
    (props.message.metadata?.citations?.length || 0) > 0
  )
})
```

**Step 2: Verify TypeScript**

```bash
cd autobot-frontend
npx tsc --noEmit 2>&1 | grep -i "MessageItem"
```

Expected: no output.

**Step 3: Commit**

```bash
git add autobot-frontend/src/components/chat/MessageItem.vue
git commit -m "feat(chat): show sources panel for all assistant messages (#1186)"
```

---

### Task 4: Remove `used_knowledge` gate from `ChatMessages.vue`

**Files:**
- Modify: `autobot-frontend/src/components/chat/ChatMessages.vue:147`

**Context:**
`ChatMessages.vue` has an inline `v-if` that also gates on `used_knowledge`. It must be updated to match the new logic.

**Step 1: Find and update the v-if condition**

The line reads:
```html
v-if="message.sender === 'assistant' && message.metadata?.used_knowledge && message.metadata?.citations?.length > 0"
```

Change to:
```html
v-if="message.sender === 'assistant' && message.metadata?.citations?.length > 0"
```

**Step 2: Verify no TypeScript / template errors**

```bash
cd autobot-frontend
npx vue-tsc --noEmit 2>&1 | grep -i "ChatMessages"
```

Expected: no output.

**Step 3: Commit**

```bash
git add autobot-frontend/src/components/chat/ChatMessages.vue
git commit -m "feat(chat): remove used_knowledge gate from ChatMessages citations (#1186)"
```

---

### Task 5: Build frontend and verify

**Step 1: Build frontend**

```bash
cd autobot-frontend
npm run build 2>&1 | tail -20
```

Expected: `dist/` created, no errors.

**Step 2: Smoke test — check KB response**

Send a chat message whose answer is likely in the KB (e.g., "What is AutoBot?").
Expected: Sources panel appears with ≥1 📚 KB entry + 🤖 LLM entry.

**Step 3: Smoke test — check LLM-only response**

Send a simple conversational message (e.g., "Hi, how are you?").
Expected: Sources panel appears with 🤖 LLM entry only, reliability badge = "Medium".

**Step 4: Smoke test — check web research response**

Send a current-data query (e.g., "What is the weather in London?").
Expected: Sources panel shows 🌐 web entry with clickable URL + 🤖 LLM entry.

**Step 5: Final commit + close issue**

```bash
git add autobot-frontend/dist/
git commit -m "build(frontend): rebuild for source attribution (#1186)"
gh issue comment 1186 --body "All tasks complete. Sources panel now shows on every assistant message: KB entries (📚 High), web results (🌐 Medium, clickable URL), and LLM training data (🤖 Medium). Removed used_knowledge gate from MessageItem.vue and ChatMessages.vue. Backend always emits ≥1 citation via _build_source_list()."
gh issue close 1186
```

---

## Testing Checklist

- [ ] LLM-only response shows 🤖 Sources panel with "Medium" badge
- [ ] KB response shows 📚 entries + 🤖 LLM entry
- [ ] Web response shows 🌐 entry with link + 🤖 LLM entry
- [ ] Reliability badges: green = high, amber = medium, red = low
- [ ] Web URLs open in new tab
- [ ] Panel collapses/expands correctly
- [ ] No regression on KB citation scoring display
- [ ] Frontend build succeeds with no TypeScript errors
