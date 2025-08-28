<template>
  <div class="knowledge-search">
    <div class="search-header">
      <h3>Search Knowledge Base</h3>
      <button
        @click="controller.toggleAdvancedSearch()"
        class="toggle-advanced-btn"
        :class="{ 'active': store.showAdvancedSearch }"
      >
        {{ store.showAdvancedSearch ? 'Simple Search' : 'Advanced Search' }}
      </button>
    </div>

    <div class="search-form">
      <!-- Main search input with enhanced UX -->
      <div class="search-input-container">
        <div class="search-input-wrapper">
          <input
            v-model="store.searchQuery"
            type="text"
            placeholder="Search knowledge base... (try keywords, questions, or topics)"
            @keyup.enter="handleSearch"
            @input="handleSearchInput"
            @focus="showSearchHelp = true"
            @blur="hideSearchHelp"
            class="main-search-input enhanced"
            id="knowledge-search-input"
            autocomplete="off"
            spellcheck="false"
          />
          <div class="search-input-icons">
            <i v-if="store.searching" class="fas fa-spinner fa-spin search-spinner"></i>
            <i v-else-if="store.searchQuery" @click="controller.clearSearch()" class="fas fa-times clear-search" title="Clear search"></i>
            <i v-else class="fas fa-search search-icon"></i>
          </div>
        </div>
        <button
          @click="handleSearch"
          :disabled="store.searching || !store.searchQuery.trim()"
          class="search-btn enhanced"
          :class="{ 'searching': store.searching }"
        >
          {{ store.searching ? 'Searching...' : 'Search' }}
        </button>
      </div>

      <!-- Search help tooltip -->
      <div v-if="showSearchHelp && !store.searchQuery" class="search-help-tooltip">
        <div class="help-item">
          <strong>💡 Search Tips:</strong>
        </div>
        <div class="help-item">• Use quotes for exact phrases: "machine learning"</div>
        <div class="help-item">• Use wildcards: config* or *setup</div>
        <div class="help-item">• Try natural questions: "How to configure Redis?"</div>
      </div>

      <!-- Enhanced search suggestions with categories -->
      <div v-if="store.showSuggestions && store.searchSuggestions.length > 0" class="search-suggestions enhanced">
        <div class="suggestions-header">
          <i class="fas fa-lightbulb"></i>
          <span>Suggested searches</span>
        </div>
        <div class="suggestions-list">
          <div
            v-for="(suggestion, index) in store.searchSuggestions"
            :key="suggestion"
            @click="applySuggestion(suggestion)"
            @keyup.enter="applySuggestion(suggestion)"
            class="suggestion-item enhanced"
            :class="{ 'highlighted': index === selectedSuggestionIndex }"
            tabindex="0"
          >
            <i class="fas fa-search suggestion-icon"></i>
            <span class="suggestion-text">{{ suggestion }}</span>
          </div>
        </div>
      </div>

      <!-- Advanced search filters -->
      <div v-if="store.showAdvancedSearch" class="advanced-search">
        <div class="filter-row">
          <div class="filter-group">
            <label>Categories</label>
            <select v-model="selectedCategories" multiple class="filter-select">
              <option v-for="category in store.categories" :key="category.id" :value="category.name">
                {{ category.name }} ({{ category.documentCount }})
              </option>
            </select>
          </div>
          <div class="filter-group">
            <label>Tags</label>
            <select v-model="selectedTags" multiple class="filter-select">
              <option v-for="tag in store.allTags" :key="tag" :value="tag">
                {{ tag }}
              </option>
            </select>
          </div>
          <div class="filter-group">
            <label>Document Type</label>
            <select v-model="selectedTypes" multiple class="filter-select">
              <option value="document">Documents</option>
              <option value="webpage">Web Pages</option>
              <option value="api">API Docs</option>
              <option value="upload">Uploads</option>
            </select>
          </div>
          <div class="filter-group">
            <label>Date Range</label>
            <input type="date" v-model="dateFrom" class="filter-input" />
            <span>to</span>
            <input type="date" v-model="dateTo" class="filter-input" />
          </div>
        </div>
        <div class="filter-actions">
          <button @click="applyFilters" class="apply-filters-btn">
            Apply Filters
          </button>
          <button @click="clearFilters" class="clear-filters-btn">
            Clear All
          </button>
        </div>
      </div>
    </div>

    <!-- Search Results -->
    <div v-if="store.hasSearchResults || searchPerformed" class="search-results-section">
      <div class="results-header">
        <h4>
          {{ store.hasSearchResults ? `Found ${store.searchResults.length} results` : 'No results found' }}
          <span v-if="lastSearchQuery" class="search-query-display">for "{{ lastSearchQuery }}"</span>
        </h4>
        <div v-if="store.hasSearchResults" class="results-actions">
          <button @click="exportResults" class="export-btn" title="Export results">
            <i class="fas fa-download"></i> Export
          </button>
          <button @click="clearResults" class="clear-results-btn" title="Clear results">
            <i class="fas fa-times"></i> Clear
          </button>
        </div>
      </div>

      <div v-if="store.hasSearchResults" class="results-list">
        <div
          v-for="result in store.searchResults"
          :key="result.document.id"
          class="result-item"
          @click="selectDocument(result.document)"
        >
          <div class="result-header">
            <h5 class="result-title">{{ result.document.title || 'Untitled' }}</h5>
            <span class="result-score" :class="getScoreClass(result.score)">
              {{ Math.round(result.score * 100) }}% match
            </span>
          </div>
          <div class="result-meta">
            <span class="result-type">
              <i :class="getTypeIcon(result.document.type)"></i>
              {{ result.document.type }}
            </span>
            <span class="result-category">{{ result.document.category }}</span>
            <span class="result-date">{{ formatDate(result.document.updatedAt) }}</span>
          </div>
          <div class="result-content">
            <p v-html="highlightSearchTerms(result.highlights[0] || result.document.content)"></p>
          </div>
          <div v-if="result.document.tags.length > 0" class="result-tags">
            <span v-for="tag in result.document.tags" :key="tag" class="tag-chip">
              {{ tag }}
            </span>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'

