<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KBSearchResultPanel — Issue #3296; Refined UI port in #18244.
  Ranked KB full-text search results: title, relevance score and a highlighted snippet per hit,
  keyboard navigation (arrows, Enter, Escape), and the selected hit's document beside the list
  (KBSearchDocViewer). Query terms are highlighted in snippets and in the full text.
-->
<template>
  <div
    ref="panelRef"
    class="kb-search-result-panel"
    role="region"
    :aria-label="$t('knowledge.searchPanel.label')"
    tabindex="-1"
    @keydown="handleKeydown"
  >
    <header class="panel-header">
      <div class="panel-title">
        <Icon name="search" aria-hidden="true" />
        <span v-if="loading">{{ $t('knowledge.searchPanel.searching') }}</span>
        <span v-else-if="results.length">
          {{ $t('knowledge.searchPanel.resultsFor', { count: results.length }) }}
          <em class="query-label">"{{ query }}"</em>
        </span>
        <span v-else>{{ $t('knowledge.searchPanel.noResultsFor') }} <em class="query-label">"{{ query }}"</em></span>
      </div>
      <BaseButton variant="ghost" size="sm" :aria-label="$t('knowledge.searchPanel.close')" @click="emit('close')">
        <Icon name="times" aria-hidden="true" />
      </BaseButton>
    </header>

    <div v-if="loading" class="result-list" aria-busy="true">
      <BaseSkeleton v-for="n in 3" :key="n" :lines="3" />
    </div>

    <div v-else-if="results.length" class="panel-body">
      <ul ref="listRef" class="result-list" role="listbox" :aria-label="$t('knowledge.searchPanel.rankedLabel')">
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
            <span class="result-title">{{ titleOf(result) }}</span>
            <BaseTooltip :text="$t('knowledge.searchPanel.relevance', { score: percent(result.score) })" placement="left">
              <template #default="{ describedby }">
                <BaseBadge :variant="scoreVariant(result.score)" size="xs" tabindex="0" :aria-describedby="describedby">
                  {{ percent(result.score) }}%
                </BaseBadge>
              </template>
            </BaseTooltip>
            <BaseTooltip v-if="result.rerank_score != null" :text="$t('knowledge.searchPanel.rerank', { score: percent(result.rerank_score) })" placement="left">
              <template #default="{ describedby }">
                <BaseBadge variant="info" size="xs" tabindex="0" :aria-describedby="describedby">
                  <Icon name="brain" aria-hidden="true" /> {{ percent(result.rerank_score) }}%
                </BaseBadge>
              </template>
            </BaseTooltip>
          </div>
          <div class="result-item-meta">
            <span><Icon name="folder" aria-hidden="true" /> {{ result.document?.category || $t('knowledge.searchPanel.general') }}</span>
            <span><Icon name="file-alt" aria-hidden="true" /> {{ result.document?.type || $t('knowledge.searchPanel.text') }}</span>
          </div>
          <p class="result-snippet" v-html="snippetOf(result)"></p>
        </li>
      </ul>

      <KBSearchDocViewer :result="activeResult" :content="viewerContent" :query="query" :loading="loadingDoc" />
    </div>

    <div v-else class="empty-state">
      <Icon name="search" aria-hidden="true" />
      <p>{{ $t('knowledge.searchPanel.noResultsFor') }} "{{ query }}"</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseSkeleton, BaseTooltip } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import KBSearchDocViewer from './KBSearchDocViewer.vue'
import { KnowledgeRepository } from '@/models/repositories'
import type { SearchResult, KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { createLogger } from '@/utils/debugUtils'
import { preferredScrollBehavior } from '@/composables/useReducedMotion'
import { formatManPageTitle } from '@/utils/formatHelpers'
import { highlightSnippet, scoreVariant } from '@/composables/knowledge/searchHighlight'

// A document whose list payload already holds this much text is shown without a fetch.
const FULL_CONTENT_MIN = 300

const logger = createLogger('KBSearchResultPanel')
const { t } = useI18n()

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

const panelRef = ref<HTMLElement | null>(null)
const listRef = ref<HTMLElement | null>(null)
const selectedIndex = ref(-1)
const loadingDoc = ref(false)
const viewerContent = ref('')

const activeResult = computed<SearchResult | null>(() =>
  selectedIndex.value >= 0 ? (props.results[selectedIndex.value] ?? null) : null,
)

const percent = (score: number) => Math.round(score * 100)
const titleOf = (r: SearchResult) =>
  formatManPageTitle(r.document?.title, r.document?.metadata?.factType, t) || t('knowledge.searchPanel.untitled')
const snippetOf = (r: SearchResult) =>
  highlightSnippet(r.highlights?.[0] ?? r.document?.content?.substring(0, 200) ?? '', props.query)

watch(
  () => props.results,
  () => {
    selectedIndex.value = -1
    viewerContent.value = ''
  },
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

function handleKeydown(event: KeyboardEvent): void {
  if (!props.results.length) return
  const last = props.results.length - 1
  const moves: Record<string, () => void> = {
    ArrowDown: () => (selectedIndex.value = Math.min(selectedIndex.value + 1, last)),
    ArrowUp: () => (selectedIndex.value = Math.max(selectedIndex.value - 1, 0)),
    Enter: openSelected,
    Escape: () => emit('close'),
  }
  const move = moves[event.key]
  if (!move) return
  event.preventDefault()
  move()
}

function openSelected(): void {
  if (activeResult.value) emit('select', activeResult.value)
}

function selectResult(index: number): void {
  selectedIndex.value = index
  nextTick(() => panelRef.value?.focus())
}

async function loadDocumentContent(document: KnowledgeDocument): Promise<void> {
  if (!document.id) return
  if (document.content && document.content.length >= FULL_CONTENT_MIN) {
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
    const item = listRef.value?.children[index] as HTMLElement | undefined
    // #14770: no glide for a user who asked for reduced motion; the item still comes into view.
    item?.scrollIntoView({ block: 'nearest', behavior: preferredScrollBehavior() })
  })
}
</script>

<style scoped>
.kb-search-result-panel {
  display: flex;
  flex-direction: column;
  max-block-size: 80vh;
  overflow: hidden;
  outline: none;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-2) var(--spacing-4);
  border-block-end: var(--bw) solid var(--line);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
}

.query-label {
  font-style: normal;
  color: var(--text2);
}

.panel-body {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) 3fr;
  flex: 1;
  min-block-size: 0;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: var(--spacing-2);
  list-style: none;
  overflow-y: auto;
  border-inline-end: var(--bw) solid var(--line);
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding: var(--spacing-2);
  border-radius: var(--radius-md);
  border-inline-start: 3px solid transparent;
  cursor: pointer;
}

.result-item:hover,
.result-item.selected {
  background: var(--surface2);
}

.result-item.selected {
  border-inline-start-color: var(--primary);
}

.result-item:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}

.result-item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.result-rank {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--muted);
}

.result-title {
  flex: 1;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
}

.result-item-meta {
  display: flex;
  gap: var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--muted);
}

.result-snippet {
  margin: 0;
  font-size: var(--text-xs);
  line-height: 1.5;
  color: var(--text2);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-8) var(--spacing-4);
  color: var(--muted);
}

.empty-state p {
  margin: 0;
  font-size: var(--text-sm);
}
</style>

<!-- The mark sits inside v-html content, which a scoped style cannot reach. -->
<style>
.kb-highlight {
  background-color: var(--kbsearch-highlight-bg);
  color: var(--kbsearch-highlight-text);
  border-radius: var(--radius-xs);
  padding: var(--spacing-0) var(--spacing-px);
  font-weight: 600;
}
</style>
