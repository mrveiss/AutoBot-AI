<template>
  <div class="knowledge-search">
    <div class="search-header">
      <h3>Knowledge Search</h3>
      <p>Search through your knowledge base documents, facts, and stored information</p>
    </div>

    <!-- Search Mode Toggle -->
    <div class="search-mode-toggle">
      <div class="toggle-container">
        <button
          :class="['mode-button', { active: !useRagSearch }]"
          @click="useRagSearch = false"
        >
          <i class="fas fa-search"></i>
          Traditional Search
        </button>
        <button
          :class="['mode-button', 'rag-button', { active: useRagSearch }]"
          @click="useRagSearch = true"
        >
          <i class="fas fa-brain"></i>
          RAG Enhanced
        </button>
      </div>
      <div class="mode-description">
        <p v-if="!useRagSearch" class="traditional-desc">
          Fast semantic search across documents
        </p>
        <p v-else class="rag-desc">
          AI-powered synthesis with comprehensive analysis
        </p>
      </div>
    </div>

    <!-- Category Filter -->
    <div class="category-filter">
      <label class="filter-label">
        <i class="fas fa-filter"></i>
        Filter by Category:
      </label>
      <div class="filter-controls">
        <select
          v-model="selectedCategory"
          class="category-select"
          :disabled="loadingCategories"
        >
          <option value="">All Categories</option>
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
          title="Clear category filter"
        >
          <i class="fas fa-times"></i>
        </button>
        <span v-if="loadingCategories" class="loading-indicator">
          <i class="fas fa-spinner fa-spin"></i>
        </span>
      </div>
      <span v-if="selectedCategory" class="active-filter-badge">
        Filtering: {{ formatCategory(selectedCategory) }}
      </span>
      <div v-if="categoriesError" class="categories-error">
        <i class="fas fa-exclamation-triangle"></i>
        {{ categoriesError }}
        <button @click="loadCategories" class="retry-button">
          <i class="fas fa-redo"></i> Retry
        </button>
      </div>
    </div>

    <!-- Issue #685: Access Level Filter -->
    <div class="access-level-filter">
      <label class="filter-label">
        <i class="fas fa-shield-alt"></i>
        Filter by Access Level:
      </label>
      <div class="filter-chips">
        <button
          v-for="level in accessLevels"
          :key="level.value"
          :class="['filter-chip', { active: selectedAccessLevel === level.value }]"
          @click="toggleAccessLevel(level.value)"
        >
          <i :class="level.icon"></i>
          {{ level.label }}
        </button>
        <button
          v-if="selectedAccessLevel"
          @click="clearAccessLevelFilter"
          class="clear-chip"
          title="Clear access level filter"
        >
          <i class="fas fa-times"></i>
          Clear
        </button>
      </div>
    </div>

    <!-- Search Input -->
    <div class="search-input-container">
      <div class="search-input-wrapper">
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="useRagSearch ? 'Ask questions about your knowledge... (e.g., Summarize key findings about...)' : 'Search knowledge base... (try keywords, questions, or topics)'"
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
          {{ isSearching ? 'Searching...' : 'Search' }}
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
            Auto-enhance query for better results
          </label>
        </div>
        <div class="option-group">
          <label>
            <input
              v-model="ragOptions.enableReranking"
              type="checkbox"
            >
            <span class="reranking-label">
              Enable neural reranking
              <span class="reranking-badge">Slower but more accurate</span>
            </span>
          </label>
        </div>
        <div class="option-group">
          <label>
            Results limit:
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
            <i class="fas fa-brain rag-icon"></i>
            AI Synthesis
          </h4>
          <div v-if="ragResponse.rag_analysis" class="analysis-badges">
            <span class="confidence-badge" :class="getConfidenceBadgeClass(ragResponse.rag_analysis.confidence)">
              {{ Math.round(ragResponse.rag_analysis.confidence * 100) }}% confidence
            </span>
            <span class="sources-badge">
              {{ ragResponse.rag_analysis.sources_used }} sources
            </span>
          </div>
        </div>

        <div class="synthesis-content">
          <p>{{ ragResponse.synthesized_response }}</p>
        </div>

        <div v-if="ragResponse.reformulated_query && ragResponse.reformulated_query !== ragResponse.query" class="query-reformulation">
          <p class="reformulated-note">
            <i class="fas fa-lightbulb"></i>
            Enhanced query: "{{ ragResponse.reformulated_query }}"
          </p>
        </div>
      </div>

      <!-- Traditional Results Header -->
      <div v-if="hasSearchResults" class="results-header">
        <h4>
          Found {{ searchResults.length }} results for "{{ lastSearchQuery }}"
          <span v-if="useRagSearch" class="rag-enhanced-label">
            <i class="fas fa-brain"></i>
            RAG Enhanced
          </span>
        </h4>
      </div>

      <!-- Results List -->
      <div v-if="hasSearchResults" class="results-list">
        <div
          v-for="(result, index) in searchResults"
          :key="result?.document?.id || `result-${index}`"
          class="result-item"
          @click="openDocument(result.document)"
        >
          <div v-if="result && result.document" class="result-header">
            <h5 class="result-title">{{ result.document.title || 'Knowledge Document' }}</h5>
            <div class="score-badges">
              <span class="result-score" :class="getScoreClass(result.score)">
                {{ Math.round(result.score * 100) }}% match
              </span>
              <span v-if="result.rerank_score" class="rerank-score" :class="getScoreClass(result.rerank_score)">
                <i class="fas fa-brain"></i>
                Rerank: {{ Math.round(result.rerank_score * 100) }}%
              </span>
            </div>
          </div>
          <div v-if="result && result.document" class="result-meta">
            <span class="result-type">
              <i class="fas fa-file-text"></i>
              {{ result.document.type || 'text' }}
            </span>
            <span class="result-category">{{ result.document.category || 'general' }}</span>
            <!-- Issue #685: Access level badge -->
            <span v-if="getAccessLevel(result.document)" class="access-level-badge" :class="`access-${getAccessLevel(result.document)}`">
              <i :class="getAccessLevelIcon(result.document)"></i>
              {{ formatAccessLevel(result.document) }}
            </span>
          </div>
          <div v-if="result && result.document" class="result-content">
            <p>{{ result.highlights?.[0] || (result.document.content ? result.document.content.substring(0, 200) + '...' : 'No content') }}</p>
          </div>
          <div class="result-footer">
            <span class="click-hint">
              <i class="fas fa-hand-pointer"></i>
              Click to view full document
            </span>
          </div>
        </div>
      </div>

      <!-- Document Viewer Modal -->
      <BaseModal
        v-model="showDocumentModal"
        :title="selectedDocument?.title || 'Document'"
        size="large"
        scrollable
      >
        <div class="document-modal-meta">
          <span class="modal-meta-item">
            <i class="fas fa-file-text"></i>
            {{ selectedDocument?.type || 'text' }}
          </span>
          <span class="modal-meta-item">
            <i class="fas fa-folder"></i>
            {{ selectedDocument?.category || 'general' }}
          </span>
          <span v-if="selectedDocument?.updatedAt" class="modal-meta-item">
            <i class="fas fa-clock"></i>
            {{ new Date(selectedDocument.updatedAt).toLocaleDateString() }}
          </span>
        </div>

        <div v-if="loadingDocument" class="modal-loading">
          <i class="fas fa-spinner fa-spin"></i>
          Loading document...
        </div>
        <div v-else-if="selectedDocument?.content" class="document-text">
          {{ selectedDocument.content }}
        </div>
        <div v-else class="modal-no-content">
          <i class="fas fa-file-excel"></i>
          <p>No content available for this document</p>
        </div>

        <template #actions>
          <button @click="copyDocument" class="modal-action-button">
            <i class="fas fa-copy"></i>
            Copy Content
          </button>
          <button @click="closeDocument" class="modal-action-button modal-close-action">
            Close
          </button>
        </template>
      </BaseModal>

      <!-- No Results -->
      <EmptyState
        v-if="!hasSearchResults"
        icon="fas fa-search"
        message="No documents found matching your search."
      >
        <p class="no-results-hint">
          {{ useRagSearch
            ? 'Try rephrasing your question or using different keywords.'
            : 'Try using different keywords or check your filters.'
          }}
        </p>
        <div class="initialization-help">
          <p><strong>Need to index your knowledge base?</strong></p>
          <p>Go to <router-link to="/knowledge/manage" class="help-link">Manage → System Knowledge</router-link> and click "Initialize Machine Knowledge" to create search indexes.</p>
        </div>
      </EmptyState>

      <!-- RAG Error Handling -->
      <div v-if="useRagSearch && ragError" class="rag-error">
        <div class="error-header">
          <i class="fas fa-exclamation-triangle"></i>
          RAG Enhancement Unavailable
        </div>
        <p>{{ ragError }}</p>
        <p class="fallback-note">Showing traditional search results instead.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { KnowledgeRepository, type RagSearchResponse } from '@/models/repositories'
