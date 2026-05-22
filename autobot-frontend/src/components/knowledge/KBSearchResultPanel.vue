<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <!-- Issue #3296: KB full-text search result viewer -->
  <div
    ref="panelRef"
    class="kb-search-result-panel"
    role="region"
    aria-label="Search results"
    @keydown="handleKeydown"
    tabindex="-1"
  >
    <!-- Panel header -->
    <div class="panel-header">
      <div class="panel-title">
        <Icon name="search" />
        <span v-if="loading">Searching…</span>
        <span v-else-if="results.length">
          {{ results.length }} result{{ results.length === 1 ? '' : 's' }} for
          <em class="query-label">"{{ query }}"</em>
        </span>
        <span v-else>No results for <em class="query-label">"{{ query }}"</em></span>
      </div>
      <button
        class="close-btn"
        aria-label="Close search results"
        @click="emit('close')"
      >
        <Icon name="times" />
      </button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="result-list">
      <div
        v-for="n in 3"
        :key="n"
        class="result-skeleton"
      >
        <div class="skeleton-title"></div>
        <div class="skeleton-meta"></div>
        <div class="skeleton-snippet"></div>
      </div>
    </div>

    <!-- Result list (left pane) + viewer (right pane) -->
    <div v-else-if="results.length" class="panel-body">
      <!-- Left: ranked result list -->
      <ul
        ref="listRef"
        class="result-list"
        role="listbox"
        aria-label="Ranked search results"
      >
        <li
          v-for="(result, index) in results"
          :key="result.document?.id || `r-${index}`"
          :class="['result-item', { selected: selectedIndex === index }]"
          role="option"
          :aria-selected="selectedIndex === index"
          :tabindex="selectedIndex === index ? 0 : -1"
          @click="selectResult(index)"
          @keydown.enter.prevent="openSelected"
        >
          <div class="result-item-header">
            <span class="result-rank">{{ index + 1 }}</span>
            <span class="result-title">
              {{ result.document?.title || 'Untitled' }}
            </span>
            <span
              class="result-score"
              :class="scoreClass(result.score)"
              :title="`Relevance: ${Math.round(result.score * 100)}%`"
            >
              {{ Math.round(result.score * 100) }}%
            </span>
            <span
              v-if="result.rerank_score != null"
              class="rerank-badge"
              :title="`Re-rank score: ${Math.round(result.rerank_score * 100)}%`"
            >
              <Icon name="brain" />
              {{ Math.round(result.rerank_score * 100) }}%
            </span>
          </div>

          <div class="result-item-meta">
            <span><Icon name="folder" /> {{ result.document?.category || 'general' }}</span>
            <span><Icon name="file-alt" /> {{ result.document?.type || 'text' }}</span>
          </div>

          <!-- Highlighted snippet -->
          <p
            class="result-snippet"
            v-html="highlightedSnippet(result)"
          ></p>
        </li>
      </ul>

      <!-- Right: inline document viewer -->
      <div class="doc-viewer" role="complementary" aria-label="Document viewer">
        <div v-if="!activeResult" class="viewer-empty">
          <Icon name="hand-paper" />
          <p>Select a result to view the document</p>
          <p class="viewer-hint">Use arrow keys to navigate, Enter to open</p>
        </div>

        <template v-else>
          <div class="viewer-header">
            <div class="viewer-title-row">
              <Icon name="file-alt" class="viewer-icon" />
              <h4 class="viewer-title">{{ activeResult.document?.title || 'Untitled' }}</h4>
            </div>
            <div class="viewer-meta">
              <span v-if="activeResult.document?.category">
                <Icon name="folder" /> {{ activeResult.document.category }}
              </span>
              <span v-if="activeResult.document?.type">
                <Icon name="tag" /> {{ activeResult.document.type }}
              </span>
              <span v-if="activeResult.document?.updatedAt">
                <Icon name="clock" />
                {{ formatDate(activeResult.document.updatedAt) }}
              </span>
              <span
                class="viewer-score"
                :class="scoreClass(activeResult.score)"
              >
                {{ Math.round(activeResult.score * 100) }}% match
              </span>
            </div>
          </div>

          <div v-if="loadingDoc" class="viewer-loading">
            <Icon name="spinner" class="animate-spin" />
            Loading document…
          </div>

          <div v-else class="viewer-body">
            <!-- Highlight query terms in full content -->
            <pre
              class="viewer-content"
              v-html="highlightedContent(viewerContent)"
            ></pre>
          </div>

          <div class="viewer-footer">
            <button
              class="action-btn"
              @click="copyContent"
              :disabled="!viewerContent"
              title="Copy content"
            >
              <Icon name="copy" /> Copy
            </button>
            <span v-if="copySuccess" class="copy-success">
              <Icon name="check" /> Copied
            </span>
          </div>
        </template>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading" class="empty-state">
      <Icon name="search" />
      <p>No results found for "{{ query }}"</p>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * KBSearchResultPanel — Issue #3296
 *
 * Displays ranked KB full-text search results with:
 * - Title, relevance score, and highlighted snippet
 * - Keyboard navigation (arrow keys, Enter, Escape)
 * - Inline read-only document viewer on selection
 * - Query-term highlighting in both snippets and full content
 *
 * Issue #3940: Fixed `as any` cast and consolidated repository instance
 */

