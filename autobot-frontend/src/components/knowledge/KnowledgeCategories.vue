<template>
  <div class="knowledge-categories">

    <!-- Category Selection View -->
    <div v-if="!selectedMainCategory" class="category-selection">
      <div class="selection-header">
        <h2>{{ $t('knowledge.categories.title') }}</h2>
        <p class="subtitle">{{ $t('knowledge.categories.subtitle') }}</p>
      </div>

      <!-- Document Change Feed Section (PROMINENT) -->
      <div class="change-feed-section-wrapper">
        <div class="section-header prominent">
          <h3><Icon name="sync-alt" /> {{ $t('knowledge.categories.documentLifecycle') }}</h3>
          <span class="section-badge">{{ $t('knowledge.categories.realTimeTracking') }}</span>
        </div>
        <DocumentChangeFeed />
      </div>

      <!-- Categories loading state -->
      <div v-if="isLoadingCategories" class="loading-state">
        <Icon name="spinner" class="animate-spin" />
        <p>{{ $t('knowledge.categories.loadingCategories') }}</p>
      </div>

      <!-- Categories error state -->
      <div v-else-if="categoriesError" class="categories-error-state">
        <Icon name="exclamation-triangle" />
        <p>{{ categoriesError }}</p>
        <button class="retry-btn" @click="loadMainCategories">
          <Icon name="redo" /> {{ $t('knowledge.categories.retryBtn') }}
        </button>
      </div>

      <div v-else class="main-categories-grid">
        <div
          v-for="category in mainCategories"
          :key="category.id"
          class="main-category-card"
          :style="{ borderColor: category.color }"
          @click="selectMainCategory(category.id)"
        >
          <!-- Issue #747: Edit button -->
          <button
            class="category-edit-btn"
            :title="$t('knowledge.categories.editCategory')"
            @click="openCategoryEdit(category, $event)"
          >
            <Icon name="pencil-alt" />
          </button>
          <div class="category-icon-large" :style="{ backgroundColor: category.color }">
            <Icon :name="category.icon" />
          </div>
          <div class="category-content">
            <h3>{{ category.name }}</h3>
            <p class="category-description">{{ category.description }}</p>
            <p class="category-examples">{{ category.examples }}</p>
            <div class="category-stats">
              <div class="stat">
                <Icon name="file-alt" />
                <span>{{ category.count }} {{ $t('knowledge.categories.facts') }}</span>
              </div>
            </div>
          </div>
          <div class="browse-arrow">
            <Icon name="arrow-right" />
          </div>
        </div>
      </div>
    </div>

    <!-- Browser View (when category selected) -->
    <div v-else class="browser-view">
      <div class="browser-header-bar">
        <BaseButton
          variant="outline-solid"
          @click="backToCategories"
          class="back-btn"
        >
          <Icon name="arrow-left" />
          {{ $t('knowledge.categories.backToCategories') }}
        </BaseButton>
        <h3>{{ getSelectedCategoryName() }}</h3>
      </div>
      <KnowledgeBrowser :mode="selectedMainCategory! as 'user' | 'autobot' | 'autobot-documentation' | 'system-knowledge' | 'user-knowledge'" :preselected-category="selectedMainCategory!" />
    </div>

    <!-- System Category Documents Panel -->
    <BaseModal
      v-model="showCategoryDocuments"
      :title="`${formatCategoryName(selectedCategoryPath)} - Documents`"
      size="lg"
      @close="closeCategoryDocuments"
    >
      <div v-if="isLoadingCategoryDocs" class="loading-state">
        <Icon name="spinner" class="animate-spin" />
        <p>{{ $t('knowledge.categories.loadingDocuments') }}</p>
      </div>

      <EmptyState
        v-else-if="categoryDocuments.length === 0"
        icon="file-alt"
        :message="$t('knowledge.categories.noDocuments')"
      />

      <div v-else class="documents-grid">
        <div
          v-for="doc in categoryDocuments"
          :key="doc.path"
          class="document-card"
          @click="viewDocumentDetails(doc)"
        >
          <div class="doc-icon-large">
            <Icon :name="getTypeIcon(doc.type || 'document')" />
          </div>
          <div class="doc-details">
            <h4>{{ doc.title || doc.filename }}</h4>
            <p class="doc-path">{{ doc.path }}</p>
            <div class="doc-meta">
              <span><Icon name="file" /> {{ doc.type || 'document' }}</span>
              <span v-if="doc.size"><Icon name="database" /> {{ formatFileSize(doc.size) }}</span>
            </div>
          </div>
        </div>
      </div>
    </BaseModal>

    <!-- Document Details Modal -->
    <BaseModal
      v-model="showDocumentModal"
      :title="currentDocument?.title || currentDocument?.filename || $t('knowledge.categories.documentDetails')"
      size="lg"
      @close="closeDocumentModal"
    >
      <div v-if="currentDocument">
        <div class="document-metadata">
          <div class="meta-item">
            <strong>{{ $t('knowledge.categories.path') }}</strong> {{ currentDocument.path }}
          </div>
          <div class="meta-item" v-if="currentDocument.type">
            <strong>{{ $t('knowledge.categories.type') }}</strong> {{ currentDocument.type }}
          </div>
          <div class="meta-item" v-if="currentDocument.size">
            <strong>{{ $t('knowledge.categories.size') }}</strong> {{ formatFileSize(currentDocument.size) }}
          </div>
        </div>

        <div v-if="currentDocument.content" class="document-content">
          <h4>{{ $t('knowledge.categories.contentPreview') }}</h4>
          <pre>{{ currentDocument.content.substring(0, 2000) }}{{ currentDocument.content.length > 2000 ? '...' : '' }}</pre>
        </div>
      </div>
    </BaseModal>

    <!-- Issue #747: Category Edit Modal -->
    <CategoryEditModal
      v-model="showCategoryEditModal"
      :category="categoryToEdit"
      @updated="handleCategoryUpdated"
      @deleted="handleCategoryDeleted"
    />
    </div>

  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import { useKnowledgeStats } from '@/composables/knowledge/useKnowledgeStats'
