<template>
  <div class="chroma-explorer">
    <!-- Header -->
    <div class="explorer-header">
      <div class="header-title">
        <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
        </svg>
        <h1>ChromaDB Explorer</h1>
      </div>
      <p class="header-subtitle">Browse and search vector collections at port 8100</p>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="error-alert" role="alert">
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = ''" :aria-label="'Close error'">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Main Content -->
    <div class="explorer-content">
      <!-- Collections List -->
      <div class="collections-panel" :class="{ collapsed: selectedCollection }">
        <div class="panel-header">
          <h2>Collections</h2>
          <button
            @click="loadCollections"
            :disabled="isLoading"
            class="refresh-btn"
            :aria-label="'Refresh collections'"
          >
            <svg :class="{ spinning: isLoading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        <div v-if="isLoading && collections.length === 0" class="loading-state">
          <div class="spinner"></div>
          <p>Loading collections...</p>
        </div>

        <div v-else-if="collections.length === 0" class="empty-state">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
          <p>No collections found</p>
        </div>

        <div v-else class="collections-list">
          <button
            v-for="collection in collections"
            :key="collection.name"
            @click="selectCollection(collection)"
            class="collection-item"
            :class="{ active: selectedCollection?.name === collection.name }"
          >
            <div class="collection-info">
              <span class="collection-name">{{ collection.name }}</span>
              <span class="collection-count">{{ collection.count }} documents</span>
            </div>
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Collection Details -->
      <div v-if="selectedCollection" class="details-panel">
        <!-- Collection Header -->
        <div class="details-header">
          <button @click="selectedCollection = null" class="back-btn">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
            </svg>
            <span>Back</span>
          </button>
          <h2>{{ selectedCollection.name }}</h2>
        </div>

        <!-- Collection Stats -->
        <div class="collection-stats">
          <div class="stat-card">
            <span class="stat-label">Documents</span>
            <span class="stat-value">{{ selectedCollection.count }}</span>
          </div>
          <div v-if="selectedCollection.metadata" class="stat-card">
            <span class="stat-label">Metadata</span>
            <span class="stat-value">{{ Object.keys(selectedCollection.metadata).length }} fields</span>
          </div>
        </div>

        <!-- Search Panel -->
        <div class="search-panel">
          <h3>Search Documents</h3>
          <div class="search-controls">
            <input
              v-model="searchQuery"
              @keyup.enter="performSearch"
              type="text"
              placeholder="Enter search query..."
              class="search-input"
            />
            <input
              v-model.number="searchLimit"
              type="number"
              min="1"
              max="100"
              placeholder="Results"
              class="search-limit"
            />
            <button
              @click="performSearch"
              :disabled="!searchQuery || isSearching"
              class="search-btn"
            >
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span>Search</span>
            </button>
          </div>

          <!-- Search Results -->
          <div v-if="searchResults.length > 0" class="search-results">
            <div class="results-header">
              <h4>{{ searchResults.length }} results</h4>
              <button @click="clearSearch" class="clear-btn">Clear</button>
            </div>
            <div
              v-for="result in searchResults"
              :key="result.id"
              class="search-result-item"
            >
              <div class="result-header">
                <span class="result-id">{{ result.id }}</span>
                <span v-if="result.distance !== null" class="result-distance">
                  {{ result.distance.toFixed(4) }}
                </span>
              </div>
              <p v-if="result.document" class="result-document">{{ result.document }}</p>
              <div v-if="result.metadata" class="result-metadata">
                <span class="metadata-label">Metadata:</span>
                <code>{{ JSON.stringify(result.metadata, null, 2) }}</code>
              </div>
            </div>
          </div>
        </div>

        <!-- Documents Browser -->
        <div class="documents-panel">
          <div class="panel-controls">
            <h3>Documents</h3>
            <div class="pagination-controls">
              <button
                @click="prevPage"
                :disabled="currentPage === 0 || isLoadingDocuments"
                class="page-btn"
              >
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <span class="page-info">
                Page {{ currentPage + 1 }} ({{ currentOffset + 1 }}-{{ Math.min(currentOffset + pageSize, selectedCollection.count) }} of {{ selectedCollection.count }})
              </span>
              <button
                @click="nextPage"
                :disabled="currentOffset + pageSize >= selectedCollection.count || isLoadingDocuments"
                class="page-btn"
              >
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>

          <div v-if="isLoadingDocuments" class="loading-state">
            <div class="spinner"></div>
            <p>Loading documents...</p>
          </div>

          <div v-else-if="documents.length === 0" class="empty-state">
            <p>No documents found</p>
          </div>

          <div v-else class="documents-list">
            <div
              v-for="(doc, idx) in documents"
              :key="doc.id"
              class="document-item"
            >
              <div class="document-header">
                <span class="document-id">{{ doc.id }}</span>
                <span v-if="doc.embedding_dim" class="embedding-info">
                  {{ doc.embedding_dim }}D embedding
                </span>
              </div>
              <p v-if="doc.document" class="document-content">{{ doc.document }}</p>
              <div v-if="doc.metadata && Object.keys(doc.metadata).length > 0" class="document-metadata">
                <button @click="toggleMetadata(idx)" class="metadata-toggle">
                  <svg :class="{ rotated: expandedDocs.has(idx) }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                  </svg>
                  <span>Metadata</span>
                </button>
                <pre v-if="expandedDocs.has(idx)" class="metadata-content">{{ JSON.stringify(doc.metadata, null, 2) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State (no collection selected) -->
      <div v-else class="empty-selection">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        <p>Select a collection to explore its documents</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChromaDBExplorer')
const apiClient = useApiClient()

// Data
interface CollectionMetadata {
  name: string
  count: number
  metadata: Record<string, any> | null
}

interface DocumentItem {
  id: string
  document: string | null
  metadata: Record<string, any> | null
  embedding_dim: number | null
}

interface SearchResultItem {
  id: string
  document: string | null
  metadata: Record<string, any> | null
  distance: number | null
}

const collections = ref<CollectionMetadata[]>([])
const selectedCollection = ref<CollectionMetadata | null>(null)
const documents = ref<DocumentItem[]>([])
const searchResults = ref<SearchResultItem[]>([])
const isLoading = ref(false)
const isLoadingDocuments = ref(false)
const isSearching = ref(false)
const errorMessage = ref('')
const currentPage = ref(0)
const currentOffset = ref(0)
const pageSize = ref(50)
const searchQuery = ref('')
const searchLimit = ref(10)
const expandedDocs = ref(new Set<number>())

// Methods
async function loadCollections() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const response = await apiClient.get<{ success: boolean; data: CollectionMetadata[]; error?: string }>(
      '/api/knowledge/chroma/collections'
    )
    if (response.success && response.data) {
      collections.value = response.data
      logger.info(`Loaded ${collections.value.length} collections`)
    } else {
      errorMessage.value = response.error || 'Failed to load collections'
    }
  } catch (error) {
    logger.error('Failed to load collections:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Failed to load collections'
  } finally {
    isLoading.value = false
  }
}

async function selectCollection(collection: CollectionMetadata) {
  selectedCollection.value = collection
  currentPage.value = 0
  currentOffset.value = 0
  searchResults.value = []
  searchQuery.value = ''
  await loadDocuments()
}

async function loadDocuments() {
  if (!selectedCollection.value) return

  isLoadingDocuments.value = true
  errorMessage.value = ''

  try {
    const params = new URLSearchParams({
      limit: String(pageSize.value),
      offset: String(currentOffset.value)
    })
    const response = await apiClient.get<{
      success: boolean
      data: {
        ids: string[]
        documents: (string | null)[]
        metadatas: (Record<string, any> | null)[]
        embedding_dim: number | null
      }
      total: number
      error?: string
    }>(
      `/api/knowledge/chroma/collections/${selectedCollection.value.name}/documents?${params}`
    )

    if (response.success && response.data) {
      const { ids, documents: docs, metadatas, embedding_dim } = response.data

      documents.value = ids.map((id: string, idx: number) => ({
        id,
        document: docs?.[idx] || null,
        metadata: metadatas?.[idx] || null,
        embedding_dim: embedding_dim || null
      }))

      logger.info(`Loaded ${documents.value.length} documents`)
    } else {
      errorMessage.value = response.error || 'Failed to load documents'
    }
  } catch (error) {
    logger.error('Failed to load documents:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Failed to load documents'
  } finally {
    isLoadingDocuments.value = false
  }
}

async function performSearch() {
  if (!selectedCollection.value || !searchQuery.value) return

  isSearching.value = true
  errorMessage.value = ''

  try {
    const response = await apiClient.post<{
      success: boolean
      data: SearchResultItem[]
      query: string
      error?: string
    }>(
      `/api/knowledge/chroma/collections/${selectedCollection.value.name}/search`,
      {
        query: searchQuery.value,
        n_results: searchLimit.value
      }
    )

    if (response.success && response.data) {
      searchResults.value = response.data
      logger.info(`Found ${searchResults.value.length} search results`)
    } else {
      errorMessage.value = response.error || 'Search failed'
    }
  } catch (error) {
    logger.error('Search failed:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Search failed'
  } finally {
    isSearching.value = false
  }
}

function clearSearch() {
  searchResults.value = []
  searchQuery.value = ''
}

function nextPage() {
  if (!selectedCollection.value) return
  if (currentOffset.value + pageSize.value >= selectedCollection.value.count) return

  currentOffset.value += pageSize.value
  currentPage.value++
  loadDocuments()
}

function prevPage() {
  if (currentOffset.value === 0) return

  currentOffset.value = Math.max(0, currentOffset.value - pageSize.value)
  currentPage.value = Math.max(0, currentPage.value - 1)
  loadDocuments()
}

function toggleMetadata(idx: number) {
  if (expandedDocs.value.has(idx)) {
    expandedDocs.value.delete(idx)
  } else {
    expandedDocs.value.add(idx)
  }
}

onMounted(() => {
  loadCollections()
})
</script>

<style scoped>
/* Issue #8999: ChromaDB Explorer Design */

.chroma-explorer {
  contain: layout style paint;
  padding: var(--spacing-6);
  max-width: 1400px;
  margin: 0 auto;
}

/* ============================================
 * HEADER
 * ============================================ */

.explorer-header {
  margin-bottom: var(--spacing-6);
}

.header-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-2);
}

.header-icon {
  width: 32px;
  height: 32px;
  color: var(--color-info);
}

.explorer-header h1 {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-subtitle {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin: 0;
}

/* ============================================
 * ERROR ALERT
 * ============================================ */

.error-alert {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--color-danger-bg);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-md);
  color: var(--color-danger);
  margin-bottom: var(--spacing-4);
}

