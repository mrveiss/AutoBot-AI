<template>
  <div class="knowledge-search">
    <div class="search-header">
      <h3>Knowledge Search</h3>
      <p>Search through your knowledge base documents, facts, and stored information</p>
    </div>

    <!-- Search Input -->
    <div class="search-input-container">
      <div class="search-input-wrapper">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search knowledge base... (try keywords, questions, or topics)"
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
    </div>

    <!-- Search Results -->
    <div v-if="searchPerformed" class="search-results">
      <div v-if="hasSearchResults" class="results-header">
        <h4>Found {{ searchResults.length }} results for "{{ lastSearchQuery }}"</h4>
      </div>

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

      <div v-else class="no-results">
        <i class="fas fa-search no-results-icon"></i>
        <p>No documents found matching your search.</p>
        <p class="no-results-hint">Try using different keywords or check your filters.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import apiClient from '@/utils/ApiClient'

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

// State
const searchQuery = ref('')
const searchResults = ref<SearchResult[]>([])
const isSearching = ref(false)
const searchPerformed = ref(false)
const lastSearchQuery = ref('')

// Computed
const hasSearchResults = computed(() => searchResults.value.length > 0)

// Methods
const handleSearch = async () => {
  if (!searchQuery.value.trim()) return
  
  isSearching.value = true
  try {
    const response = await apiClient.post('/api/knowledge_base/search', {
      query: searchQuery.value,
      limit: 20
    })
    
    if (response.ok) {
      const data = await response.json()
      searchResults.value = data.results || []
    }
  } catch (error) {
    console.error('Knowledge search failed:', error)
    searchResults.value = []
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

.search-results {
  @apply space-y-4;
}

.results-header h4 {
  @apply text-base font-medium text-gray-900;
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
</style>