import type { KnowledgeDocument, SearchResult } from '@/stores/useKnowledgeStore'
import type { KnowledgeCategoryItem } from '@/types/knowledgeBase'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeSearch')

// Repository instance
const knowledgeRepo = new KnowledgeRepository()

// Knowledge base composable for category fetching
const { fetchCategories, formatCategory } = useKnowledgeBase()

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
const accessLevels = [
  { value: 'autobot', label: 'Platform', icon: 'fas fa-robot' },
  { value: 'general', label: 'Public', icon: 'fas fa-globe' },
  { value: 'system', label: 'System', icon: 'fas fa-cog' },
  { value: 'user', label: 'User', icon: 'fas fa-user' }
]

// Document viewer state
const showDocumentModal = ref(false)
const selectedDocument = ref<KnowledgeDocument | null>(null)
const loadingDocument = ref(false)

// RAG Options
const ragOptions = ref({
  reformulateQuery: true,
  enableReranking: true,
  limit: 10
})

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
const toggleAccessLevel = async (level: string) => {
  selectedAccessLevel.value = selectedAccessLevel.value === level ? '' : level
  // Re-run search with new access level filter
  if (searchPerformed.value && searchQuery.value.trim()) {
    await handleSearch()
  }
}

const clearAccessLevelFilter = async () => {
  selectedAccessLevel.value = ''
  // Re-run search to show unfiltered results
  if (searchPerformed.value && searchQuery.value.trim()) {
    await handleSearch()
  }
}