import { useKnowledgeIcons } from '@/composables/knowledge/useKnowledgeIcons'
import { useKnowledgeCategories } from '@/composables/knowledge/useKnowledgeCategories'
import { formatDate, formatCategoryName, formatFileSize } from '@/utils/formatHelpers'
import KnowledgeBrowser from './KnowledgeBrowser.vue'
import DocumentChangeFeed from './DocumentChangeFeed.vue'
import CategoryEditModal from './modals/CategoryEditModal.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeCategories')
const { t } = useI18n()

// Import shared document feed wrapper styles
import '@/styles/document-feed-wrapper.css'

// Domain composables (migrated from useKnowledgeBase BC shim in #5193)
const { fetchBasicStats } = useKnowledgeStats()
const { getCategoryIcon, getTypeIcon } = useKnowledgeIcons()
const { fetchMainCategories, fetchCategoryDocuments } = useKnowledgeCategories()

// Router
const router = useRouter()
const route = useRoute()

// UI state
const selectedMainCategory = ref<string | null>(null)

// Shared state
const isLoadingKBStats = ref(false)
const kbStats = ref<any>(null)
const mainCategories = ref<any[]>([])
const isLoadingCategories = ref(false)
const categoriesError = ref<string | null>(null)

// Category documents state
const isLoadingCategoryDocs = ref(false)
const categoryDocuments = ref<any[]>([])
const showCategoryDocuments = ref(false)
const selectedCategoryPath = ref('')
const showDocumentModal = ref(false)
const currentDocument = ref<any>(null)

