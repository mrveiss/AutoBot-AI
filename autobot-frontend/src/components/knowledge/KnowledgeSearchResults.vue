<template>
  <div v-if="search.searchPerformed.value" class="search-results">
    <!-- RAG Synthesized Response -->
    <div v-if="search.useRagSearch.value && search.ragResponse.value?.synthesized_response" class="rag-synthesis">
      <div class="synthesis-header">
        <h4>
          <Icon name="brain" class="rag-icon" />
          {{ $t('knowledge.search.aiSynthesis') }}
        </h4>
        <div v-if="search.ragResponse.value.rag_analysis" class="analysis-badges">
          <span class="confidence-badge" :class="getConfidenceBadgeClass(search.ragResponse.value.rag_analysis.confidence)">
            {{ $t('knowledge.search.confidence', { value: Math.round(search.ragResponse.value.rag_analysis.confidence * 100) }) }}
          </span>
          <span class="sources-badge">
            {{ $t('knowledge.search.sourcesCount', { count: search.ragResponse.value.rag_analysis.sources_used }) }}
          </span>
        </div>
      </div>

      <div class="synthesis-content">
        <p>{{ search.ragResponse.value.synthesized_response }}</p>
      </div>

      <div v-if="search.ragResponse.value.reformulated_query && search.ragResponse.value.reformulated_query !== search.ragResponse.value.query" class="query-reformulation">
        <p class="reformulated-note">
          <Icon name="lightbulb" />
          {{ $t('knowledge.search.enhancedQuery') }}: "{{ search.ragResponse.value.reformulated_query }}"
        </p>
      </div>
    </div>

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

    <!-- No Results -->
    <EmptyState
      v-if="search.searchResults.value.length === 0 && !search.isSearching.value"
      icon="search"
      :message="$t('knowledge.search.noResults')"
    >
      <p class="no-results-hint">
        {{ search.useRagSearch.value
          ? $t('knowledge.search.noResultsRagHint')
          : $t('knowledge.search.noResultsHint')
        }}
      </p>
      <div class="initialization-help">
        <p><strong>{{ $t('knowledge.search.needToIndex') }}</strong></p>
        <p>{{ $t('knowledge.search.indexHelpBefore') }} <router-link to="/knowledge/manage" class="help-link">{{ $t('knowledge.search.indexHelpLink') }}</router-link> {{ $t('knowledge.search.indexHelpAfter') }}</p>
      </div>
    </EmptyState>

    <!-- RAG Error Handling -->
    <div v-if="search.useRagSearch.value && search.ragError.value" class="rag-error">
      <div class="error-header">
        <Icon name="exclamation-triangle" />
        {{ $t('knowledge.search.ragUnavailable') }}
      </div>
      <p>{{ search.ragError.value }}</p>
      <p class="fallback-note">{{ $t('knowledge.search.fallbackNote') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { knowledgeRepository } from '@/models/repositories'
import type { SearchResult } from '@/stores/useKnowledgeStore'
import EmptyState from '@/components/ui/EmptyState.vue'
import KBSearchResultPanel from './KBSearchResultPanel.vue'
import Icon from '@/components/ui/Icon.vue'
import type { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'

defineProps<{ search: ReturnType<typeof useKnowledgeSearch> }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', result: SearchResult): void
}>()

function getConfidenceBadgeClass(confidence: number): string {
  if (confidence >= 0.8) return 'confidence-high'
  if (confidence >= 0.6) return 'confidence-medium'
  return 'confidence-low'
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";

/* Results */
.search-results {
  @apply space-y-4;
}

/* RAG Synthesis */
.rag-synthesis {
  @apply mb-6 p-4 rounded-lg;
  background: var(--color-info-bg);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.synthesis-header {
  @apply flex justify-between items-start mb-3;
}

.synthesis-header h4 {
  @apply text-lg font-semibold flex items-center gap-2;
  color: var(--text-primary);
}

.rag-icon {
  color: var(--color-info);
}

.analysis-badges {
  @apply flex gap-2;
}

.confidence-badge, .sources-badge {
  @apply px-2 py-1 rounded-full text-xs font-medium;
}

.confidence-high {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.confidence-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.confidence-low {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.sources-badge {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.synthesis-content {
  @apply prose prose-sm max-w-none;
}

.synthesis-content p {
  @apply text-autobot-text-primary leading-relaxed;
}

.query-reformulation {
  @apply mt-3 pt-3 border-t;
  border-color: rgba(59, 130, 246, 0.2);
}

.reformulated-note {
  @apply text-sm flex items-center gap-2;
  color: var(--color-info);
}

/* No Results */
.no-results-hint {
  @apply text-sm text-autobot-text-muted mt-2;
}

.initialization-help {
  @apply mt-4 p-4 rounded-lg;
  background: var(--color-info-bg);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.initialization-help p {
  @apply text-sm mb-1;
  color: var(--text-primary);
}

.initialization-help strong {
  @apply font-semibold;
}

.help-link {
  @apply underline font-medium;
  color: var(--color-info);
}

.help-link:hover {
  color: var(--text-primary);
}

/* RAG Error */
.rag-error {
  @apply mt-4 p-4 rounded-lg;
  background: var(--color-warning-bg);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.error-header {
  @apply flex items-center gap-2 font-medium mb-2;
  color: var(--color-warning);
}

.rag-error p {
  @apply text-sm;
  color: var(--color-warning);
}

.fallback-note {
  @apply mt-2 text-xs font-medium;
  color: var(--color-warning);
}
</style>