const getScoreClass = (score: number) => {
  if (score >= 0.8) return 'score-high'
  if (score >= 0.6) return 'score-medium'
  return 'score-low'
}

const getConfidenceBadgeClass = (confidence: number) => {
  if (confidence >= 0.8) return 'confidence-high'
  if (confidence >= 0.6) return 'confidence-medium'
  return 'confidence-low'
}

// Issue #685: Access level badge helpers
const getAccessLevel = (document: KnowledgeDocument): string | null => {
  // Check both document properties and metadata
  const level = (document as any).access_level || (document as any).metadata?.access_level
  return level || null
}

const formatAccessLevel = (document: KnowledgeDocument): string => {
  const level = getAccessLevel(document)
  if (!level) return ''

  const labels: Record<string, string> = {
    'autobot': 'Platform',
    'general': 'Public',
    'system': 'System',
    'user': 'User'
  }
  return labels[level] || level.charAt(0).toUpperCase() + level.slice(1)
}

const getAccessLevelIcon = (document: KnowledgeDocument): string => {
  const level = getAccessLevel(document)
  const icons: Record<string, string> = {
    'autobot': 'fas fa-robot',
    'general': 'fas fa-globe',
    'system': 'fas fa-cog',
    'user': 'fas fa-user'
  }
  return icons[level || ''] || 'fas fa-file'
}

// Document viewer methods
const openDocument = async (document: KnowledgeDocument) => {
  if (!document || !document.id) return

  showDocumentModal.value = true
  loadingDocument.value = true

  try {
    // Fetch full document if content is not available or truncated
    if (!document.content || document.content.length < 300) {
      const fullDocument = await knowledgeRepo.getDocument(document.id)
      selectedDocument.value = fullDocument as unknown as KnowledgeDocument
    } else {
      selectedDocument.value = document
    }
  } catch (error) {
    logger.error('Failed to load document:', error)
    selectedDocument.value = document // Show what we have
  } finally {
    loadingDocument.value = false
  }
}

const closeDocument = () => {
  showDocumentModal.value = false
  selectedDocument.value = null
}

