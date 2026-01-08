<template>
  <div class="knowledge-categories">

    <!-- Category Selection View -->
    <div v-if="!selectedMainCategory" class="category-selection">
      <div class="selection-header">
        <h2>Knowledge Base Categories</h2>
        <p class="subtitle">Browse AutoBot's knowledge organized by purpose and source</p>
      </div>

      <!-- Document Change Feed Section (PROMINENT) -->
      <div class="change-feed-section-wrapper">
        <div class="section-header prominent">
          <h3><i class="fas fa-sync-alt"></i> Document Lifecycle & Vectorization</h3>
          <span class="section-badge">Real-time Tracking</span>
        </div>
        <DocumentChangeFeed />
      </div>

      <div class="main-categories-grid">
        <div
          v-for="category in mainCategories"
          :key="category.id"
          class="main-category-card"
          :style="{ borderColor: category.color }"
          @click="selectMainCategory(category.id)"
        >
          <div class="category-icon-large" :style="{ backgroundColor: category.color }">
            <i :class="category.icon"></i>
          </div>
          <div class="category-content">
            <h3>{{ category.name }}</h3>
            <p class="category-description">{{ category.description }}</p>
            <p class="category-examples">{{ category.examples }}</p>
            <div class="category-stats">
              <div class="stat">
                <i class="fas fa-file-alt"></i>
                <span>{{ category.count }} facts</span>
              </div>
            </div>
          </div>
          <div class="browse-arrow">
            <i class="fas fa-arrow-right"></i>
          </div>
        </div>
      </div>
    </div>

    <!-- Browser View (when category selected) -->
    <div v-else class="browser-view">
      <div class="browser-header-bar">
        <BaseButton
          variant="outline"
          @click="backToCategories"
          class="back-btn"
        >
          <i class="fas fa-arrow-left"></i>
          Back to Categories
        </BaseButton>
        <h3>{{ getSelectedCategoryName() }}</h3>
      </div>
      <KnowledgeBrowser :mode="selectedMainCategory! as 'user' | 'autobot' | 'autobot-documentation' | 'system-knowledge' | 'user-knowledge'" :preselected-category="selectedMainCategory!" />
    </div>

    <!-- System Category Documents Panel -->
    <BaseModal
      v-model="showCategoryDocuments"
      :title="`${formatCategoryName(selectedCategoryPath)} - Documents`"
      size="large"
      @close="closeCategoryDocuments"
    >
      <div v-if="isLoadingCategoryDocs" class="loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <p>Loading documents...</p>
      </div>

      <EmptyState
        v-else-if="categoryDocuments.length === 0"
        icon="fas fa-file-alt"
        message="No documents in this category"
      />

      <div v-else class="documents-grid">
        <div
          v-for="doc in categoryDocuments"
          :key="doc.path"
          class="document-card"
          @click="viewDocumentDetails(doc)"
        >
          <div class="doc-icon-large">
            <i :class="getTypeIcon(doc.type || 'document')"></i>
          </div>
          <div class="doc-details">
            <h4>{{ doc.title || doc.filename }}</h4>
            <p class="doc-path">{{ doc.path }}</p>
            <div class="doc-meta">
              <span><i class="fas fa-file"></i> {{ doc.type || 'document' }}</span>
              <span v-if="doc.size"><i class="fas fa-database"></i> {{ formatFileSize(doc.size) }}</span>
            </div>
          </div>
        </div>
      </div>
    </BaseModal>

    <!-- Document Details Modal -->
    <BaseModal
      v-model="showDocumentModal"
      :title="currentDocument?.title || currentDocument?.filename || 'Document Details'"
      size="large"
      @close="closeDocumentModal"
    >
      <div v-if="currentDocument">
        <div class="document-metadata">
          <div class="meta-item">
            <strong>Path:</strong> {{ currentDocument.path }}
          </div>
          <div class="meta-item" v-if="currentDocument.type">
            <strong>Type:</strong> {{ currentDocument.type }}
          </div>
          <div class="meta-item" v-if="currentDocument.size">
            <strong>Size:</strong> {{ formatFileSize(currentDocument.size) }}
          </div>
        </div>

        <div v-if="currentDocument.content" class="document-content">
          <h4>Content Preview:</h4>
          <pre>{{ currentDocument.content.substring(0, 2000) }}{{ currentDocument.content.length > 2000 ? '...' : '' }}</pre>
        </div>
      </div>
    </BaseModal>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'