import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch, nextTick } from 'vue'
import { KnowledgeRepository } from '@/models/repositories'
import type { SearchResult, KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KBSearchResultPanel')

// ---------------------------------------------------------------------------
// Props & emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  results: SearchResult[]
  query: string
  loading: boolean
  repository: KnowledgeRepository
}>()

const emit = defineEmits<{
  (e: 'select', result: SearchResult): void
  (e: 'close'): void
}>()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const panelRef = ref<HTMLElement | null>(null)
const listRef = ref<HTMLElement | null>(null)
const selectedIndex = ref<number>(-1)
const loadingDoc = ref(false)
const viewerContent = ref<string>('')
const copySuccess = ref(false)

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

const activeResult = computed<SearchResult | null>(() =>
  selectedIndex.value >= 0 ? props.results[selectedIndex.value] ?? null : null
)

// ---------------------------------------------------------------------------
// Watchers
// ---------------------------------------------------------------------------

watch(
  () => props.results,
  () => {
    selectedIndex.value = -1
    viewerContent.value = ''
  }
)

watch(selectedIndex, async (idx) => {
  if (idx < 0) {
    viewerContent.value = ''
    return
  }
  const result = props.results[idx]
  if (!result?.document) return

  emit('select', result)
  await loadDocumentContent(result.document)
  scrollListItemIntoView(idx)
})

// ---------------------------------------------------------------------------
// Keyboard navigation
// ---------------------------------------------------------------------------

function handleKeydown(event: KeyboardEvent): void {
  if (!props.results.length) return

  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      selectedIndex.value = Math.min(selectedIndex.value + 1, props.results.length - 1)
      break
    case 'ArrowUp':
      event.preventDefault()
      selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
      break
    case 'Enter':
      event.preventDefault()
      openSelected()
      break
    case 'Escape':
      event.preventDefault()
      emit('close')
      break
  }
}

function openSelected(): void {
  if (activeResult.value) {
    emit('select', activeResult.value)
  }
}

// ---------------------------------------------------------------------------
// Result selection & document loading
// ---------------------------------------------------------------------------

function selectResult(index: number): void {
  selectedIndex.value = index
  nextTick(() => panelRef.value?.focus())
}

async function loadDocumentContent(document: KnowledgeDocument): Promise<void> {
  if (!document.id) return

  // Use cached content if sufficient
  if (document.content && document.content.length >= 300) {
    viewerContent.value = document.content
    return
  }

  loadingDoc.value = true
  try {
    const full = await props.repository.getDocument(document.id)
    viewerContent.value = full?.content ?? document.content ?? ''
  } catch (err) {
    logger.error('Failed to load document content:', err)
    viewerContent.value = document.content ?? ''
  } finally {
    loadingDoc.value = false
  }
}

