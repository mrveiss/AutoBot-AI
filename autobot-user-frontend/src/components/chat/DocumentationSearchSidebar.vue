<template>
  <div class="doc-search-sidebar" :class="{ 'collapsed': isCollapsed }">
    <!-- Sidebar Toggle -->
    <button
      class="sidebar-toggle"
      @click="toggleSidebar"
      :aria-expanded="!isCollapsed"
      aria-label="Toggle documentation sidebar"
    >
      <i :class="isCollapsed ? 'fas fa-chevron-left' : 'fas fa-chevron-right'" aria-hidden="true"></i>
    </button>

    <div v-if="!isCollapsed" class="sidebar-content">
      <!-- Header -->
      <div class="sidebar-header">
        <h3 class="sidebar-title">
          <i class="fas fa-book-open" aria-hidden="true"></i>
          Documentation
        </h3>
        <button
          class="close-btn"
          @click="$emit('close')"
          aria-label="Close documentation sidebar"
        >
          <i class="fas fa-times" aria-hidden="true"></i>
        </button>
      </div>

      <!-- Search Input -->
      <div class="search-section">
        <div class="search-input-wrapper">
          <i class="fas fa-search search-icon" aria-hidden="true"></i>
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="Search documentation..."
            @input="handleSearch"
            @keydown.enter="executeSearch"
            aria-label="Search documentation"
          />
          <button
            v-if="searchQuery"
            class="clear-search-btn"
            @click="clearSearch"
            aria-label="Clear search"
          >
            <i class="fas fa-times" aria-hidden="true"></i>
          </button>
        </div>
      </div>

      <!-- Category Filter -->
      <DocumentationCategoryFilter
        v-if="categories.length > 0"
        :categories="categories"
        v-model:selectedCategories="selectedCategories"
        :is-loading="isLoadingCategories"
        @category-change="handleCategoryChange"
        class="category-filter-section"
      />

      <!-- Results Section -->
      <div class="results-section">
        <div class="results-header">
          <span class="results-count">
            {{ results.length }} result{{ results.length !== 1 ? 's' : '' }}
          </span>
          <div class="sort-controls">
            <select
              v-model="sortBy"
              class="sort-select"
              aria-label="Sort results by"
              @change="handleSortChange"
            >
              <option value="relevance">Relevance</option>
              <option value="title">Title</option>
              <option value="category">Category</option>
              <option value="date">Date</option>
            </select>
          </div>
        </div>

        <!-- Loading State -->
        <div v-if="isSearching" class="loading-state">
          <i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
          <span>Searching...</span>
        </div>

        <!-- Results List -->
        <div v-else-if="results.length > 0" class="results-list">
          <DocumentationResultCard
            v-for="result in results"
            :key="result.id || result.contentHash"
            :title="result.title"
            :content="result.content"
            :category="result.category"
            :section="result.section"
            :file-path="result.filePath"
            :score="result.score"
            @click="handleResultClick(result)"
            @insert="handleInsert(result)"
            @copy="handleCopy(result)"
            @open="handleOpen(result)"
            class="result-item"
          />

          <!-- Load More -->
          <button
            v-if="hasMore"
            class="load-more-btn"
            @click="loadMore"
            :disabled="isLoadingMore"
          >
            <i v-if="isLoadingMore" class="fas fa-spinner fa-spin" aria-hidden="true"></i>
            <span>{{ isLoadingMore ? 'Loading...' : 'Load more' }}</span>
          </button>
        </div>

        <!-- Empty State -->
        <div v-else class="empty-state">
          <i class="fas fa-file-alt" aria-hidden="true"></i>
          <p v-if="searchQuery">No results found for "{{ searchQuery }}"</p>
          <p v-else>Search AutoBot documentation</p>
          <div v-if="!searchQuery" class="quick-searches">
            <span class="quick-search-label">Quick searches:</span>
            <div class="quick-search-chips">
              <DocumentationSuggestionChip
                v-for="suggestion in quickSearches"
                :key="suggestion"
                :label="suggestion"
                @click="quickSearch(suggestion)"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Recent Docs -->
      <div v-if="recentDocs.length > 0 && !searchQuery" class="recent-section">
        <h4 class="section-title">Recent Documents</h4>
        <div class="recent-list">
          <button
            v-for="doc in recentDocs"
            :key="doc.id"
            class="recent-item"
            @click="openRecentDoc(doc)"
          >
            <i :class="getCategoryIcon(doc.category)" aria-hidden="true"></i>
            <span class="recent-title">{{ doc.title }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Documentation Search Sidebar Component
 *
 * Provides a collapsible sidebar for searching and browsing
 * documentation within the chat interface.
 *
 * Issue #165: Chat Documentation UI Integration
 */

import { ref, computed, onMounted, watch } from 'vue'
import DocumentationResultCard from './DocumentationResultCard.vue'
import DocumentationSuggestionChip from './DocumentationSuggestionChip.vue'
import DocumentationCategoryFilter from './DocumentationCategoryFilter.vue'
import { useApi } from '@/composables/useApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DocumentationSearchSidebar')