import KnowledgeBrowser from './KnowledgeBrowser.vue'
import DocumentChangeFeed from './DocumentChangeFeed.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeCategories')

// Import shared document feed wrapper styles
import '@/styles/document-feed-wrapper.css'

// Use the shared composable
const {
  fetchBasicStats,
  formatDateOnly: formatDate,
  formatCategoryName,
  getCategoryIcon,
  getTypeIcon,
  formatFileSize
} = useKnowledgeBase()

// Router
const router = useRouter()
const route = useRoute()

// UI state
const selectedMainCategory = ref<string | null>(null)

// Shared state
const isLoadingKBStats = ref(false)
const kbStats = ref<any>(null)
const mainCategories = ref<any[]>([])

// Category documents state
const isLoadingCategoryDocs = ref(false)
const categoryDocuments = ref<any[]>([])
const showCategoryDocuments = ref(false)
const selectedCategoryPath = ref('')
const showDocumentModal = ref(false)
const currentDocument = ref<any>(null)

// Computed properties
const systemCategories = computed(() => {
  return kbStats.value?.categories || []
})

const getKBStats = async () => {
  isLoadingKBStats.value = true

  try {
    const response = await fetchBasicStats()
    kbStats.value = response
  } catch (error) {
    logger.error('Error fetching KB stats:', error)
  } finally {
    isLoadingKBStats.value = false
  }
}

const browseCategory = async (category: string) => {
  // Navigate to search with category filter
  router.push({
    path: '/knowledge/search',
    query: { category }
  })
}

const viewCategoryDocuments = async (category: any) => {
  isLoadingCategoryDocs.value = true
  selectedCategoryPath.value = category.path

  try {
    const response = await apiClient.get(`/api/knowledge_base/categories/${encodeURIComponent(category.path)}`)
    const data = await parseApiResponse(response)
    categoryDocuments.value = data?.documents || []
    showCategoryDocuments.value = true
  } catch (error) {
    logger.error('Error loading category documents:', error)
    categoryDocuments.value = []
  } finally {
    isLoadingCategoryDocs.value = false
  }
}

const closeCategoryDocuments = () => {
  showCategoryDocuments.value = false
  categoryDocuments.value = []
  selectedCategoryPath.value = ''
}

const viewDocumentDetails = (doc: any) => {
  currentDocument.value = doc
  showDocumentModal.value = true
}

const closeDocumentModal = () => {
  showDocumentModal.value = false
  currentDocument.value = null
}

// Main category methods
const loadMainCategories = async () => {
  try {
    const response = await apiClient.get('/api/knowledge_base/categories/main')
    const data = await parseApiResponse(response)
    mainCategories.value = data?.categories || []
  } catch (error) {
    logger.error('Failed to load main categories:', error)
    mainCategories.value = []
  }
}

const selectMainCategory = (categoryId: string) => {
  selectedMainCategory.value = categoryId
}

const backToCategories = () => {
  selectedMainCategory.value = null
}

const getSelectedCategoryName = () => {
  const category = mainCategories.value.find(c => c.id === selectedMainCategory.value)
  return category?.name || 'Knowledge Browser'
}

// Load data on mount
onMounted(() => {
  getKBStats()
  loadMainCategories()
})

// Cleanup on unmount to prevent teleport accumulation
onUnmounted(() => {
  // Close all modals to prevent teleport elements from accumulating
  showCategoryDocuments.value = false
  showDocumentModal.value = false

  // Clear modal data
  categoryDocuments.value = []
  currentDocument.value = null
  selectedCategoryPath.value = ''
})
</script>