.error-alert svg {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.error-alert span {
  flex: 1;
}

.error-alert button {
  background: none;
  border: none;
  color: var(--color-danger);
  cursor: pointer;
  padding: var(--spacing-1);
}

.error-alert button svg {
  width: 16px;
  height: 16px;
}

/* ============================================
 * MAIN CONTENT
 * ============================================ */

.explorer-content {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: var(--spacing-4);
  min-height: 600px;
}

/* ============================================
 * COLLECTIONS PANEL
 * ============================================ */

.collections-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 200px);
  overflow: hidden;
  transition: all var(--duration-200) ease;
}

.collections-panel.collapsed {
  grid-column: 1;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.panel-header h2 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn svg {
  width: 18px;
  height: 18px;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* ============================================
 * COLLECTIONS LIST
 * ============================================ */

.collections-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-2);
}

.collection-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--spacing-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  transition: all var(--duration-150) ease;
  margin-bottom: var(--spacing-1);
}

.collection-item:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-default);
}

.collection-item.active {
  background: var(--color-info-bg);
  border-color: var(--color-info);
  color: var(--color-info);
}

.collection-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex: 1;
}

.collection-name {
  font-size: var(--text-sm);
  font-weight: 500;
}

.collection-count {
  font-size: var(--text-xs);
  opacity: 0.7;
}