interface DocResult {
  id?: string
  contentHash?: string
  title: string
  content: string
  category: string
  section?: string
  filePath: string
  score?: number
}

interface Category {
  id: string
  name: string
  description?: string
  count: number
}

interface RecentDoc {
  id: string
  title: string
  category: string
  filePath: string
}

interface Props {
  initiallyOpen?: boolean
}

interface Emits {
  (e: 'close'): void
  (e: 'insert', content: string): void
  (e: 'result-click', result: DocResult): void
  (e: 'visibility-change', visible: boolean): void
}

const props = withDefaults(defineProps<Props>(), {
  initiallyOpen: true
})

const emit = defineEmits<Emits>()

const { apiClient, parseApiResponse } = useApi() as any

// State
const isCollapsed = ref(!props.initiallyOpen)
const searchQuery = ref('')
const selectedCategories = ref<string[]>([])
const sortBy = ref('relevance')
const results = ref<DocResult[]>([])
const categories = ref<Category[]>([])
const recentDocs = ref<RecentDoc[]>([])
const isSearching = ref(false)
const isLoadingCategories = ref(false)
const isLoadingMore = ref(false)
const hasMore = ref(false)
const currentPage = ref(1)
const searchDebounceTimeout = ref<number | null>(null)

// Quick search suggestions
const quickSearches = [
  'Redis configuration',
  'API endpoints',
  'Troubleshooting',
  'Agent setup',
  'Deployment'
]

// Category icons
const categoryIcons: Record<string, string> = {
  architecture: 'fas fa-project-diagram',
  developer: 'fas fa-code',
  api: 'fas fa-plug',
  troubleshooting: 'fas fa-wrench',
  deployment: 'fas fa-rocket',
  security: 'fas fa-shield-alt',
  features: 'fas fa-star',
  testing: 'fas fa-vial',
  workflow: 'fas fa-sitemap',
  guides: 'fas fa-book',
  implementation: 'fas fa-cogs',
  agents: 'fas fa-robot',
  general: 'fas fa-file-alt'
}

const getCategoryIcon = (category: string): string => {
  return categoryIcons[category] || categoryIcons.general
}

// Methods
const toggleSidebar = () => {
  isCollapsed.value = !isCollapsed.value
  emit('visibility-change', !isCollapsed.value)
}

const handleSearch = () => {
  // Debounce search
  if (searchDebounceTimeout.value) {
    clearTimeout(searchDebounceTimeout.value)
  }
  searchDebounceTimeout.value = window.setTimeout(() => {
    executeSearch()
  }, 300)
}

const executeSearch = async () => {
  if (!searchQuery.value.trim() && selectedCategories.value.length === 0) {
    results.value = []
    return
  }

  isSearching.value = true
  currentPage.value = 1

  try {
    const response = await apiClient.post('/api/knowledge_base/search', {
      query: searchQuery.value || '*',
      top_k: 20,
      filters: selectedCategories.value.length > 0
        ? { category: selectedCategories.value }
        : undefined
    })
    const data = await parseApiResponse(response)

    if (data?.results) {
      results.value = data.results.map((r: any) => ({
        id: r.node_id || r.doc_id,
        contentHash: r.metadata?.content_hash,
        title: r.metadata?.title || 'Untitled',
        content: r.content || '',
        category: r.metadata?.category || 'general',
        section: r.metadata?.section,
        filePath: r.metadata?.file_path || '',
        score: r.score || r.rrf_score
      }))
      hasMore.value = results.value.length >= 20
    }
  } catch (error) {
    logger.error('Search failed:', error)
    results.value = []
  } finally {
    isSearching.value = false
  }
}

const clearSearch = () => {
  searchQuery.value = ''
  results.value = []
}

const quickSearch = (query: string) => {
  searchQuery.value = query
  executeSearch()
}

const handleCategoryChange = () => {
  executeSearch()
}

const handleSortChange = () => {
  // Sort results locally
  const sortFns: Record<string, (a: DocResult, b: DocResult) => number> = {
    relevance: (a, b) => (b.score || 0) - (a.score || 0),
    title: (a, b) => a.title.localeCompare(b.title),
    category: (a, b) => a.category.localeCompare(b.category),
    date: (a, b) => 0 // Would need indexed_at field
  }
  results.value.sort(sortFns[sortBy.value] || sortFns.relevance)
}

const loadMore = async () => {
  if (isLoadingMore.value) return

  isLoadingMore.value = true
  currentPage.value++

  try {
    const response = await apiClient.post('/api/knowledge_base/docs/browse', {
      search_query: searchQuery.value,
      category: selectedCategories.value[0] || null,
      page: currentPage.value,
      page_size: 20
    })
    const data = await parseApiResponse(response)

    if (data?.documents) {
      const newResults = data.documents.map((d: any) => ({
        id: d.content_hash,
        title: d.title || 'Untitled',
        content: '',
        category: d.category || 'general',
        filePath: d.file_path || ''
      }))
      results.value = [...results.value, ...newResults]
      hasMore.value = newResults.length >= 20
    }
  } catch (error) {
    logger.error('Load more failed:', error)
  } finally {
    isLoadingMore.value = false
  }
}

