# Knowledge Browser Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge `/knowledge/categories`, `/knowledge/documents`, `/knowledge/search` into one unified explorer at `/knowledge/browser` (search bar on top, tree left, list + preview/editor right), remove the three old routes, and update every in-code reference.

**Architecture:** `KnowledgeBrowser.vue` stays the canonical component and absorbs the other two views. Search logic is extracted from `KnowledgeSearch.vue` into a `useKnowledgeSearch` composable; new focused child components (`KnowledgeSearchBar`, `KnowledgeSearchResults`, `KnowledgeDocumentsBranch`) plug into the existing split-pane layout. No backend changes.

**Tech Stack:** Vue 3 `<script setup>` + TypeScript, vue-router 4, vue-i18n, Vitest, existing singleton `knowledgeRepository` and `src/composables/knowledge/` layer.

**Spec:** `docs/superpowers/specs/2026-07-10-knowledge-browser-consolidation-design.md`

## Global Constraints

- Branch target: `Dev_new_gui`; work in `.worktrees/<issue>/`; commit format `<type>(scope): <description> (#issue)`.
- NO commit trailers (no Co-Authored-By / Generated-with) — mrveiss is sole author.
- No `Enhanced/Unified/Consolidated/V2` names anywhere.
- No hardcoded UI strings — every new string gets a key in ALL 11 locales: `src/i18n/locales/{ar,de,en,es,fa,fr,he,lv,pl,pt,ur}.json`.
- No `console.*` — use `createLogger('Name')` from `@/utils/debugUtils`.
- Never instantiate a second `KnowledgeRepository` — import the `knowledgeRepository` singleton.
- Functions ≤30 lines.
- All commands below run from `autobot-frontend/` inside the worktree.
- Type check: `npx vue-tsc --noEmit -p tsconfig.app.json`. Tests: `npx vitest run <file>`. Lint gate is `--max-warnings 0`.
- Replace `#11526` in commit messages with the umbrella issue number (created before implementation starts).

## Reference inventory (verified 2026-07-10)

Every reference to the three old routes that must change:

| Location | Current | New |
|---|---|---|
| `src/router/index.ts:150-153` | `/knowledge` default redirect → `/knowledge/search` | → `/knowledge/browser` |
| `src/router/index.ts:155-163` | `knowledge-search` route | DELETE |
| `src/router/index.ts:164-186` | `knowledge-documents` route + `document-detail` child | DELETE |
| `src/router/index.ts:219-227` | `knowledge-categories` route | becomes `path: 'browser'`, `name: 'knowledge-browser'` |
| `src/router/index.ts:319-332` | `manpages` + `system-knowledge` redirects → `/knowledge/categories?view=system` | → `/knowledge/browser?view=system` |
| `src/router/index.ts:333-340` | `browser/user`, `browser/autobot` redirects → `/knowledge/categories` | → `/knowledge/browser` |
| `src/router/index.ts:822-829` | legacy `/documents` → `/knowledge/documents`; `/documents/:docId` → `/knowledge/documents/:docId` | → `/knowledge/browser`; → `{ path: '/knowledge/browser', query: { doc: docId } }` |
| `src/views/KnowledgeView.vue:44-54` | sidebar Search entry | DELETE |
| `src/views/KnowledgeView.vue:56-67` | sidebar AI Documents entry | DELETE |
| `src/views/KnowledgeView.vue:130-140` | sidebar Categories entry | becomes single Browser entry |
| `src/composables/chat/useEntityAnchors.ts:74` | `{ name: 'document-detail', params: { docId: anchor.id } }` | `{ name: 'knowledge-browser', query: { doc: anchor.id } }` |
| `src/composables/chat/__tests__/useEntityAnchors.test.ts:51,118` | expects `document-detail` | expects `knowledge-browser` + query |
| `src/components/knowledge/KnowledgeCategories.vue:266-270` | `_browseCategory` pushes `/knowledge/search?category=` | `/knowledge/browser?category=` |
| `src/config/routes.ts:41` | `redirectTo: '/knowledge/search'` | `'/knowledge/browser'` |
| `src/config/routes.ts:45-58` | `knowledge-search` + `knowledge-categories` child entries | one `knowledge-browser` entry |
| `src/components/knowledge/KnowledgeManager.vue:32-33,62-63,74` | imports `KnowledgeSearch.vue` for `search` tab, falls back to it | point `search` tab at `KnowledgeBrowser.vue` |
| `src/components/knowledge/index.ts:39` | `export { default as KnowledgeSearch }` | DELETE line |
| `src/components/knowledge/KnowledgeSearch.stories.ts` | stories for deleted component | DELETE file |