<style scoped>
.knowledge-categories {
  padding: 1.5rem;
  max-width: 1400px;
  margin: 0 auto;
  min-height: calc(100vh - 200px);
}

/* Category Selection View */
.category-selection {
  padding: 2rem 0;
}

.selection-header {
  text-align: center;
  margin-bottom: 3rem;
}

.selection-header h2 {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}

.selection-header .subtitle {
  color: var(--text-secondary);
  font-size: 1.125rem;
}

/* Main Categories Grid */
.main-categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.main-category-card {
  background: var(--bg-card);
  border: 3px solid var(--border-default);
  border-radius: 1rem;
  padding: 2rem;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.main-category-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, var(--card-color, var(--border-default)), transparent);
  opacity: 0;
  transition: opacity 0.3s;
}

.main-category-card:hover {
  transform: translateY(-8px);
  box-shadow: var(--shadow-xl);
}

.main-category-card:hover::before {
  opacity: 1;
}

.category-icon-large {
  width: 5rem;
  height: 5rem;
  border-radius: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 2.5rem;
  margin-bottom: 1.5rem;
  transition: all 0.3s;
}

.main-category-card:hover .category-icon-large {
  transform: scale(1.1) rotate(5deg);
}

.category-content {
  flex: 1;
  width: 100%;
}

.category-content h3 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}

.category-description {
  color: var(--text-secondary);
  font-size: 1rem;
  margin-bottom: 0.75rem;
  line-height: 1.6;
}

.category-examples {
  color: var(--text-tertiary);
  font-size: 0.875rem;
  font-style: italic;
  margin-bottom: 1.5rem;
  padding: 0.75rem;
  background: var(--bg-secondary);
  border-radius: 0.5rem;
}

.category-stats {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  margin-top: 1rem;
}

.category-stats .stat {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
}

.category-stats .stat i {
  color: var(--color-info);
}

.browse-arrow {
  margin-top: 1.5rem;
  color: var(--color-info);
  font-size: 1.5rem;
  transition: transform 0.3s;
}

.main-category-card:hover .browse-arrow {
  transform: translateX(8px);
}

/* Browser View */
.browser-view {
  animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.browser-header-bar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: var(--bg-card);
  border-radius: 0.75rem;
  box-shadow: var(--shadow-sm);
}

/* Button styling handled by BaseButton component */

.browser-header-bar h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

/* Page Header */
.page-header {
  text-align: center;
  margin-bottom: 2rem;
}

.page-header h2 {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.page-header .subtitle {
  color: var(--text-secondary);
  font-size: 1.1rem;
}

/* Tab Selection */
.category-tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 2rem;
  border-bottom: 2px solid var(--border-default);
  padding-bottom: 0;
}

.tab-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  background: none;
  color: var(--text-secondary);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-secondary);
}

.tab-btn.active {
  color: var(--color-info);
  border-bottom-color: var(--color-info);
}

/* View Header */
.view-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--bg-card);
  border-radius: 0.75rem;
  box-shadow: var(--shadow-sm);
}

.view-header h3 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.view-description {
  color: var(--text-secondary);
  font-size: 0.95rem;
  margin-top: 0.25rem;
}

.manage-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1.25rem;
  background: var(--color-info);
  color: var(--text-on-primary);
  text-decoration: none;
  border-radius: 0.5rem;
  font-weight: 500;
  transition: all 0.2s;
}

.manage-btn:hover {
  background: var(--color-info-hover);
  transform: translateY(-1px);
}

/* Stats Overview */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--bg-card);
  border-radius: 0.75rem;
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: var(--shadow-sm);
  transition: all 0.2s;
}