// Issue #747: Category edit modal state
const showCategoryEditModal = ref(false)
const categoryToEdit = ref<any>(null)

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
    categoryDocuments.value = await fetchCategoryDocuments(category.path)
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
  isLoadingCategories.value = true
  categoriesError.value = null
  try {
    // fetchMainCategories delegates to apiClient.get<T> which returns parsed
    // JSON or throws on HTTP error — 401/403 handling lives in the catch
    // below via the thrown error (#5033).
    mainCategories.value = await fetchMainCategories()
  } catch (error: unknown) {
    logger.error('Failed to load main categories:', error)
    const status = (error as { status?: number; response?: { status?: number } })?.status
      ?? (error as { response?: { status?: number } })?.response?.status
    if (status === 401) {
      categoriesError.value = t('knowledge.categories.authRequired')
    } else if (status === 403) {
      categoriesError.value = t('knowledge.categories.noPermission')
    } else {
      categoriesError.value = t('knowledge.categories.loadFailed')
    }
  } finally {
    isLoadingCategories.value = false
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
  return category?.name || t('knowledge.categories.knowledgeBrowser')
}

// Issue #747: Category edit/delete handlers
const openCategoryEdit = (category: any, event: Event) => {
  event.stopPropagation() // Prevent card click from triggering
  categoryToEdit.value = category
  showCategoryEditModal.value = true
}

const handleCategoryUpdated = (updatedCategory: any) => {
  // Update the category in the list
  const index = mainCategories.value.findIndex(c => c.id === updatedCategory.id)
  if (index !== -1) {
    mainCategories.value[index] = { ...mainCategories.value[index], ...updatedCategory }
  }
  showCategoryEditModal.value = false
  categoryToEdit.value = null
}

const handleCategoryDeleted = (categoryId: string) => {
  // Remove the category from the list
  mainCategories.value = mainCategories.value.filter(c => c.id !== categoryId)
  showCategoryEditModal.value = false
  categoryToEdit.value = null
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
  padding: var(--spacing-6);
  max-width: 1400px;
  margin: 0 auto;
  min-height: calc(100vh - 200px);
}

/* Category Selection View */
.category-selection {
  padding: var(--spacing-8) var(--spacing-0);
}

.selection-header {
  text-align: center;
  margin-bottom: var(--spacing-12);
}

.selection-header h2 {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-3);
}

.selection-header .subtitle {
  color: var(--text-secondary);
  font-size: var(--text-lg);
}

/* Main Categories Grid */
.main-categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-8);
  max-width: 1200px;
  margin: 0 auto;
}

.main-category-card {
  background: var(--bg-card);
  border: 3px solid var(--border-default);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-8);
  cursor: pointer;
  transition: all var(--duration-300) var(--ease-in-out);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
  overflow: hidden;
}

/* Issue #747: Category edit button */
.category-edit-btn {
  position: absolute;
  top: 1rem;
  right: 1rem;
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  opacity: 0;
  transition: all var(--duration-200);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.category-edit-btn:hover {
  background: var(--color-info);
  color: var(--text-on-primary);
}

.main-category-card:hover .category-edit-btn {
  opacity: 1;
}

.main-category-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--card-color, var(--border-default));
  opacity: 0;
  transition: opacity var(--duration-300);
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
  border-radius: var(--radius-2xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: 2.5rem;
  margin-bottom: var(--spacing-6);
  transition: all var(--duration-300);
}

.main-category-card:hover .category-icon-large {
  transform: scale(1.1) rotate(5deg);
}

.category-content {
  flex: 1;
  width: 100%;
}

.category-content h3 {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-3);
}

.category-description {
  color: var(--text-secondary);
  font-size: var(--text-base);
  margin-bottom: var(--spacing-3);
  line-height: 1.6;
}