// Store and controller
const store = useKnowledgeStore()
const controller = useKnowledgeController()

// Local UI state
const showSearchHelp = ref(false)
const selectedSuggestionIndex = ref(-1)
const searchPerformed = ref(false)
const lastSearchQuery = ref('')

// Advanced search filters
const selectedCategories = ref<string[]>([])
const selectedTags = ref<string[]>([])
const selectedTypes = ref<string[]>([])
const dateFrom = ref('')
const dateTo = ref('')

// Methods
const handleSearch = async () => {
  searchPerformed.value = true
  lastSearchQuery.value = store.searchQuery
  await controller.performSearch()
}

const handleSearchInput = (event: Event) => {
  const query = (event.target as HTMLInputElement).value
  if (query.length >= 3) {
    controller.getSearchSuggestions(query)
  } else {
    store.showSuggestions = false
  }
}

const hideSearchHelp = () => {
  setTimeout(() => {
    showSearchHelp.value = false
  }, 200)
}

const applySuggestion = (suggestion: string) => {
  store.updateSearchQuery(suggestion)
  handleSearch()
}

const applyFilters = () => {
  controller.updateFilters({
    categories: selectedCategories.value,
    tags: selectedTags.value,
    types: selectedTypes.value,
    dateRange: dateFrom.value && dateTo.value ? {
      start: new Date(dateFrom.value),
      end: new Date(dateTo.value)
    } : undefined
  })
  handleSearch()
}

const clearFilters = () => {
  selectedCategories.value = []
  selectedTags.value = []
  selectedTypes.value = []
  dateFrom.value = ''
  dateTo.value = ''
  controller.clearFilters()
}

const selectDocument = (document: KnowledgeDocument) => {
  store.selectDocument(document)
  // Emit event or navigate to document view
}

const exportResults = async () => {
  // Implementation for exporting search results
  const data = store.searchResults.map(r => ({
    title: r.document.title,
    content: r.document.content,
    score: r.score,
    category: r.document.category,
    tags: r.document.tags
  }))

  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `knowledge-search-results-${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const clearResults = () => {
  controller.clearSearch()
  searchPerformed.value = false
  lastSearchQuery.value = ''
}

// Utility functions
const getScoreClass = (score: number): string => {
  if (score >= 0.8) return 'score-high'
  if (score >= 0.5) return 'score-medium'
  return 'score-low'
}

const getTypeIcon = (type: string): string => {
  const icons: Record<string, string> = {
    document: 'fas fa-file-alt',
    webpage: 'fas fa-globe',
    api: 'fas fa-code',
    upload: 'fas fa-upload'
  }
  return icons[type] || 'fas fa-file'
}

const formatDate = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString()
}

const highlightSearchTerms = (text: string): string => {
  if (!store.searchQuery) return text

  const terms = store.searchQuery.split(/\s+/).filter(t => t.length > 2)
  let highlighted = text

  terms.forEach(term => {
    const regex = new RegExp(`(${term})`, 'gi')
    highlighted = highlighted.replace(regex, '<mark>$1</mark>')
  })

  return highlighted
}

// Load categories on mount
onMounted(() => {
  controller.loadCategories()
})

// Watch for filter changes in store
watch(() => store.filters, (newFilters) => {
  selectedCategories.value = newFilters.categories
  selectedTags.value = newFilters.tags
  selectedTypes.value = newFilters.types
})
</script>

<style scoped>
/* Component-specific styles here */
.knowledge-search {
  padding: 1rem;
}

.search-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.search-form {
  margin-bottom: 2rem;
}

.search-input-container {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.search-input-wrapper {
  flex: 1;
  position: relative;
}

.main-search-input {
  width: 100%;
  padding: 0.75rem 2.5rem 0.75rem 1rem;
  border: 2px solid #e0e0e0;
  border-radius: 0.5rem;
  font-size: 1rem;
  transition: all 0.3s ease;
}

.main-search-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.search-input-icons {
  position: absolute;
  right: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.search-btn {
  padding: 0.75rem 1.5rem;
  background-color: #3b82f6;
  color: white;
  border: none;
  border-radius: 0.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.search-btn:hover:not(:disabled) {
  background-color: #2563eb;
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Additional styles for other elements... */
</style>