.stat-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.stat-icon {
  width: 3rem;
  height: 3rem;
  background: linear-gradient(135deg, var(--color-info), var(--color-info-hover));
  color: var(--text-on-primary);
  border-radius: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.stat-label {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

/* Category Browse Grid */
.category-browse-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.category-browse-card {
  background: var(--bg-card);
  border-radius: 0.75rem;
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  cursor: pointer;
  border: 2px solid var(--border-default);
  transition: all 0.2s;
}

.category-browse-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.category-browse-card .category-icon {
  width: 3.5rem;
  height: 3.5rem;
  background: linear-gradient(135deg, var(--color-info-bg), var(--color-info-bg-hover));
  color: var(--color-info);
  border-radius: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.75rem;
}

.category-browse-card .category-info {
  flex: 1;
}

.category-browse-card .category-info h4 {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}

.category-browse-card .category-info p {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.category-browse-card .browse-arrow {
  color: var(--color-info);
  font-size: 1.25rem;
  transition: transform 0.2s;
}

.category-browse-card:hover .browse-arrow {
  transform: translateX(0.25rem);
}

/* System Categories */
.system-categories {
  min-height: 400px;
}

.population-controls {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
  margin-top: 1.5rem;
}

.category-tree-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1rem;
  max-height: 500px;
  overflow-y: auto;
}

.population-actions {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.selected-category-info {
  background: var(--color-info-bg);
  padding: 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-info);
}

.selected-category-info label {
  font-weight: 500;
  color: var(--text-primary);
  display: block;
  margin-bottom: 0.5rem;
}

.selected-path {
  color: var(--color-info);
  font-weight: 500;
}

.action-buttons {
  display: flex;
  gap: 0.75rem;
}

.action-button {
  flex: 1;
  padding: 0.75rem 1rem;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.action-button.primary {
  background: var(--color-info);
  color: var(--text-on-primary);
}

.action-button.primary:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.action-button.primary:disabled {
  background: var(--text-muted);
  cursor: not-allowed;
}

.action-button.secondary {
  background: var(--text-secondary);
  color: var(--text-on-primary);
}

.action-button.secondary:hover:not(:disabled) {
  background: var(--text-tertiary);
}

/* KB Stats */
.kb-stats {
  background: var(--bg-secondary);
  border-radius: 0.5rem;
  padding: 1.25rem;
  border: 1px solid var(--border-default);
}

.kb-stats h4 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 1rem;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-info);
}

/* KB Message */
.kb-message {
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.kb-message.success {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
  border: 1px solid var(--color-success-border);
}

.kb-message.error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border: 1px solid var(--color-error-border);
}

.categories-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.categories-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* Button styling handled by BaseButton component */

.loading-state {
  text-align: center;
  padding: 3rem;
  color: var(--text-secondary);
}

.categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
}

.category-card {
  background: var(--bg-card);
  border: 2px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.category-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
}

.category-card.selected {
  border-color: var(--color-info);
  background-color: var(--color-info-bg);
}

.category-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.category-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 1.25rem;
}

.category-actions {
  display: flex;
  gap: 0.5rem;
}

/* Button styling handled by BaseButton component */

.category-name {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.category-description {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.category-stats {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

/* Button styling handled by BaseButton component */

/* Form styles (used in modals) */

.form-group {
  margin-bottom: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-primary);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 0.625rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: var(--shadow-focus);
}

.color-picker {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.color-option {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.375rem;
  cursor: pointer;
  position: relative;
  transition: transform 0.2s;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.selected::after {
  content: '\2713';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--text-on-primary);
  font-weight: bold;
}

/* Button styling handled by BaseButton component */

/* Documents Panel */
.documents-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  background: var(--bg-card);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-modal);
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-default);
}

/* Button styling handled by BaseButton component */

.documents-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.document-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.document-item:hover {
  background: var(--bg-secondary);
  border-color: var(--color-info);
}

.doc-icon {
  width: 2.5rem;
  height: 2.5rem;
  background: var(--color-info-bg);
  border-radius: 0.375rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-info);
}

.doc-info h5 {
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}