.category-examples {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  font-style: italic;
  margin-bottom: var(--spacing-6);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.category-stats {
  display: flex;
  justify-content: center;
  gap: var(--spacing-6);
  margin-top: var(--spacing-4);
}

.category-stats .stat {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
}

.category-stats .stat i {
  color: var(--color-info);
}

.browse-arrow {
  margin-top: var(--spacing-6);
  color: var(--color-info);
  font-size: var(--text-2xl);
  transition: transform var(--duration-300);
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
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
}

/* Button styling handled by BaseButton component */

.browser-header-bar h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

/* Page Header */
.page-header {
  text-align: center;
  margin-bottom: var(--spacing-8);
}

.page-header h2 {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.page-header .subtitle {
  color: var(--text-secondary);
  font-size: 1.1rem;
}

/* Tab Selection */
.category-tabs {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-8);
  border-bottom: 2px solid var(--border-default);
  padding-bottom: var(--spacing-0);
}

.tab-btn {
  padding: var(--spacing-3) var(--spacing-6);
  border: none;
  background: none;
  color: var(--text-secondary);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
  border-bottom: 2px solid transparent;
  margin-bottom: var(--spacing-neg-2px);
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
  margin-bottom: var(--spacing-8);
  padding: var(--spacing-6);
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
}

.view-header h3 {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.view-description {
  color: var(--text-secondary);
  font-size: 0.95rem;
  margin-top: var(--spacing-1);
}

.manage-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-info);
  color: var(--text-on-primary);
  text-decoration: none;
  border-radius: var(--radius-lg);
  font-weight: 500;
  transition: all var(--duration-200);
}

.manage-btn:hover {
  background: var(--color-info-hover);
  transform: translateY(-1px);
}

/* Stats Overview */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-8);
}

.stat-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-200);
}

.stat-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.stat-icon {
  width: 3rem;
  height: 3rem;
  background: var(--color-info);
  color: var(--text-on-primary);
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
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
  font-size: var(--text-sm);
  margin-top: var(--spacing-1);
}

/* Category Browse Grid */
.category-browse-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-8);
}

.category-browse-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  cursor: pointer;
  border: 2px solid var(--border-default);
  transition: all var(--duration-200);
}

.category-browse-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.category-browse-card .category-icon {
  width: 3.5rem;
  height: 3.5rem;
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.75rem;
}

.category-browse-card .category-info {
  flex: 1;
}

.category-browse-card .category-info h4 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.category-browse-card .category-info p {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.category-browse-card .browse-arrow {
  color: var(--color-info);
  font-size: var(--text-xl);
  transition: transform var(--duration-200);
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
  gap: var(--spacing-8);
  margin-top: var(--spacing-6);
}

.category-tree-container {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  max-height: 500px;
  overflow-y: auto;
}

.population-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.selected-category-info {
  background: var(--color-info-bg);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-info);
}

.selected-category-info label {
  font-weight: 500;
  color: var(--text-primary);
  display: block;
  margin-bottom: var(--spacing-2);
}

.selected-path {
  color: var(--color-info);
  font-weight: 500;
}

.action-buttons {
  display: flex;
  gap: var(--spacing-3);
}

.action-button {
  flex: 1;
  padding: var(--spacing-3) var(--spacing-4);
  border: none;
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
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
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  border: 1px solid var(--border-default);
}

.kb-stats h4 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--color-info);
}

/* KB Message */
.kb-message {
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
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
  margin-bottom: var(--spacing-6);
}

.categories-header h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
}

/* Button styling handled by BaseButton component */

.loading-state {
  text-align: center;
  padding: var(--spacing-12);
  color: var(--text-secondary);
}

.categories-error-state {
  text-align: center;
  padding: var(--spacing-12) var(--spacing-8);
  color: var(--color-error-dark);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-xl);
  max-width: 500px;
  margin: 2rem auto;
}

.categories-error-state i {
  font-size: 2.5rem;
  margin-bottom: var(--spacing-4);
  display: block;
}

.categories-error-state p {
  font-size: var(--text-base);
  margin-bottom: var(--spacing-5);
}

.retry-btn {
  padding: var(--spacing-2) var(--spacing-5);
  background: var(--color-error-dark);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--duration-200);
}

.retry-btn:hover {
  opacity: 0.85;
}

.categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-6);
}

.category-card {
  background: var(--bg-card);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  cursor: pointer;
  transition: all var(--duration-200);
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
  margin-bottom: var(--spacing-4);
}

.category-icon {
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-xl);
}

.category-actions {
  display: flex;
  gap: var(--spacing-2);
}

/* Button styling handled by BaseButton component */

.category-name {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.category-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-4);
}