NOT route references — do NOT touch: backend API paths (`/api/knowledge/search*`, `/knowledge/search/scoped`, `chat-knowledge/search`) in `useApi.ts`, `api.ts`, `useKnowledgeCollaboration.ts`, `service-worker.test.ts`, `types/generated/api.ts`.

Pre-existing bug fixed in-scope (CLAUDE.md Rule 6): the `?view=system` query set by the `manpages`/`system-knowledge` redirects is read by nothing — `KnowledgeBrowser.vue` only honors the `preselectedCategory` prop, which no router entry passes. Task 4 wires `?view=system` → `selectedMainCategory = 'system-knowledge'`.

---

### Task 0: Worktree + spec commit

**Files:**
- Create: `.worktrees/issue-11526/` (worktree), branch `issue-11526`
- Commit: both spec files + this plan

- [ ] **Step 1: Create worktree**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI
git worktree add .worktrees/issue-11526 -b issue-11526 origin/Dev_new_gui
git -C .worktrees/issue-11526 branch --unset-upstream
```

- [ ] **Step 2: Copy spec + plan into the worktree and commit**

```bash
mkdir -p .worktrees/issue-11526/docs/superpowers/specs .worktrees/issue-11526/docs/superpowers/plans
cp docs/superpowers/specs/2026-07-10-knowledge-browser-consolidation-design.md .worktrees/issue-11526/docs/superpowers/specs/
cp docs/superpowers/plans/2026-07-10-knowledge-browser-consolidation.md .worktrees/issue-11526/docs/superpowers/plans/
git -C .worktrees/issue-11526 add docs/superpowers
git -C .worktrees/issue-11526 commit -m "docs(knowledge): browser consolidation spec + plan (#11526)"
```

---

### Task 1: Extract `useKnowledgeSearch` composable

Pure logic move from `KnowledgeSearch.vue` script (lines 242-487) into a reusable composable. The category filter becomes an injected `Ref` (the browser's selected tree category will drive it) instead of the local dropdown state.

**Files:**
- Create: `src/composables/knowledge/useKnowledgeSearch.ts`
- Test: `src/composables/__tests__/useKnowledgeSearch.test.ts`

**Interfaces:**
- Consumes: `knowledgeRepository` singleton (`ragSearch`, `searchKnowledge`), types `RagSearchResponse`, `SearchResult`.
- Produces: `useKnowledgeSearch(selectedCategory: Ref<string | null>)` returning `{ searchQuery, searchResults, ragResponse, ragError, isSearching, searchPerformed, lastSearchQuery, useRagSearch, selectedAccessLevel, ragOptions, handleSearch, clearResults, clearAccessLevelFilter, toggleAccessLevel }`. Tasks 2 and 4 rely on these exact names.

- [ ] **Step 1: Write the failing test**

Create `src/composables/__tests__/useKnowledgeSearch.test.ts` (mock pattern follows `useKnowledgeCategories.test.ts` in the same directory):

```typescript
// Copyright (c) 2026 mrveiss
// Unit tests for useKnowledgeSearch (extracted from KnowledgeSearch.vue)
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const ragSearch = vi.fn()
const searchKnowledge = vi.fn()
vi.mock('@/models/repositories', () => ({
  knowledgeRepository: { ragSearch: (...a: unknown[]) => ragSearch(...a), searchKnowledge: (...a: unknown[]) => searchKnowledge(...a) },
}))

import { useKnowledgeSearch } from '../knowledge/useKnowledgeSearch'