function scrollListItemIntoView(index: number): void {
  nextTick(() => {
    const list = listRef.value
    if (!list) return
    const item = list.children[index] as HTMLElement | undefined
    item?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

// ---------------------------------------------------------------------------
// Highlighting helpers
// ---------------------------------------------------------------------------

/** Escape special regex characters in query terms. */
function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Build a regex that matches any individual query word (min 2 chars). */
function buildHighlightRegex(query: string): RegExp | null {
  const terms = query
    .trim()
    .split(/\s+/)
    .filter((t) => t.length >= 2)
    .map(escapeRegex)
  if (!terms.length) return null
  return new RegExp(`(${terms.join('|')})`, 'gi')
}

function applyHighlight(text: string, regex: RegExp): string {
  // Escape HTML entities first to prevent XSS, then apply highlight span
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped.replace(regex, '<mark class="kb-highlight">$1</mark>')
}

function highlightedSnippet(result: SearchResult): string {
  const raw = result.highlights?.[0]
    ?? result.document?.content?.substring(0, 200)
    ?? ''
  const snippet = raw.length > 200 ? raw.substring(0, 200) + '…' : raw
  const regex = buildHighlightRegex(props.query)
  if (!regex) {
    return snippet
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }
  return applyHighlight(snippet, regex)
}

function highlightedContent(text: string): string {
  if (!text) return ''
  const regex = buildHighlightRegex(props.query)
  if (!regex) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }
  return applyHighlight(text, regex)
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function scoreClass(score: number): string {
  if (score >= 0.8) return 'score-high'
  if (score >= 0.6) return 'score-medium'
  return 'score-low'
}

function formatDate(date: Date | string): string {
  try {
    return new Date(date).toLocaleDateString()
  } catch {
    return ''
  }
}

async function copyContent(): Promise<void> {
  if (!viewerContent.value) return
  try {
    await navigator.clipboard.writeText(viewerContent.value)
    copySuccess.value = true
    setTimeout(() => { copySuccess.value = false }, 2000)
  } catch (err) {
    logger.error('Clipboard write failed:', err)
  }
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";

/* Panel container */
.kb-search-result-panel {
  @apply flex flex-col bg-autobot-bg-card rounded-lg border border-autobot-border shadow-md overflow-hidden;
  outline: none;
  max-height: 80vh;
}

/* Header */
.panel-header {
  @apply flex items-center justify-between px-4 py-3 bg-autobot-bg-secondary border-b border-autobot-border;
}

.panel-title {
  @apply flex items-center gap-2 text-sm font-medium text-autobot-text-primary;
}

.panel-title i {
  @apply text-blue-500;
}

.query-label {
  @apply text-blue-600 not-italic font-semibold;
}

.close-btn {
  @apply p-1.5 rounded-md text-autobot-text-muted hover:text-autobot-text-primary hover:bg-autobot-bg-tertiary transition-colors;
}

/* Body layout: list + viewer side by side */
.panel-body {
  @apply flex flex-1 overflow-hidden min-h-0;
}

/* Left list */
.result-list {
  @apply w-64 shrink-0 overflow-y-auto border-r border-autobot-border list-none m-0 p-0;
}

.result-item {
  @apply px-3 py-3 cursor-pointer border-b border-autobot-border transition-colors;
  @apply hover:bg-autobot-bg-secondary;
}

.result-item.selected {
  @apply bg-blue-50 border-l-2 border-l-blue-500;
}

.result-item-header {
  @apply flex items-center gap-1.5 mb-1;
}

.result-rank {
  @apply w-5 h-5 flex items-center justify-center rounded-full bg-autobot-bg-tertiary text-xs text-autobot-text-muted font-semibold shrink-0;
}

.result-title {
  @apply flex-1 text-sm font-medium text-autobot-text-primary truncate;
}

.result-score {
  @apply text-xs px-1.5 py-0.5 rounded-full font-semibold shrink-0;
}

.rerank-badge {
  @apply text-xs px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium shrink-0 flex items-center gap-1;
}

.rerank-badge i {
  @apply text-blue-500;
}

.score-high {
  @apply bg-green-100 text-green-800;
}

.score-medium {
  @apply bg-yellow-100 text-yellow-800;
}

.score-low {
  @apply bg-red-100 text-red-800;
}

.result-item-meta {
  @apply flex gap-3 text-xs text-autobot-text-muted mb-1;
}

.result-item-meta i {
  @apply mr-0.5;
}

.result-snippet {
  @apply text-xs text-autobot-text-secondary line-clamp-2 m-0;
}

/* Right viewer */
.doc-viewer {
  @apply flex-1 flex flex-col overflow-hidden;
}

.viewer-empty {
  @apply flex flex-col items-center justify-center h-full text-autobot-text-muted gap-2 px-6 text-center;
}

.viewer-empty i {
  @apply text-3xl text-autobot-text-muted;
}

.viewer-empty p {
  @apply text-sm;
}

.viewer-hint {
  @apply text-xs text-autobot-text-muted;
}

.viewer-header {
  @apply px-4 py-3 border-b border-autobot-border bg-autobot-bg-secondary;
}

.viewer-title-row {
  @apply flex items-center gap-2 mb-2;
}

.viewer-icon {
  @apply text-blue-500;
}

.viewer-title {
  @apply text-sm font-semibold text-autobot-text-primary m-0;
}

.viewer-meta {
  @apply flex flex-wrap gap-3 text-xs text-autobot-text-muted;
}

.viewer-meta i {
  @apply mr-0.5;
}

.viewer-score {
  @apply px-1.5 py-0.5 rounded-full text-xs font-semibold;
}

.viewer-loading {
  @apply flex items-center justify-center gap-2 py-8 text-autobot-text-muted text-sm;
}

.viewer-body {
  @apply flex-1 overflow-y-auto p-4;
}

.viewer-content {
  @apply text-sm text-autobot-text-primary whitespace-pre-wrap font-sans leading-relaxed m-0;
}

.viewer-footer {
  @apply px-4 py-2 border-t border-autobot-border flex items-center gap-3 bg-autobot-bg-secondary;
}

.action-btn {
  @apply px-3 py-1.5 text-xs font-medium bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 transition-colors;
}

.copy-success {
  @apply text-xs text-green-600 flex items-center gap-1 font-medium;
}

/* Skeleton loading */
.result-skeleton {
  @apply px-3 py-3 border-b border-autobot-border animate-pulse;
}

.skeleton-title {
  @apply h-3 bg-autobot-bg-tertiary rounded w-4/5 mb-2;
}

.skeleton-meta {
  @apply h-2 bg-autobot-bg-tertiary rounded w-2/5 mb-2;
}

.skeleton-snippet {
  @apply h-2 bg-autobot-bg-tertiary rounded w-full;
}

/* Empty state */
.empty-state {
  @apply flex flex-col items-center justify-center py-12 text-autobot-text-muted gap-2;
}

.empty-state i {
  @apply text-3xl;
}

.empty-state p {
  @apply text-sm;
}
</style>

<!-- Global style for the highlight mark (scoped won't reach v-html content) -->
<style>
.kb-highlight {
  background-color: #fef08a;
  color: #713f12;
  border-radius: var(--radius-xs);
  padding: var(--spacing-0) var(--spacing-px);
  font-weight: 600;
}
</style>