const handleResultClick = (result: DocResult) => {
  addToRecent(result)
  emit('result-click', result)
}

const handleInsert = (result: DocResult) => {
  emit('insert', result.content)
}

const handleCopy = (result: DocResult) => {
  logger.info('Content copied:', result.title)
}

const handleOpen = (result: DocResult) => {
  logger.info('Opening document:', result.filePath)
}

const addToRecent = (doc: DocResult) => {
  const recentDoc: RecentDoc = {
    id: doc.id || doc.contentHash || '',
    title: doc.title,
    category: doc.category,
    filePath: doc.filePath
  }

  // Remove if already exists
  recentDocs.value = recentDocs.value.filter(d => d.id !== recentDoc.id)
  // Add to front
  recentDocs.value.unshift(recentDoc)
  // Keep only last 5
  recentDocs.value = recentDocs.value.slice(0, 5)

  // Persist to localStorage
  try {
    localStorage.setItem('autobot_recent_docs', JSON.stringify(recentDocs.value))
  } catch (e) {
    // Ignore storage errors
  }
}

const openRecentDoc = (doc: RecentDoc) => {
  emit('result-click', {
    id: doc.id,
    title: doc.title,
    content: '',
    category: doc.category,
    filePath: doc.filePath
  })
}

const loadCategories = async () => {
  isLoadingCategories.value = true
  try {
    const response = await apiClient.get('/api/knowledge_base/docs/categories')
    const data = await parseApiResponse(response)
    if (data?.categories) {
      categories.value = data.categories
    }
  } catch (error) {
    logger.error('Failed to load categories:', error)
  } finally {
    isLoadingCategories.value = false
  }
}

const loadRecentDocs = () => {
  try {
    const stored = localStorage.getItem('autobot_recent_docs')
    if (stored) {
      recentDocs.value = JSON.parse(stored)
    }
  } catch (e) {
    // Ignore parse errors
  }
}

// Watch for visibility changes
watch(isCollapsed, (collapsed) => {
  emit('visibility-change', !collapsed)
})

// Initialize
onMounted(() => {
  loadCategories()
  loadRecentDocs()
})
</script>

<style scoped>
/* Issue #704: Migrated to design tokens */

.doc-search-sidebar {
  position: relative;
  width: 320px;
  height: 100%;
  background: var(--bg-card);
  border-left: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  transition: width var(--duration-200) var(--ease-in-out);
}

.doc-search-sidebar.collapsed {
  width: 40px;
}

.sidebar-toggle {
  position: absolute;
  left: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 48px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-default) 0 0 var(--radius-default);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  z-index: var(--z-10);
  transition: var(--transition-all);
}

.sidebar-toggle:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-default);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: var(--transition-all);
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.search-section {
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: var(--spacing-3);
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.search-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-8) var(--spacing-2) var(--spacing-8);
  font-size: 0.8125rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: var(--transition-all);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-info);
  background: var(--bg-card);
  box-shadow: var(--shadow-focus);
}

.search-input::placeholder {
  color: var(--text-muted);
}

.clear-search-btn {
  position: absolute;
  right: var(--spacing-2);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition-all);
}

.clear-search-btn:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.category-filter-section {
  margin: var(--spacing-3);
}

.results-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2) var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
}

.results-count {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.sort-select {
  font-size: 0.6875rem;
  padding: var(--spacing-1) var(--spacing-2);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-default);
  background: var(--bg-card);
  color: var(--text-muted);
  cursor: pointer;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-8);
  color: var(--text-tertiary);
  font-size: 0.8125rem;
}

.results-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-2);
}

.result-item {
  margin-bottom: var(--spacing-2);
}

.load-more-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1-5);
  width: 100%;
  padding: var(--spacing-2-5);
  margin-top: var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-info);
  background: var(--color-info-bg);
  border: 1px solid var(--color-info);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-all);
}

.load-more-btn:hover:not(:disabled) {
  background: var(--color-info-bg-hover);
}

.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  text-align: center;
  color: var(--text-tertiary);
}

.empty-state i {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-3);
  opacity: 0.5;
}

.empty-state p {
  font-size: 0.8125rem;
  margin: 0 0 var(--spacing-4) 0;
}

.quick-searches {
  width: 100%;
}

.quick-search-label {
  display: block;
  font-size: 0.6875rem;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.quick-search-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1-5);
  justify-content: center;
}

.recent-section {
  padding: var(--spacing-3) var(--spacing-4);
  border-top: 1px solid var(--border-subtle);
}

.section-title {
  font-size: 0.6875rem;
  font-weight: var(--font-semibold);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0 0 var(--spacing-2) 0;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.recent-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  width: 100%;
  padding: var(--spacing-1-5) var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
  background: none;
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  text-align: left;
  transition: var(--transition-all);
}

.recent-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.recent-item i {
  color: var(--text-secondary);
  font-size: 0.625rem;
}

.recent-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Scrollbar styling */
.results-list::-webkit-scrollbar {
  width: 6px;
}

.results-list::-webkit-scrollbar-track {
  background: var(--scrollbar-track);
}

.results-list::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: var(--scrollbar-radius);
}

.results-list::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover);
}
</style>
