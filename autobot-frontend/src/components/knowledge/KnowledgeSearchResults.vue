<template>
  <BaseCard v-if="search.searchPerformed.value" class="search-results" flush>
    <section v-if="search.useRagSearch.value && search.ragResponse.value?.synthesized_response" class="rag-synthesis">
      <header class="synthesis-header">
        <h4><Icon name="brain" class="rag-icon" aria-hidden="true" /> {{ $t('knowledge.search.aiSynthesis') }}</h4>
        <div v-if="search.ragResponse.value.rag_analysis" class="analysis-badges">
          <BaseBadge :variant="confidenceVariant(search.ragResponse.value.rag_analysis.confidence)" size="sm">
            {{ $t('knowledge.search.confidence', { value: Math.round(search.ragResponse.value.rag_analysis.confidence * 100) }) }}
          </BaseBadge>
          <BaseBadge variant="info" size="sm">
            {{ $t('knowledge.search.sourcesCount', { count: search.ragResponse.value.rag_analysis.sources_used }) }}
          </BaseBadge>
        </div>
      </header>
      <p class="synthesis-content">{{ search.ragResponse.value.synthesized_response }}</p>
      <p
        v-if="search.ragResponse.value.reformulated_query && search.ragResponse.value.reformulated_query !== search.ragResponse.value.query"
        class="reformulated-note"
      >
        <Icon name="lightbulb" aria-hidden="true" />
        {{ $t('knowledge.search.enhancedQuery') }}: "{{ search.ragResponse.value.reformulated_query }}"
      </p>
    </section>

    <!-- Issue #3296: KB search result panel with keyboard nav + highlight -->
    <!-- Issue #3940: Pass repository instance to eliminate duplicate creation -->
    <KBSearchResultPanel
      v-if="search.searchResults.value.length > 0 || search.isSearching.value"
      :repository="knowledgeRepository"
      :results="search.searchResults.value"
      :query="search.lastSearchQuery.value"
      :loading="search.isSearching.value"
      @select="e => emit('select', e)"
      @close="emit('close')"
    />

    <EmptyState
      v-if="search.searchResults.value.length === 0 && !search.isSearching.value"
      icon="search"
      :message="$t('knowledge.search.noResults')"
    >
      <p class="no-results-hint">
        {{ search.useRagSearch.value ? $t('knowledge.search.noResultsRagHint') : $t('knowledge.search.noResultsHint') }}
      </p>
      <BaseAlert variant="info" :title="$t('knowledge.search.needToIndex')">
        {{ $t('knowledge.search.indexHelpBefore') }}
        <router-link to="/knowledge/manage" class="help-link">{{ $t('knowledge.search.indexHelpLink') }}</router-link>
        {{ $t('knowledge.search.indexHelpAfter') }}
      </BaseAlert>
    </EmptyState>

    <BaseAlert
      v-if="search.useRagSearch.value && search.ragError.value"
      variant="warning"
      :title="$t('knowledge.search.ragUnavailable')"
    >
      <p class="rag-error-text">{{ search.ragError.value }}</p>
      <p class="rag-error-text">{{ $t('knowledge.search.fallbackNote') }}</p>
    </BaseAlert>
  </BaseCard>
</template>

<script setup lang="ts">
import { knowledgeRepository } from '@/models/repositories'
import type { SearchResult } from '@/stores/useKnowledgeStore'
import EmptyState from '@/components/ui/EmptyState.vue'
import KBSearchResultPanel from './KBSearchResultPanel.vue'
import Icon from '@/components/ui/Icon.vue'
import { BaseAlert, BaseBadge, BaseCard } from '@autobot/ui'
import type { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'

defineProps<{ search: ReturnType<typeof useKnowledgeSearch> }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', result: SearchResult): void
}>()

const CONFIDENCE_HIGH = 0.8
const CONFIDENCE_MEDIUM = 0.6

function confidenceVariant(confidence: number): 'success' | 'warning' | 'error' {
  if (confidence >= CONFIDENCE_HIGH) return 'success'
  if (confidence >= CONFIDENCE_MEDIUM) return 'warning'
  return 'error'
}
</script>

<style scoped>
.search-results {
  min-inline-size: 0;
}

.rag-synthesis {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  background: var(--info-bg);
  color: var(--info-fg);
  border-block-end: var(--bw) solid var(--line);
}

.synthesis-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.synthesis-header h4 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
}

.analysis-badges {
  display: flex;
  gap: var(--spacing-2);
}

.synthesis-content,
.reformulated-note,
.no-results-hint,
.rag-error-text {
  margin: 0;
}

.synthesis-content {
  font-size: var(--text-sm);
  line-height: 1.6;
  color: var(--text);
}

.reformulated-note {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

.no-results-hint {
  font-size: var(--text-sm);
  color: var(--muted);
}

.help-link {
  color: var(--link);
  font-weight: 600;
  text-decoration: underline;
}
</style>