const copyDocument = async () => {
  if (!selectedDocument.value?.content) return

  try {
    await navigator.clipboard.writeText(selectedDocument.value.content)
    // Could add a toast notification here
    logger.debug('Document content copied to clipboard')
  } catch (error) {
    logger.error('Failed to copy document:', error)
  }
}
</script>

<style scoped>
.knowledge-search {
  @apply p-4 bg-white rounded-lg shadow-sm border;
}

.search-header {
  @apply mb-6;
}

.search-header h3 {
  @apply text-lg font-semibold text-gray-900 mb-1;
}

.search-header p {
  @apply text-sm text-gray-600;
}

/* Search Mode Toggle */
.search-mode-toggle {
  @apply mb-4;
}

/* Category Filter */
.category-filter {
  @apply mb-4 p-3 bg-gray-50 rounded-lg border border-gray-200;
}

.filter-label {
  @apply text-sm font-medium text-gray-700 flex items-center gap-2 mb-2;
}

.filter-label i {
  @apply text-gray-500;
}

.filter-controls {
  @apply flex items-center gap-2;
}

.category-select {
  @apply flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white;
}

.category-select:disabled {
  @apply bg-gray-100 cursor-not-allowed;
}

.clear-filter-button {
  @apply p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors;
}

.loading-indicator {
  @apply text-gray-400 text-sm;
}

.active-filter-badge {
  @apply inline-block mt-2 px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full;
}

.categories-error {
  @apply mt-2 p-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2;
}

.categories-error i {
  @apply text-red-500;
}

.retry-button {
  @apply ml-auto px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors flex items-center gap-1;
}

/* Issue #685: Access Level Filter */
.access-level-filter {
  @apply mb-4 p-3 bg-gray-50 rounded-lg border border-gray-200;
}

.filter-chips {
  @apply flex flex-wrap gap-2;
}

.filter-chip {
  @apply px-3 py-1.5 text-sm font-medium rounded-full border-2 transition-all flex items-center gap-1.5;
  @apply border-gray-300 bg-white text-gray-700 hover:bg-gray-50;
}

.filter-chip.active {
  @apply border-blue-500 bg-blue-50 text-blue-700;
}

.filter-chip i {
  @apply text-xs;
}

.clear-chip {
  @apply px-3 py-1.5 text-sm font-medium rounded-full border-2 transition-all flex items-center gap-1.5;
  @apply border-red-300 bg-white text-red-600 hover:bg-red-50 hover:border-red-400;
}

.toggle-container {
  @apply flex bg-gray-100 rounded-lg p-1 mb-2;
}

.mode-button {
  @apply flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 flex items-center justify-center gap-2;
}

.mode-button:not(.active) {
  @apply text-gray-600 hover:text-gray-900;
}

.mode-button.active {
  @apply bg-white text-gray-900 shadow-sm;
}

.mode-button.rag-button.active {
  @apply bg-blue-500 text-white;
}

.mode-description {
  @apply text-xs text-gray-500 px-2;
}

.rag-desc {
  @apply text-blue-600;
}

/* RAG Options */
.rag-options {
  @apply mt-3 p-3 bg-blue-50 rounded-lg border border-blue-100;
}

.option-group {
  @apply flex items-center gap-2 text-sm text-gray-700;
}

.option-group + .option-group {
  @apply mt-2;
}

.limit-select {
  @apply ml-2 px-2 py-1 border border-gray-300 rounded text-xs;
}

.reranking-label {
  @apply flex items-center gap-2;
}

.reranking-badge {
  @apply text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-normal;
}

/* Search Input */
.search-input-container {
  @apply mb-6;
}

.search-input-wrapper {
  @apply flex gap-2;
}

.search-input {
  @apply flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent;
}

.search-button {
  @apply px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2;
}

/* RAG Synthesis */
.rag-synthesis {
  @apply mb-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200;
}

.synthesis-header {
  @apply flex justify-between items-start mb-3;
}

.synthesis-header h4 {
  @apply text-lg font-semibold text-blue-900 flex items-center gap-2;
}

.rag-icon {
  @apply text-blue-600;
}

.analysis-badges {
  @apply flex gap-2;
}

.confidence-badge, .sources-badge {
  @apply px-2 py-1 rounded-full text-xs font-medium;
}

