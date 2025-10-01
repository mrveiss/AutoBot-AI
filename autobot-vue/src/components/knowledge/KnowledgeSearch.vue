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
          v-for="result in searchResults"
          :key="result.document.id"
          class="result-item"
        >
          <div class="result-header">
            <h5 class="result-title">{{ result.document.title || 'Knowledge Document' }}</h5>
            <span class="result-score" :class="getScoreClass(result.score)">
              {{ Math.round(result.score * 100) }}% match
            </span>
          </div>
          <div class="result-meta">
            <span class="result-type">
              <i class="fas fa-file-text"></i>
              {{ result.document.type || 'text' }}
            </span>
            <span class="result-category">{{ result.document.category || 'general' }}</span>
          </div>
          <div class="result-content">
            <p>{{ result.highlights[0] || result.document.content.substring(0, 200) + '...' }}</p>
          </div>
        </div>
      </div>

      <!-- No Results -->
      <div v-else class="no-results">
        <i class="fas fa-search no-results-icon"></i>
        <p>No documents found matching your search.</p>
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
      </div>

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
import { ref, computed } from 'vue'
import { KnowledgeRepository, type RagSearchResponse } from '@/models/repositories/KnowledgeRepository'

// Define types
interface KnowledgeDocument {
  id: string
  title: string
  content: string
  type: string
  category: string
  updatedAt: string
  tags: string[]
}

interface SearchResult {
  document: KnowledgeDocument
  score: number
  highlights: string[]
}

// Repository instance
const knowledgeRepo = new KnowledgeRepository()

// State
const searchQuery = ref('')
const searchResults = ref<SearchResult[]>([])
const ragResponse = ref<RagSearchResponse | null>(null)
const ragError = ref<string | null>(null)
const isSearching = ref(false)
const searchPerformed = ref(false)
const lastSearchQuery = ref('')
const useRagSearch = ref(false)

// RAG Options
const ragOptions = ref({
  reformulateQuery: true,
  limit: 10
})

// Computed
const hasSearchResults = computed(() => searchResults.value.length > 0)

// Methods
const handleSearch = async () => {
  if (!searchQuery.value.trim()) return

  isSearching.value = true
  ragError.value = null
  ragResponse.value = null

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
          searchResults.value = ragResponse.value.results
        }
      } catch (ragErr: any) {
        ragError.value = ragErr.message || 'RAG functionality is currently unavailable'

        // Fallback to traditional search
        const results = await knowledgeRepo.searchKnowledge({
          query: searchQuery.value,
          limit: ragOptions.value.limit,
          use_rag: false
        })
        searchResults.value = results
      }
    } else {
      // Use traditional search
      const results = await knowledgeRepo.searchKnowledge({
        query: searchQuery.value,
        limit: 20,
        use_rag: false
      })
      searchResults.value = results
    }
  } catch (error) {
    console.error('Knowledge search failed:', error)
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

.result-score {
  @apply text-xs px-2 py-1 rounded-full;
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

.result-content p {
  @apply text-sm text-gray-700 line-clamp-2;
}

/* No Results */
.no-results {
  @apply text-center py-8;
}

.no-results-icon {
  @apply text-gray-400 text-3xl mb-4;
}

.no-results p {
  @apply text-gray-600;
}

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
</style>