describe('useKnowledgeSearch', () => {
  beforeEach(() => { ragSearch.mockReset(); searchKnowledge.mockReset() })

  it('traditional search passes the injected category as a filter', async () => {
    searchKnowledge.mockResolvedValue([{ document: { id: '1' } }])
    const category = ref<string | null>('linux')
    const s = useKnowledgeSearch(category)
    s.searchQuery.value = 'grep'
    await s.handleSearch()
    expect(searchKnowledge).toHaveBeenCalledWith(expect.objectContaining({
      query: 'grep', use_rag: false, filters: { categories: ['linux'] },
    }))
    expect(s.searchResults.value).toHaveLength(1)
    expect(s.searchPerformed.value).toBe(true)
    expect(s.lastSearchQuery.value).toBe('grep')
  })

  it('RAG search failure falls back to traditional search and records ragError', async () => {
    ragSearch.mockRejectedValue(new Error('rag down'))
    searchKnowledge.mockResolvedValue([])
    const s = useKnowledgeSearch(ref(null))
    s.useRagSearch.value = true
    s.searchQuery.value = 'x'
    await s.handleSearch()
    expect(s.ragError.value).toBe('rag down')
    expect(searchKnowledge).toHaveBeenCalled()
  })

  it('access-level filter is applied client-side', async () => {
    searchKnowledge.mockResolvedValue([
      { document: { id: '1', access_level: 'system' } },
      { document: { id: '2', access_level: 'user' } },
    ])
    const s = useKnowledgeSearch(ref(null))
    s.selectedAccessLevel.value = 'system'
    s.searchQuery.value = 'x'
    await s.handleSearch()
    expect(s.searchResults.value.map(r => r.document?.id)).toEqual(['1'])
  })

  it('clearResults resets search state', async () => {
    searchKnowledge.mockResolvedValue([{ document: { id: '1' } }])
    const s = useKnowledgeSearch(ref(null))
    s.searchQuery.value = 'x'
    await s.handleSearch()
    s.clearResults()
    expect(s.searchResults.value).toEqual([])
    expect(s.searchPerformed.value).toBe(false)
    expect(s.ragResponse.value).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/composables/__tests__/useKnowledgeSearch.test.ts`
Expected: FAIL — cannot resolve `../knowledge/useKnowledgeSearch`.

- [ ] **Step 3: Create the composable**

Create `src/composables/knowledge/useKnowledgeSearch.ts`. Move the following from `src/components/knowledge/KnowledgeSearch.vue` **verbatim unless noted**: state refs (lines 267-296), `AccessLevelDoc` interface (300-303), `buildCategoryFilter` (352-357), `handleSearch` (360-450), `clearAccessLevelFilter` (462-468), `clearResults` (482-487). Changes from the source:
- `selectedCategory` is the injected `Ref<string | null>` parameter, not a local ref (drop the dropdown-specific `categories`/`loadingCategories`/`categoriesError`/`loadCategories`/`clearCategoryFilter` code — the tree replaces the dropdown).
- Add `toggleAccessLevel(level: string)` (the debounce wrapper stays in the bar component; this is the plain toggle):

```typescript
// Copyright (c) 2026 mrveiss
/**
 * useKnowledgeSearch — search state + execution for the knowledge browser.
 * Extracted from KnowledgeSearch.vue during the /knowledge/browser
 * consolidation. The category scope is injected (driven by the browser's
 * selected tree category) rather than owned here.
 */
import { ref, type Ref } from 'vue'
import { knowledgeRepository, type RagSearchResponse } from '@/models/repositories'
import type { SearchResult } from '@/stores/useKnowledgeStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeSearch')

interface AccessLevelDoc {
  access_level?: string
  metadata?: { access_level?: string }
}

export function useKnowledgeSearch(selectedCategory: Ref<string | null>) {
  const searchQuery = ref('')
  const searchResults = ref<SearchResult[]>([])
  const ragResponse = ref<RagSearchResponse | null>(null)
  const ragError = ref<string | null>(null)
  const isSearching = ref(false)
  const searchPerformed = ref(false)
  const lastSearchQuery = ref('')
  const useRagSearch = ref(false)
  const selectedAccessLevel = ref<string>('')
  const ragOptions = ref({ reformulateQuery: true, enableReranking: true, limit: 10 })

  const buildCategoryFilter = () =>
    selectedCategory.value ? { categories: [selectedCategory.value] } : undefined

  const matchesAccessLevel = (r: SearchResult) => {
    const doc = r.document as AccessLevelDoc | undefined
    return doc?.access_level === selectedAccessLevel.value ||
      doc?.metadata?.access_level === selectedAccessLevel.value
  }

  // handleSearch: body moved verbatim from KnowledgeSearch.vue lines 360-450,
  // with the two inline access-level filter blocks replaced by
  // `results = results.filter(matchesAccessLevel)` and the RAG client-side
  // category filter reading `selectedCategory.value` (unchanged semantics).
  const handleSearch = async () => { /* moved body */ }

  const toggleAccessLevel = async (level: string) => {
    selectedAccessLevel.value = selectedAccessLevel.value === level ? '' : level
    if (searchPerformed.value && searchQuery.value.trim()) await handleSearch()
  }

  const clearAccessLevelFilter = async () => {
    selectedAccessLevel.value = ''
    if (searchPerformed.value && searchQuery.value.trim()) await handleSearch()
  }

  const clearResults = () => {
    searchResults.value = []
    searchPerformed.value = false
    ragResponse.value = null
    ragError.value = null
  }

  return {
    searchQuery, searchResults, ragResponse, ragError, isSearching,
    searchPerformed, lastSearchQuery, useRagSearch, selectedAccessLevel,
    ragOptions, handleSearch, clearResults, clearAccessLevelFilter,
    toggleAccessLevel,
  }
}
```

(The `/* moved body */` placeholder above is for plan brevity ONLY — the implementer moves the real 90-line body from `KnowledgeSearch.vue:360-450`; nothing is left unimplemented.)

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/composables/__tests__/useKnowledgeSearch.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/composables/knowledge/useKnowledgeSearch.ts src/composables/__tests__/useKnowledgeSearch.test.ts
git commit -m "refactor(knowledge): extract useKnowledgeSearch composable from KnowledgeSearch.vue (#11526)"
```

---

### Task 2: `KnowledgeSearchBar.vue` + `KnowledgeSearchResults.vue`

Presentational children. The bar owns the query input, RAG toggle, and a collapsible Filters row (access-level chips + RAG options). The results component renders RAG synthesis + `KBSearchResultPanel` + empty/error states (template moved from `KnowledgeSearch.vue:168-238`).

**Files:**
- Create: `src/components/knowledge/KnowledgeSearchBar.vue`
- Create: `src/components/knowledge/KnowledgeSearchResults.vue`

**Interfaces:**
- `KnowledgeSearchBar` — props: `search: ReturnType<typeof useKnowledgeSearch>` (the whole composable object, passed by the browser so bar and results share state). Emits: `search` (after Enter/click, so the browser can also react), `clear`.
- `KnowledgeSearchResults` — props: `search: ReturnType<typeof useKnowledgeSearch>`. Emits: `close` (user dismissed results), `select` (result: `SearchResult`).

- [ ] **Step 1: Create `KnowledgeSearchBar.vue`**

Template: search input + mode toggle moved from `KnowledgeSearch.vue:8-34` and `110-166` (input wrapper, RAG options), access-level chips from lines `82-108`; the standalone category `<select>` (lines 36-80) is NOT carried over. Wrap chips + RAG options in a `<details class="filters-row">` disclosure with summary `{{ $t('knowledge.browser.filters') }}` (new key). Script:

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import type { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'

const props = defineProps<{ search: ReturnType<typeof useKnowledgeSearch> }>()
const emit = defineEmits<{ (e: 'search'): void; (e: 'clear'): void }>()
const { t } = useI18n()

const accessLevels = computed(() => [
  { value: 'autobot', label: t('knowledge.search.accessPlatform'), icon: 'fas fa-robot' },
  { value: 'general', label: t('knowledge.search.accessPublic'), icon: 'fas fa-globe' },
  { value: 'system', label: t('knowledge.search.accessSystem'), icon: 'fas fa-cog' },
  { value: 'user', label: t('knowledge.search.accessUser'), icon: 'fas fa-user' },
])

async function onSearch() {
  await props.search.handleSearch()
  emit('search')
}

function onClear() {
  props.search.searchQuery.value = ''
  props.search.clearResults()
  emit('clear')
}
</script>
```

All bindings reference `search.searchQuery.value` etc. through the prop; input `@keyup.enter="onSearch"`, a clear (×) button visible when `search.searchPerformed.value` calls `onClear()`. Styles: move the relevant scoped blocks from `KnowledgeSearch.vue` (`.search-mode-toggle` through `.search-button`, access-level chip styles).

- [ ] **Step 2: Create `KnowledgeSearchResults.vue`**

Move template from `KnowledgeSearch.vue:169-238` verbatim, replacing state refs with `search.` prop access, `KBSearchResultPanel` keeps `:repository="knowledgeRepository"` (import singleton). `@select="e => emit('select', e)"`, `@close="emit('close')"`. Move the matching scoped styles (`.rag-synthesis` … `.fallback-note`). Script is ~15 lines: props/emits + `getConfidenceBadgeClass` moved from `KnowledgeSearch.vue:470-474`.

- [ ] **Step 3: Type check**

Run: `npx vue-tsc --noEmit -p tsconfig.app.json`
Expected: clean (components not yet mounted anywhere).

- [ ] **Step 4: Commit**

```bash
git add src/components/knowledge/KnowledgeSearchBar.vue src/components/knowledge/KnowledgeSearchResults.vue
git commit -m "feat(knowledge): search bar + results components for unified browser (#11526)"
```

---

### Task 3: `KnowledgeDocumentsBranch.vue`

AI Documents as a tree-pane section: paginated doc list + delete flow + collapsed transcriber group. Logic moved from `DocumentsView.vue`.

**Files:**
- Create: `src/components/knowledge/KnowledgeDocumentsBranch.vue`

**Interfaces:**
- Consumes: `useAIDocument()` (`fetchDocuments(limit, offset)`, `deleteDocument(id)`, `documents`, `total`, `isLoading`, `hasDocuments`, `error`), `useTranscriberApi().listProjects()`.
- Produces — emits: `select` (docId: string), `deleted` (docId: string), `error` (message: string). Task 4 relies on these names.
- Props: `selectedDocId: string | null`.

- [ ] **Step 1: Create the component**

Move from `src/views/DocumentsView.vue`:
- Script blocks: pagination state + `loadPage/prevPage/nextPage` (lines 194-247), delete flow incl. focus trap/restore/scroll-lock wiring (lines 199-207, 253-270), transcriber fetch (lines 191-192, 216-220), `formatDate` + `showError` (lines 292-312) — `showError` becomes `emit('error', msg)` (toast stays in the browser, single surface).
- Template: collapsible wrapper `<details class="docs-branch" open>` with summary `{{ $t('knowledge.views.documents') }}`; inside it the doc list + pagination (lines 35-86), the delete modal (lines 117-148), and the transcriber mini-grid (lines 156-171) inside its own nested `<details>` (collapsed by default) with summary `{{ $t('documents.transcriberProjects') }}`.
- `selectDocument(id)` becomes `emit('select', id)`; `executeDelete` emits `deleted` after success.
- Move list/modal scoped styles from `DocumentsView.vue` (`.document-list` … `.modal-actions`, `.transcriber-section` block), dropping the page-level layout styles (`.documents-view`, `.documents-sidebar`, `.documents-main`, `.no-selection*`).

- [ ] **Step 2: Type check**

Run: `npx vue-tsc --noEmit -p tsconfig.app.json`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add src/components/knowledge/KnowledgeDocumentsBranch.vue
git commit -m "feat(knowledge): AI documents branch component for unified browser (#11526)"
```

---

### Task 4: Integrate into `KnowledgeBrowser.vue`

**Files:**
- Modify: `src/components/knowledge/KnowledgeBrowser.vue`

**Interfaces:**
- Consumes: everything produced by Tasks 1-3.
- Produces: the finished `/knowledge/browser` view; honors `?q=`, `?doc=`, `?view=system`, `?category=` query params.

- [ ] **Step 1: Script additions**

```typescript
import { useRoute } from 'vue-router'
import { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'
import KnowledgeSearchBar from './KnowledgeSearchBar.vue'
import KnowledgeSearchResults from './KnowledgeSearchResults.vue'
import KnowledgeDocumentsBranch from './KnowledgeDocumentsBranch.vue'
import AIDocumentEditor from '@/components/documents/AIDocumentEditor.vue'

const route = useRoute()
const search = useKnowledgeSearch(selectedCategory)   // existing ref, line 300
const selectedDocId = ref<string | null>(null)
const docBranchError = ref<string | null>(null)

// Right-pane priority: document editor > search results > content viewer
const rightPane = computed<'editor' | 'results' | 'viewer'>(() => {
  if (selectedDocId.value) return 'editor'
  if (search.searchPerformed.value) return 'results'
  return 'viewer'
})

function onDocSelect(id: string) {
  selectedDocId.value = id
  clearSelection()               // existing fn — a doc replaces a selected fact
}

function onDocDeleted(id: string) {
  if (selectedDocId.value === id) selectedDocId.value = null
}
```

In the existing `selectNode` (line 786), add `selectedDocId.value = null` before `selectedFile.value = node` so picking a fact leaves the editor. In `onMounted` (line 1088), append deep-link handling:

```typescript
// Deep links: ?doc= opens the editor, ?q= runs a search, ?view=system
// pre-selects the system main category (fixes the previously inert
// query set by the legacy manpages/system-knowledge redirects).
if (typeof route.query.doc === 'string') selectedDocId.value = route.query.doc
if (typeof route.query.category === 'string') selectedCategory.value = route.query.category
if (route.query.view === 'system') selectedMainCategory.value = 'system-knowledge'
if (typeof route.query.q === 'string' && route.query.q.trim()) {
  search.searchQuery.value = route.query.q
  search.handleSearch()
}
```

- [ ] **Step 2: Template changes**

At the top of `.knowledge-file-browser` (before `KnowledgeMainCategories`, line 4) insert:

```html
<KnowledgeSearchBar :search="search" @clear="/* nothing extra */" />
```

In the tree pane `.tree-container` (after the `TreeNodeComponent` loop + load-more block, line ~173) insert:

```html
<KnowledgeDocumentsBranch
  :selected-doc-id="selectedDocId"
  @select="onDocSelect"
  @deleted="onDocDeleted"
  @error="docBranchError = $event"
/>
```

Replace the right pane (lines 177-184) with the three-state switch:

```html
<AIDocumentEditor
  v-if="rightPane === 'editor'"
  :doc-id="selectedDocId!"
  class="content-pane"
  @error="docBranchError = $event"
/>
<KnowledgeSearchResults
  v-else-if="rightPane === 'results'"
  :search="search"
  class="content-pane"
  @close="search.clearResults()"
/>
<KnowledgeContentViewer
  v-else
  :selected-file="selectedFile"
  :content="fileContent"
  :is-loading="isLoadingContent"
  :error="contentError instanceof Error ? contentError.message : (contentError as string | null)"
  @close="clearSelection"
/>
```

Add an error toast near the root (pattern from `DocumentsView.vue:151-153`): `<div v-if="docBranchError" class="error-toast" role="alert">{{ docBranchError }}</div>` with a 5s auto-clear watcher; move the `.error-toast` style from `DocumentsView.vue`.

- [ ] **Step 3: Manual verify in dev server**

Run: `npm run dev` — open `/knowledge/categories` (old route still live until Task 5). Verify: search bar renders; typing a query + Enter shows results in right pane; clearing returns to viewer; AI Documents branch lists docs; selecting one opens the editor; delete works.

- [ ] **Step 4: Type check + commit**

```bash
npx vue-tsc --noEmit -p tsconfig.app.json
git add src/components/knowledge/KnowledgeBrowser.vue
git commit -m "feat(knowledge): unify search, documents and browsing in KnowledgeBrowser (#11526)"
```

---

### Task 5: Routing, navigation, reference sweep, deletions

**Files:**
- Modify: `src/router/index.ts`, `src/views/KnowledgeView.vue`, `src/config/routes.ts`, `src/composables/chat/useEntityAnchors.ts`, `src/composables/chat/__tests__/useEntityAnchors.test.ts`, `src/components/knowledge/KnowledgeCategories.vue`, `src/components/knowledge/KnowledgeManager.vue`, `src/components/knowledge/index.ts`
- Delete: `src/components/knowledge/KnowledgeSearch.vue`, `src/components/knowledge/KnowledgeSearch.stories.ts`, `src/views/DocumentsView.vue`

- [ ] **Step 1: Router changes** — apply every `src/router/index.ts` row from the Reference inventory table. The new canonical entry (replacing lines 219-227):

```typescript
{
  path: 'browser',
  name: 'knowledge-browser',
  component: () => import('@/components/knowledge/KnowledgeBrowser.vue'),
  meta: {
    title: 'Knowledge Browser',
    parent: 'knowledge'
  }
},
```

Legacy document deep-link redirect (line 826-829) becomes:

```typescript
{
  path: '/documents/:docId',
  redirect: (to) => ({ path: '/knowledge/browser', query: { doc: String(to.params.docId) } }),
},
```

- [ ] **Step 2: Sidebar** — in `src/views/KnowledgeView.vue` delete the Search (44-54) and AI Documents (56-67) entries; replace the Categories entry (130-140) with:

```html
<router-link
  to="/knowledge/browser"
  class="category-item"
  :class="{ active: $route.name === 'knowledge-browser' }"
  :aria-label="$t('knowledge.views.browserAriaLabel')"
>
  <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
  </svg>
  <span>{{ $t('knowledge.views.browser') }}</span>
</router-link>
```

- [ ] **Step 3: Remaining sweep rows** — `config/routes.ts` (one `knowledge-browser` child replaces the two), `useEntityAnchors.ts:74` + its test, `KnowledgeCategories.vue:266-270`, `KnowledgeManager.vue` (import `KnowledgeBrowser` instead of `KnowledgeSearch`, map both `search:` and the `||` fallback to it), `components/knowledge/index.ts:39` (drop export).

- [ ] **Step 4: Delete absorbed files**

```bash
git rm src/components/knowledge/KnowledgeSearch.vue src/components/knowledge/KnowledgeSearch.stories.ts src/views/DocumentsView.vue
```

- [ ] **Step 5: Grep gate**

```bash
grep -rn --include='*.vue' --include='*.ts' -E "knowledge/(search|documents|categories)['\"]|knowledge-search|knowledge-documents|knowledge-categories|document-detail" src/ | grep -vE "api/|scoped|accessible-scopes|chat-knowledge|generated"
```
Expected: zero output.

- [ ] **Step 6: Tests + type check + commit**

```bash
npx vitest run src/composables/chat/__tests__/useEntityAnchors.test.ts
npx vue-tsc --noEmit -p tsconfig.app.json
git add -A src/
git commit -m "feat(knowledge): route /knowledge/browser replaces categories/documents/search (#11526)"
```

---

### Task 6: i18n keys — all 11 locales

**Files:**
- Modify: `src/i18n/locales/{ar,de,en,es,fa,fr,he,lv,pl,pt,ur}.json`

New keys (English values; translate for each locale — follow neighboring keys' style):
- `knowledge.views.browser` = "Browser"
- `knowledge.views.browserAriaLabel` = "Browse, search and edit knowledge documents"
- `knowledge.browser.filters` = "Filters"
- `documents.*` keys already exist (list reused verbatim) — verify none were dropped by the DocumentsView deletion (they live in the locale files, not the component).

- [ ] **Step 1: Add the 3 keys to `en.json`** inside the existing `knowledge.views` / `knowledge.browser` objects.
- [ ] **Step 2: Add translated keys to the other 10 locales.**
- [ ] **Step 3: Verify** — `npx vitest run src/i18n/__tests__` (locale-completeness tests if present) and `npx vue-tsc --noEmit -p tsconfig.app.json`.
- [ ] **Step 4: Commit**

```bash
git add src/i18n/locales/
git commit -m "feat(i18n): knowledge browser consolidation keys x11 locales (#11526)"
```

---

### Task 7: Full verification + PR

- [ ] **Step 1: Full gates**

```bash
npx vue-tsc --noEmit -p tsconfig.app.json     # clean
npx vitest run                                 # all green
npm run lint -- --max-warnings 0               # clean
```

- [ ] **Step 2: Manual smoke** — dev server: `/knowledge` redirects to `/knowledge/browser`; `?q=test` auto-searches; `?doc=<id>` opens editor; `?view=system` pre-selects System Knowledge; old paths 404 (removed).
- [ ] **Step 3: Re-run the Task 5 grep gate** (zero matches).
- [ ] **Step 4: PR** targeting `Dev_new_gui`, headings `Thinking Path / What Changed / Verification / Model Used`, body `Closes #11526`. Check open-PR count ≤5 first.
- [ ] **Step 5: File discovery issue** — `KnowledgeManager.vue` is exported but mounted nowhere (unwired legacy tabbed manager duplicating the Knowledge section); needs wire-in-or-remove decision. Evidence: no imports outside `index.ts`/stories.

## Self-review notes

- Spec coverage: route/nav (T5), search bar + tree-scoped filter (T1/T2/T4), AI-docs branch + editor pane (T3/T4), transcriber group (T3), deep links + inert `?view=system` fix (T4/T5), deletions (T5), i18n ×11 (T6), gates (T7). Feature-parity checklist maps: search features → T1/T2; browse features → untouched existing code; documents features → T3.
- Type consistency: `useKnowledgeSearch` return names match usage in T2 (`search.` prop) and T4 (`search.searchPerformed.value`); emits `select/deleted/error` consistent between T3 definition and T4 handlers.
- Known judgment call: bar/results share the composable object via prop rather than provide/inject — explicit and typed.