.confidence-high {
  @apply bg-green-100 text-green-800;
}

.confidence-medium {
  @apply bg-yellow-100 text-yellow-800;
}

.confidence-low {
  @apply bg-red-100 text-red-800;
}

.sources-badge {
  @apply bg-blue-100 text-blue-800;
}

.synthesis-content {
  @apply prose prose-sm max-w-none;
}

.synthesis-content p {
  @apply text-gray-800 leading-relaxed;
}

.query-reformulation {
  @apply mt-3 pt-3 border-t border-blue-200;
}

.reformulated-note {
  @apply text-sm text-blue-700 flex items-center gap-2;
}

/* Results */
.search-results {
  @apply space-y-4;
}

.results-header h4 {
  @apply text-base font-medium text-gray-900 flex items-center gap-2;
}

.rag-enhanced-label {
  @apply px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full flex items-center gap-1;
}

.results-list {
  @apply space-y-3;
}

.result-item {
  @apply p-4 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer;
}

.result-header {
  @apply flex justify-between items-start mb-2;
}

.result-title {
  @apply font-medium text-gray-900;
}

.score-badges {
  @apply flex items-center gap-2;
}

.result-score {
  @apply text-xs px-2 py-1 rounded-full;
}

.rerank-score {
  @apply text-xs px-2 py-1 rounded-full flex items-center gap-1;
}

.rerank-score i {
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

.result-meta {
  @apply flex gap-4 text-xs text-gray-500 mb-2;
}

/* Issue #685: Access level badge styles */
.access-level-badge {
  @apply inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium;
}

.access-level-badge.access-autobot {
  @apply bg-purple-100 text-purple-700;
}

.access-level-badge.access-general {
  @apply bg-green-100 text-green-700;
}

.access-level-badge.access-system {
  @apply bg-blue-100 text-blue-700;
}

.access-level-badge.access-user {
  @apply bg-gray-100 text-gray-700;
}

.access-level-badge i {
  @apply text-xs;
}

.result-content p {
  @apply text-sm text-gray-700 line-clamp-2;
}

/* No Results */
.no-results-hint {
  @apply text-sm text-gray-500 mt-2;
}

.initialization-help {
  @apply mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg;
}

.initialization-help p {
  @apply text-sm text-blue-800 mb-1;
}

.initialization-help strong {
  @apply font-semibold;
}

.help-link {
  @apply text-blue-600 hover:text-blue-800 underline font-medium;
}

/* RAG Error */
.rag-error {
  @apply mt-4 p-4 bg-orange-50 border border-orange-200 rounded-lg;
}

.error-header {
  @apply flex items-center gap-2 font-medium text-orange-800 mb-2;
}

.rag-error p {
  @apply text-orange-700 text-sm;
}

.fallback-note {
  @apply mt-2 text-orange-600 text-xs font-medium;
}

/* Result Footer with Click Hint */
.result-footer {
  @apply mt-3 pt-2 border-t border-gray-100;
}

.click-hint {
  @apply text-xs text-blue-600 flex items-center gap-1 font-medium;
}

.click-hint i {
  @apply text-blue-500;
}

/* Document Viewer Modal - Content Styles */
.document-modal-meta {
  @apply flex gap-4 text-sm text-gray-600;
}

.modal-meta-item {
  @apply flex items-center gap-1;
}

.modal-meta-item i {
  @apply text-gray-400;
}

.modal-loading {
  @apply flex flex-col items-center justify-center py-12 text-gray-500;
}

.modal-loading i {
  @apply text-3xl mb-3 text-blue-500;
}

.document-text {
  @apply prose prose-sm max-w-none text-gray-800 whitespace-pre-wrap;
}

.modal-no-content {
  @apply flex flex-col items-center justify-center py-12 text-gray-400;
}

.modal-no-content i {
  @apply text-4xl mb-3;
}

.modal-no-content p {
  @apply text-gray-500;
}

.modal-action-button {
  @apply px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2;
}

.modal-action-button:not(.modal-close-action) {
  @apply bg-blue-600 text-white hover:bg-blue-700;
}

.modal-close-action {
  @apply bg-gray-200 text-gray-700 hover:bg-gray-300;
}

.modal-action-button i {
  @apply text-sm;
}
</style>