.collection-item svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* ============================================
 * LOADING & EMPTY STATES
 * ============================================ */

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-default);
  border-top-color: var(--color-info);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: var(--spacing-3);
}

.empty-state svg {
  width: 48px;
  height: 48px;
  margin-bottom: var(--spacing-3);
  opacity: 0.5;
}

.empty-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-16);
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.empty-selection svg {
  width: 64px;
  height: 64px;
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

/* ============================================
 * DETAILS PANEL
 * ============================================ */

.details-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  overflow-y: auto;
  max-height: calc(100vh - 200px);
}

.details-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.back-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.back-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.back-btn svg {
  width: 16px;
  height: 16px;
}

.details-header h2 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

/* ============================================
 * COLLECTION STATS
 * ============================================ */

.collection-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-5);
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
}

/* ============================================
 * SEARCH PANEL
 * ============================================ */

.search-panel {
  margin-bottom: var(--spacing-5);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.search-panel h3 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-3) 0;
}

.search-controls {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-4);
}

.search-input {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.search-limit {
  width: 80px;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.search-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-info);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.search-btn:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.search-btn svg {
  width: 16px;
  height: 16px;
}

/* ============================================
 * SEARCH RESULTS
 * ============================================ */

.search-results {
  margin-top: var(--spacing-4);
}

.results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-3);
}