.category-stats {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

/* Button styling handled by BaseButton component */

/* Form styles (used in modals) */

.form-group {
  margin-bottom: var(--spacing-5);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: 500;
  color: var(--text-primary);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: var(--spacing-2-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: var(--shadow-focus);
}
.form-input:focus-visible,
.form-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.color-picker {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.color-option {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  cursor: pointer;
  position: relative;
  transition: transform var(--duration-200);
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
  padding: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
}

/* Button styling handled by BaseButton component */

.documents-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-4);
}

.document-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-2);
  cursor: pointer;
  transition: all var(--duration-200);
}

.document-item:hover {
  background: var(--bg-secondary);
  border-color: var(--color-info);
}

.doc-icon {
  width: 2.5rem;
  height: 2.5rem;
  background: var(--color-info-bg);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-info);
}

.doc-info h5 {
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.doc-meta {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

/* View Documents Button */
.view-docs-button {
  margin-top: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-success);
  color: var(--text-on-success);
  border: none;
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
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
  padding: var(--spacing-8);
}

.category-documents-modal {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
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
  padding: var(--spacing-6) var(--spacing-8);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  border-radius: var(--radius-xl) 0.75rem 0 0;
}

.modal-header h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.modal-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6) var(--spacing-8);
}

.documents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: var(--spacing-4);
}

.document-card {
  background: var(--bg-card);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  cursor: pointer;
  transition: all var(--duration-200);
}

.document-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.doc-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.doc-icon {
  width: 2.5rem;
  height: 2.5rem;
  background: var(--color-info-bg);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-info);
  font-size: var(--text-lg);
}

.doc-title {
  font-weight: 600;
  color: var(--text-primary);
  font-size: var(--text-base);
}

.doc-info {
  margin-bottom: var(--spacing-4);
}

.doc-source {
  font-size: var(--text-xs);
  color: var(--color-info);
  margin-bottom: var(--spacing-2);
  font-family: var(--font-mono);
}

.doc-preview {
  font-size: var(--text-sm);
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
  gap: var(--spacing-4);
  font-size: var(--text-xs);
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
  padding: var(--spacing-4);
}

.document-viewer-modal {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
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
  padding: var(--spacing-6) var(--spacing-8);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  border-radius: var(--radius-xl) 0.75rem 0 0;
}

.viewer-header h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.document-source {
  font-size: var(--text-sm);
  color: var(--color-info);
  font-family: var(--font-mono);
  background: var(--color-info-bg);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-md);
}

.viewer-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-0);
}

.document-content {
  padding: var(--spacing-8);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: var(--spacing-0);
  background: var(--code-bg);
  color: var(--code-text);
}

/* System Tabs */
.system-tabs {
  display: flex;
  gap: var(--spacing-2);
  border-bottom: 2px solid var(--border-default);
  padding-bottom: var(--spacing-2);
}

.system-tab-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
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
  padding: var(--spacing-6);
}

.subtitle {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-2);
}

/* Documents Grid */
.documents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-4);
  margin-top: var(--spacing-4);
}

.document-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  cursor: pointer;
  transition: all var(--duration-200);
  display: flex;
  gap: var(--spacing-4);
}

.document-card:hover {
  border-color: var(--color-info);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.doc-icon-large {
  width: 3rem;
  height: 3rem;
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
  flex-shrink: 0;
}

.doc-details {
  flex: 1;
  min-width: 0;
}

.doc-details h4 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-path {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  display: flex;
  gap: var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.doc-meta span {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

/* Document Metadata */
.document-metadata {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.meta-item {
  margin-bottom: var(--spacing-2);
  font-size: var(--text-sm);
}

.meta-item:last-child {
  margin-bottom: var(--spacing-0);
}

.meta-item strong {
  color: var(--text-primary);
  margin-right: var(--spacing-2);
}

/* Document Content */
.document-content {
  margin-top: var(--spacing-4);
}

.document-content h4 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-3);
}

.document-content pre {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  font-size: var(--text-sm);
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
}
</style>