.doc-meta {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

/* View Documents Button */
.view-docs-button {
  margin-top: 0.75rem;
  padding: 0.5rem 1rem;
  background: var(--color-success);
  color: var(--text-on-success);
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.view-docs-button:hover:not(:disabled) {
  background: var(--color-success-hover);
}

.view-docs-button:disabled {
  background: var(--text-muted);
  cursor: not-allowed;
}

/* Category Documents Modal */
.category-documents-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: 2rem;
}

.category-documents-modal {
  background: var(--bg-card);
  border-radius: 0.75rem;
  width: 100%;
  max-width: 1200px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-2xl);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  border-radius: 0.75rem 0.75rem 0 0;
}

.modal-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.modal-content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
}

.documents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1rem;
}

.document-card {
  background: var(--bg-card);
  border: 2px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1.25rem;
  cursor: pointer;
  transition: all 0.2s;
}

.document-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.doc-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.doc-icon {
  width: 2.5rem;
  height: 2.5rem;
  background: var(--color-info-bg);
  border-radius: 0.375rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-info);
  font-size: 1.125rem;
}

.doc-title {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 1rem;
}

.doc-info {
  margin-bottom: 1rem;
}

.doc-source {
  font-size: 0.75rem;
  color: var(--color-info);
  margin-bottom: 0.5rem;
  font-family: var(--font-mono);
}

.doc-preview {
  font-size: 0.875rem;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.doc-footer {
  display: flex;
  justify-content: between;
  align-items: center;
  gap: 1rem;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.doc-size {
  font-weight: 500;
}

.doc-score {
  font-family: var(--font-mono);
}

/* Document Viewer Modal */
.document-viewer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: 1rem;
}

.document-viewer-modal {
  background: var(--bg-card);
  border-radius: 0.75rem;
  width: 100%;
  max-width: 1400px;
  max-height: 95vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-2xl);
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  border-radius: 0.75rem 0.75rem 0 0;
}

.viewer-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.document-source {
  font-size: 0.875rem;
  color: var(--color-info);
  font-family: var(--font-mono);
  background: var(--color-info-bg);
  padding: 0.25rem 0.75rem;
  border-radius: 0.375rem;
}

.viewer-content {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

.document-content {
  padding: 2rem;
  font-family: var(--font-mono);
  font-size: 0.875rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  background: var(--code-bg);
  color: var(--code-text);
}

/* System Tabs */
.system-tabs {
  display: flex;
  gap: 0.5rem;
  border-bottom: 2px solid var(--border-default);
  padding-bottom: 0.5rem;
}

.system-tab-btn {
  padding: 0.5rem 1rem;
  border: none;
  background: transparent;
  border-radius: 0.375rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
}

.system-tab-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.system-tab-btn.active {
  background: var(--color-info);
  color: var(--text-on-primary);
}

/* AutoBot Categories */
.autobot-categories {
  padding: 1.5rem;
}

.subtitle {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin-top: 0.5rem;
}

/* Documents Grid */
.documents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.document-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  gap: 1rem;
}

.document-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.doc-icon-large {
  width: 3rem;
  height: 3rem;
  background: linear-gradient(135deg, var(--color-info-bg), var(--color-info-bg-hover));
  color: var(--color-info);
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  flex-shrink: 0;
}

.doc-details {
  flex: 1;
  min-width: 0;
}

.doc-details h4 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-path {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.doc-meta span {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

/* Document Metadata */
.document-metadata {
  background: var(--bg-secondary);
  border-radius: 0.5rem;
  padding: 1rem;
  margin-bottom: 1rem;
}

.meta-item {
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
}

.meta-item:last-child {
  margin-bottom: 0;
}

.meta-item strong {
  color: var(--text-primary);
  margin-right: 0.5rem;
}

/* Document Content */
.document-content {
  margin-top: 1rem;
}

.document-content h4 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.75rem;
}

.document-content pre {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1rem;
  font-size: 0.875rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
}
</style>