.results-header h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.clear-btn {
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.clear-btn:hover {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.search-result-item {
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-2);
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.result-id {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.result-distance {
  font-size: var(--text-xs);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-success-bg);
  border-radius: var(--radius-sm);
  color: var(--color-success);
  font-family: var(--font-mono);
}

.result-document {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.5;
  margin: var(--spacing-2) 0;
}

.result-metadata {
  margin-top: var(--spacing-2);
}

.metadata-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-weight: 500;
  display: block;
  margin-bottom: var(--spacing-1);
}

.result-metadata code {
  display: block;
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--text-secondary);
  overflow-x: auto;
}

/* ============================================
 * DOCUMENTS PANEL
 * ============================================ */

.documents-panel {
  margin-top: var(--spacing-5);
}

.panel-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-4);
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid var(--border-default);
}

.panel-controls h3 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.page-btn:hover:not(:disabled) {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.page-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.page-btn svg {
  width: 16px;
  height: 16px;
}

.page-info {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* ============================================
 * DOCUMENTS LIST
 * ============================================ */

.documents-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.document-item {
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.document-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.document-id {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.embedding-info {
  font-size: var(--text-xs);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-info-bg);
  border-radius: var(--radius-sm);
  color: var(--color-info);
}

.document-content {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
  margin: var(--spacing-2) 0;
}

.document-metadata {
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-default);
}

.metadata-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-150) ease;
}

.metadata-toggle:hover {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.metadata-toggle svg {
  width: 14px;
  height: 14px;
  transition: transform var(--duration-150) ease;
}

.metadata-toggle svg.rotated {
  transform: rotate(90deg);
}

.metadata-content {
  margin-top: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre;
}

/* ============================================
 * RESPONSIVE
 * ============================================ */

@media (max-width: 1024px) {
  .explorer-content {
    grid-template-columns: 1fr;
  }

  .collections-panel {
    max-height: 400px;
  }

  .collections-panel.collapsed {
    display: none;
  }
}
</style>
