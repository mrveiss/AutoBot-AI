<template>
  <div class="knowledge-search">
    <div class="search-header">
      <h3>{{ $t('knowledge.search.title') }}</h3>
      <p>{{ $t('knowledge.search.subtitle') }}</p>
    </div>

    <!-- Search Mode Toggle -->
    <div class="search-mode-toggle">
      <div class="toggle-container">
        <button
          :class="['mode-button', { active: !useRagSearch }]"
          @click="useRagSearch = false"
        >
          <Icon name="search" />
          {{ $t('knowledge.search.traditionalSearch') }}
        </button>
        <button
          :class="['mode-button', 'rag-button', { active: useRagSearch }]"
          @click="useRagSearch = true"
        >
          <Icon name="brain" />
          {{ $t('knowledge.search.ragEnhanced') }}
        </button>
      </div>
      <div class="mode-description">
        <p v-if="!useRagSearch" class="traditional-desc">
          {{ $t('knowledge.search.traditionalDesc') }}
        </p>
        <p v-else class="rag-desc">
          {{ $t('knowledge.search.ragDesc') }}
        </p>
      </div>
    </div>

    <!-- Category Filter -->
    <div class="category-filter">
      <label class="filter-label">
        <Icon name="filter" />
        {{ $t('knowledge.search.filterByCategory') }}
      </label>
      <div class="filter-controls">
        <select
          v-model="selectedCategory"
          class="category-select"
          :disabled="loadingCategories"
          @change="debouncedCategoryChange"
        >
          <option value="">{{ $t('knowledge.search.allCategories') }}</option>
          <option
            v-for="cat in categories"
            :key="cat.id"
            :value="cat.name"
          >
            {{ formatCategory(cat.name) }} ({{ cat.count }})
          </option>
        </select>
        <button
          v-if="selectedCategory"
          @click="clearCategoryFilter"
          class="clear-filter-button"
          :title="$t('knowledge.search.clearCategoryFilter')"
        >
          <Icon name="times" />
        </button>
        <span v-if="loadingCategories" class="loading-indicator">
          <Icon name="spinner" :spin="true" />
        </span>
      </div>
      <span v-if="selectedCategory" class="active-filter-badge">
        {{ $t('knowledge.search.filtering', { category: formatCategory(selectedCategory) }) }}
      </span>
      <div v-if="categoriesError" class="categories-error">
        <Icon name="exclamation-triangle" />
        {{ categoriesError }}
        <button @click="loadCategories" class="retry-button">
          <Icon name="redo" /> {{ $t('knowledge.search.retry') }}
        </button>
      </div>
    </div>

    <!-- Issue #685: Access Level Filter -->
    <div class="access-level-filter">
      <label class="filter-label">
        <Icon name="shield-alt" />
        {{ $t('knowledge.search.filterByAccessLevel') }}
      </label>
      <div class="filter-chips">
        <button
          v-for="level in accessLevels"
          :key="level.value"
          :class="['filter-chip', { active: selectedAccessLevel === level.value }]"
          @click="debouncedAccessLevelChange(level.value)"
        >
          <i :class="level.icon"></i>
          {{ level.label }}
        </button>
        <button
          v-if="selectedAccessLevel"
          @click="clearAccessLevelFilter"
          class="clear-chip"
          :title="$t('knowledge.search.clearAccessLevelFilter')"
        >
          <Icon name="times" />
          {{ $t('knowledge.search.clear') }}
        </button>
      </div>
    </div>

    <!-- Search Input -->
    <div class="search-input-container">
      <div class="search-input-wrapper">
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="useRagSearch ? $t('knowledge.search.ragPlaceholder') : $t('knowledge.search.searchPlaceholder')"
          @keyup.enter="handleSearch"
          class="search-input"
        >
        <button
          @click="handleSearch"
          :disabled="isSearching || !searchQuery.trim()"
          class="search-button"
        >
          <i v-if="isSearching" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-search"></i>
          {{ isSearching ? $t('knowledge.search.searching') : $t('knowledge.search.searchBtn') }}
        </button>
      </div>

      <!-- RAG Options -->
      <div v-if="useRagSearch" class="rag-options">
        <div class="option-group">
          <label>
            <input
              v-model="ragOptions.reformulateQuery"
              type="checkbox"
            >
            {{ $t('knowledge.search.autoEnhanceQuery') }}
          </label>
        </div>
        <div class="option-group">
          <label>
            <input
              v-model="ragOptions.enableReranking"
              type="checkbox"
            >
            <span class="reranking-label">
              {{ $t('knowledge.search.enableReranking') }}
              <span class="reranking-badge">{{ $t('knowledge.search.rerankingBadge') }}</span>
            </span>
          </label>
        </div>
        <div class="option-group">
          <label>
            {{ $t('knowledge.search.resultsLimit') }}
            <select v-model.number="ragOptions.limit" class="limit-select">
              <option value="5">5</option>
              <option value="10">10</option>
              <option value="15">15</option>
              <option value="20">20</option>
            </select>
          </label>
        </div>
      </div>
    </div>

    <!-- Search Results -->
    <div v-if="searchPerformed" class="search-results">
      <!-- RAG Synthesized Response -->
      <div v-if="useRagSearch && ragResponse?.synthesized_response" class="rag-synthesis">
        <div class="synthesis-header">
          <h4>
            <Icon name="brain" class="rag-icon" />
            {{ $t('knowledge.search.aiSynthesis') }}
          </h4>
          <div v-if="ragResponse.rag_analysis" class="analysis-badges">
            <span class="confidence-badge" :class="getConfidenceBadgeClass(ragResponse.rag_analysis.confidence)">
              {{ $t('knowledge.search.confidence', { value: Math.round(ragResponse.rag_analysis.confidence * 100) }) }}
            </span>
            <span class="sources-badge">
              {{ $t('knowledge.search.sourcesCount', { count: ragResponse.rag_analysis.sources_used }) }}
            </span>
          </div>
        </div>

        <div class="synthesis-content">
          <p>{{ ragResponse.synthesized_response }}</p>
        </div>

        <div v-if="ragResponse.reformulated_query && ragResponse.reformulated_query !== ragResponse.query" class="query-reformulation">
          <p class="reformulated-note">
            <Icon name="lightbulb" />
            {{ $t('knowledge.search.enhancedQuery') }}: "{{ ragResponse.reformulated_query }}"
          </p>
        </div>
      </div>

      <!-- Issue #3296: KB search result panel with keyboard nav + highlight -->
      <!-- Issue #3940: Pass repository instance to eliminate duplicate creation -->
      <KBSearchResultPanel
        v-if="hasSearchResults || isSearching"
        :repository="knowledgeRepo"
        :results="searchResults"
        :query="lastSearchQuery"
        :loading="isSearching"
        @select="onResultSelect"
        @close="clearResults"
      />

      <!-- No Results -->
      <EmptyState
        v-if="!hasSearchResults && !isSearching"
        icon="search"
        :message="$t('knowledge.search.noResults')"
      >
        <p class="no-results-hint">
          {{ useRagSearch
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
      <div v-if="useRagSearch && ragError" class="rag-error">
        <div class="error-header">
          <Icon name="exclamation-triangle" />
          {{ $t('knowledge.search.ragUnavailable') }}
        </div>
        <p>{{ ragError }}</p>
        <p class="fallback-note">{{ $t('knowledge.search.fallbackNote') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { knowledgeRepository, type RagSearchResponse } from '@/models/repositories'
import type { SearchResult } from '@/stores/useKnowledgeStore'
import type { KnowledgeCategoryItem } from '@/types/knowledgeBase'
import { useKnowledgeCategories } from '@/composables/knowledge/useKnowledgeCategories'
import { formatCategoryName as formatCategory } from '@/utils/formatHelpers'
import { useDebouncedFn } from '@/composables/useDebounce'
import EmptyState from '@/components/ui/EmptyState.vue'
import KBSearchResultPanel from './KBSearchResultPanel.vue'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('KnowledgeSearch')

const { t } = useI18n()

// Issue #3969: Use shared singleton — never instantiate a second KnowledgeRepository here
const knowledgeRepo = knowledgeRepository

// Domain composable (migrated from useKnowledgeBase BC shim in #5193)
const { fetchCategories } = useKnowledgeCategories()

// State
const searchQuery = ref('')
const searchResults = ref<SearchResult[]>([])
const ragResponse = ref<RagSearchResponse | null>(null)
const ragError = ref<string | null>(null)
const isSearching = ref(false)
const searchPerformed = ref(false)
const lastSearchQuery = ref('')
const useRagSearch = ref(false)

// Category filter state
const categories = ref<KnowledgeCategoryItem[]>([])
const selectedCategory = ref<string>('')
const loadingCategories = ref(false)
const categoriesError = ref<string | null>(null)

// Issue #685: Access level filter state
const selectedAccessLevel = ref<string>('')
const accessLevels = computed(() => [
  { value: 'autobot', label: t('knowledge.search.accessPlatform'), icon: 'fas fa-robot' },
  { value: 'general', label: t('knowledge.search.accessPublic'), icon: 'fas fa-globe' },
  { value: 'system', label: t('knowledge.search.accessSystem'), icon: 'fas fa-cog' },
  { value: 'user', label: t('knowledge.search.accessUser'), icon: 'fas fa-user' }
])

// RAG Options
const ragOptions = ref({
  reformulateQuery: true,
  enableReranking: true,
  limit: 10
})

// Issue #4035: Debounce filter changes to avoid excessive re-searches
const { debouncedFn: debouncedCategoryChange } = useDebouncedFn(
  async () => {
    // Re-run search with new category filter
    if (searchPerformed.value && searchQuery.value.trim()) {
      await handleSearch()
    }
  },
  350
)

// Issue #4035: Debounce access level filter changes
const { debouncedFn: debouncedAccessLevelChange } = useDebouncedFn(
  async (level: string) => {
    selectedAccessLevel.value = selectedAccessLevel.value === level ? '' : level
    // Re-run search with new access level filter
    if (searchPerformed.value && searchQuery.value.trim()) {
      await handleSearch()
    }
  },
  350
)

// Load categories on mount
onMounted(async () => {
  await loadCategories()
})

// Load categories from API
const loadCategories = async () => {
  loadingCategories.value = true
  categoriesError.value = null
  try {
    categories.value = await fetchCategories()
  } catch (error) {
    logger.error('Failed to load categories:', error)
    categories.value = []
    categoriesError.value = error instanceof Error ? error.message : 'Failed to load categories'
  } finally {
    loadingCategories.value = false
  }
}

// Computed
const hasSearchResults = computed(() => searchResults.value.length > 0)

// Build category filter object if a category is selected
const buildCategoryFilter = () => {
  if (selectedCategory.value) {
    return { categories: [selectedCategory.value] }
  }
  return undefined
}

// Methods
const handleSearch = async () => {
  if (!searchQuery.value.trim()) return

  isSearching.value = true
  ragError.value = null
  ragResponse.value = null

  // Build filters including category
  const categoryFilter = buildCategoryFilter()

  try {
    if (useRagSearch.value) {
      // Use RAG-enhanced search
      try {
        ragResponse.value = await knowledgeRepo.ragSearch({
          query: searchQuery.value,
          limit: ragOptions.value.limit,
          reformulate_query: ragOptions.value.reformulateQuery
        })

        if (ragResponse.value.results) {
          // Filter results by category client-side for RAG (backend doesn't support category filter)
          let results = ragResponse.value.results
          if (selectedCategory.value) {
            results = results.filter(r => {
              const docCategory = r.document?.category
              // Safe metadata category extraction with runtime validation
              let metaCategory: unknown = undefined
              const metadata = r.document?.metadata
              if (metadata && typeof metadata === 'object' && 'category' in metadata) {
                metaCategory = (metadata as { category?: unknown }).category
              }
              return docCategory === selectedCategory.value ||
                (typeof metaCategory === 'string' && metaCategory === selectedCategory.value)
            })
          }
          // Issue #685: Filter by access level client-side
          if (selectedAccessLevel.value) {
            results = results.filter(r => {
              const docAccessLevel = (r.document as any)?.access_level
              const metaAccessLevel = (r.document as any)?.metadata?.access_level
              return docAccessLevel === selectedAccessLevel.value || metaAccessLevel === selectedAccessLevel.value
            })
          }
          searchResults.value = results
        }
      } catch (ragErr: unknown) {
        const errorMessage = ragErr instanceof Error ? ragErr.message : 'RAG functionality is currently unavailable'
        ragError.value = errorMessage

        // Fallback to traditional search with reranking if enabled
        const results = await knowledgeRepo.searchKnowledge({
          query: searchQuery.value,
          limit: ragOptions.value.limit,
          use_rag: false,
          enable_reranking: ragOptions.value.enableReranking,
          filters: categoryFilter
        })
        searchResults.value = results
      }
    } else {
      // Use traditional search (without reranking in non-RAG mode)
      let results = await knowledgeRepo.searchKnowledge({
        query: searchQuery.value,
        limit: 20,
        use_rag: false,
        enable_reranking: false,
        filters: categoryFilter
      })
      // Issue #685: Filter by access level client-side
      if (selectedAccessLevel.value) {
        results = results.filter(r => {
          const docAccessLevel = (r.document as any)?.access_level
          const metaAccessLevel = (r.document as any)?.metadata?.access_level
          return docAccessLevel === selectedAccessLevel.value || metaAccessLevel === selectedAccessLevel.value
        })
      }
      searchResults.value = results
    }
  } catch (error) {
    logger.error('Knowledge search failed:', error)
    searchResults.value = []
    if (useRagSearch.value) {
      ragError.value = 'Search failed - backend may be unavailable'
    }
  } finally {
    isSearching.value = false
    searchPerformed.value = true
    lastSearchQuery.value = searchQuery.value
  }
}

// Clear category filter and re-run search if already searched
const clearCategoryFilter = async () => {
  selectedCategory.value = ''
  // Re-run search to show unfiltered results if search was already performed
  if (searchPerformed.value && searchQuery.value.trim()) {
    await handleSearch()
  }
}

// Issue #685: Access level filter methods
const clearAccessLevelFilter = async () => {
  selectedAccessLevel.value = ''
  // Re-run search to show unfiltered results
  if (searchPerformed.value && searchQuery.value.trim()) {
    await handleSearch()
  }
}

const getConfidenceBadgeClass = (confidence: number) => {
  if (confidence >= 0.8) return 'confidence-high'
  if (confidence >= 0.6) return 'confidence-medium'
  return 'confidence-low'
}

// Issue #3296: Handle result selection from KBSearchResultPanel
const onResultSelect = (result: SearchResult) => {
  logger.debug('Result selected:', result.document?.id)
}

// Issue #3296: Close panel and reset search state
const clearResults = () => {
  searchResults.value = []
  searchPerformed.value = false
  ragResponse.value = null
  ragError.value = null
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";
.knowledge-search {
  @apply p-4 bg-autobot-bg-card rounded-lg shadow-sm border;
}

.search-header {
  @apply mb-6;
}

.search-header h3 {
  @apply text-lg font-semibold text-autobot-text-primary mb-1;
}

.search-header p {
  @apply text-sm text-autobot-text-secondary;
}

/* Search Mode Toggle */
.search-mode-toggle {
  @apply mb-4;
}

/* Category Filter */
.category-filter {
  @apply mb-4 p-3 bg-autobot-bg-tertiary rounded-lg border border-autobot-border;
}

.filter-label {
  @apply text-sm font-medium text-autobot-text-secondary flex items-center gap-2 mb-2;
}

.filter-label i {
  @apply text-autobot-text-muted;
}

.filter-controls {
  @apply flex items-center gap-2;
}

.category-select {
  @apply flex-1 px-3 py-2 border border-autobot-border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-autobot-bg-card;
}

.category-select:disabled {
  @apply bg-autobot-bg-secondary cursor-not-allowed;
}

.clear-filter-button {
  @apply p-2 text-autobot-text-muted rounded-lg transition-colors;
  &:hover { color: var(--color-error); background: var(--color-error-bg); }
}

.loading-indicator {
  @apply text-autobot-text-muted text-sm;
}

.active-filter-badge {
  @apply inline-block mt-2 px-2 py-1 text-xs font-medium rounded-full;
  background: var(--color-info-bg);
  color: var(--color-info);
}

.categories-error {
  @apply mt-2 p-2 rounded-lg text-sm flex items-center gap-2;
  background: var(--color-error-bg);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error);
}

.categories-error i {
  color: var(--color-error);
}

.retry-button {
  @apply ml-auto px-2 py-1 text-xs rounded transition-colors flex items-center gap-1;
  background: var(--color-error-bg);
  color: var(--color-error);
}

.retry-button:hover {
  background: var(--color-error-bg-hover);
}

/* Issue #685: Access Level Filter */
.access-level-filter {
  @apply mb-4 p-3 bg-autobot-bg-tertiary rounded-lg border border-autobot-border;
}

.filter-chips {
  @apply flex flex-wrap gap-2;
}

.filter-chip {
  @apply px-3 py-1.5 text-sm font-medium rounded-full border-2 transition-all flex items-center gap-1.5;
  @apply border-autobot-border bg-autobot-bg-card text-autobot-text-secondary hover:bg-autobot-bg-secondary;
}

.filter-chip.active {
  border-color: var(--color-primary);
  background: var(--color-info-bg);
  color: var(--color-info);
}

.filter-chip i {
  @apply text-xs;
}

.clear-chip {
  @apply px-3 py-1.5 text-sm font-medium rounded-full border-2 transition-all flex items-center gap-1.5;
  @apply bg-autobot-bg-card;
  border-color: rgba(239, 68, 68, 0.5);
  color: var(--color-error);
  &:hover { background: var(--color-error-bg); border-color: var(--color-error); }
}

.toggle-container {
  @apply flex bg-autobot-bg-secondary rounded-lg p-1 mb-2;
}

.mode-button {
  @apply flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 flex items-center justify-center gap-2;
}

.mode-button:not(.active) {
  @apply text-autobot-text-secondary hover:text-autobot-text-primary;
}

.mode-button.active {
  @apply bg-autobot-bg-card text-autobot-text-primary shadow-sm;
}

.mode-button.rag-button.active {
  background: var(--color-primary);
  color: var(--text-inverse);
}

.mode-description {
  @apply text-xs text-autobot-text-muted px-2;
}

.rag-desc {
  color: var(--color-info);
}

/* RAG Options */
.rag-options {
  @apply mt-3 p-3 rounded-lg;
  background: var(--color-info-bg);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.option-group {
  @apply flex items-center gap-2 text-sm text-autobot-text-secondary;
}

.option-group + .option-group {
  @apply mt-2;
}

.limit-select {
  @apply ml-2 px-2 py-1 border border-autobot-border rounded text-xs;
}

.reranking-label {
  @apply flex items-center gap-2;
}

.reranking-badge {
  @apply text-xs px-2 py-0.5 rounded-full font-normal;
  background: var(--color-info-bg);
  color: var(--color-info);
}

/* Search Input */
.search-input-container {
  @apply mb-6;
}

.search-input-wrapper {
  @apply flex gap-2;
}

.search-input {
  @apply flex-1 px-4 py-2 border border-autobot-border rounded-lg focus:ring-2 focus:border-transparent;
  --tw-ring-color: var(--color-primary);
}

.search-button {
  @apply px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2;
  background: var(--color-primary);
  color: var(--text-inverse);
}

.search-button:hover:not(:disabled) {
  filter: brightness(1.1);
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

/* Results */
.search-results {
  @apply space-y-4;
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
