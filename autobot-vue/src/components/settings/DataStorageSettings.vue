<template>
  <div class="settings-section">
    <h3><i class="fas fa-database"></i> Data Storage Management</h3>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading storage statistics...</span>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ error }}</span>
      <button @click="loadStorageStats" class="retry-btn">
        <i class="fas fa-redo"></i> Retry
      </button>
    </div>

    <template v-else-if="storageStats">
      <!-- Storage Overview -->
      <div class="storage-overview">
        <div class="overview-card total">
          <div class="card-icon">
            <i class="fas fa-hdd"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ storageStats.total_size_human }}</span>
            <span class="card-label">Total Storage Used</span>
          </div>
        </div>

        <div class="overview-card files">
          <div class="card-icon">
            <i class="fas fa-file"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ storageStats.total_files.toLocaleString() }}</span>
            <span class="card-label">Total Files</span>
          </div>
        </div>

        <div class="overview-card directories">
          <div class="card-icon">
            <i class="fas fa-folder"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ storageStats.total_directories }}</span>
            <span class="card-label">Directories</span>
          </div>
        </div>

        <div class="overview-card conversations">
          <div class="card-icon">
            <i class="fas fa-comments"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ conversationsSummary?.unique_conversations || 0 }}</span>
            <span class="card-label">Conversations</span>
          </div>
        </div>
      </div>

      <!-- Storage Categories -->
      <div class="storage-categories">
        <div class="section-header">
          <h4><i class="fas fa-layer-group"></i> Storage Categories</h4>
          <button @click="loadStorageStats" class="refresh-btn" :disabled="isLoading">
            <i class="fas fa-sync" :class="{ 'fa-spin': isLoading }"></i>
            Refresh
          </button>
        </div>

        <div class="categories-grid">
          <div
            v-for="category in sortedCategories"
            :key="category.path"
            class="category-card"
            :class="{ protected: !category.can_cleanup }"
          >
            <div class="category-header">
              <div class="category-info">
                <span class="category-name">{{ category.name }}</span>
                <span class="category-path">{{ category.path }}/</span>
              </div>
              <span
                class="category-badge"
                :class="category.cleanup_type"
              >
                {{ category.cleanup_type }}
              </span>
            </div>

            <p class="category-description">{{ category.description }}</p>

            <div class="category-stats">
              <div class="stat">
                <i class="fas fa-weight-hanging"></i>
                <span>{{ category.size_human }}</span>
              </div>
              <div class="stat">
                <i class="fas fa-file-alt"></i>
                <span>{{ category.file_count }} files</span>
              </div>
            </div>

            <div class="category-actions">
              <button
                v-if="category.can_cleanup"
                @click="previewCleanup(category.path)"
                class="action-btn preview"
                :disabled="isCleaningUp"
              >
                <i class="fas fa-search"></i> Preview Cleanup
              </button>
              <button
                @click="viewCategoryDetails(category.path)"
                class="action-btn view"
              >
                <i class="fas fa-folder-open"></i> View Files
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Database Files -->
      <div v-if="databaseFiles" class="database-files">
        <div class="section-header">
          <h4><i class="fas fa-database"></i> Database Files</h4>
          <span class="db-total">{{ databaseFiles.total_size_human }} total</span>
        </div>

        <div class="db-list">
          <div
            v-for="db in databaseFiles.databases"
            :key="db.name"
            class="db-item"
          >
            <div class="db-info">
              <span class="db-name">{{ db.name }}</span>
              <span class="db-modified">Modified: {{ formatDate(db.modified) }}</span>
            </div>
            <span class="db-size">{{ db.size_human }}</span>
          </div>
        </div>
      </div>

      <!-- Cleanup Actions -->
      <div class="cleanup-actions">
        <h4><i class="fas fa-broom"></i> Cleanup Actions</h4>

        <div class="action-cards">
          <div class="action-card">
            <div class="action-header">
              <i class="fas fa-folder-minus"></i>
              <h5>Clean Old Backups</h5>
            </div>
            <p>Remove directories ending with .old or .backup</p>
            <button
              @click="cleanupOldBackups(true)"
              class="cleanup-btn preview"
              :disabled="isCleaningUp"
            >
              <i class="fas fa-search"></i> Preview
            </button>
            <button
              @click="cleanupOldBackups(false)"
              class="cleanup-btn danger"
              :disabled="isCleaningUp"
            >
              <i class="fas fa-trash"></i> Clean Now
            </button>
          </div>

          <div class="action-card">
            <div class="action-header">
              <i class="fas fa-comments"></i>
              <h5>Clean Old Conversations</h5>
            </div>
            <p>Remove conversations older than specified days</p>
            <div class="days-input">
              <label>Older than:</label>
              <input
                type="number"
                v-model.number="cleanupDays"
                min="1"
                max="365"
              />
              <span>days</span>
            </div>
            <button
              @click="cleanupConversations(true)"
              class="cleanup-btn preview"
              :disabled="isCleaningUp"
            >
              <i class="fas fa-search"></i> Preview
            </button>
            <button
              @click="cleanupConversations(false)"
              class="cleanup-btn danger"
              :disabled="isCleaningUp"
            >
              <i class="fas fa-trash"></i> Clean Now
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Cleanup Result Modal -->
    <div v-if="cleanupResult" class="modal-overlay" @click.self="cleanupResult = null">
      <div class="modal-content">
        <div class="modal-header">
          <h4>
            <i :class="cleanupResult.dry_run ? 'fas fa-search' : 'fas fa-check-circle'"></i>
            {{ cleanupResult.dry_run ? 'Cleanup Preview' : 'Cleanup Complete' }}
          </h4>
          <button @click="cleanupResult = null" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="result-summary">
            <div class="result-item">
              <span class="label">Category:</span>
              <span class="value">{{ cleanupResult.category }}</span>
            </div>
            <div class="result-item">
              <span class="label">Files {{ cleanupResult.dry_run ? 'to remove' : 'removed' }}:</span>
              <span class="value">{{ cleanupResult.files_removed }}</span>
            </div>
            <div class="result-item">
              <span class="label">Space {{ cleanupResult.dry_run ? 'to free' : 'freed' }}:</span>
              <span class="value highlight">{{ cleanupResult.bytes_freed_human }}</span>
            </div>
          </div>

          <div v-if="cleanupResult.errors?.length" class="result-errors">
            <h5>Errors:</h5>
            <ul>
              <li v-for="(error, idx) in cleanupResult.errors" :key="idx">{{ error }}</li>
            </ul>
          </div>

          <div v-if="cleanupResult.dry_run" class="confirm-actions">
            <button
              @click="executeCleanup"
              class="confirm-btn danger"
              :disabled="isCleaningUp"
            >
              <i class="fas fa-trash"></i> Confirm Cleanup
            </button>
            <button @click="cleanupResult = null" class="confirm-btn cancel">
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Category Details Modal -->
    <div v-if="categoryDetails" class="modal-overlay" @click.self="categoryDetails = null">
      <div class="modal-content wide">
        <div class="modal-header">
          <h4>
            <i class="fas fa-folder-open"></i>
            {{ categoryDetails.category }}/
          </h4>
          <button @click="categoryDetails = null" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="category-summary">
            <span>{{ categoryDetails.total_files }} files</span>
            <span>{{ categoryDetails.total_size_human }} total</span>
            <span>Showing {{ categoryDetails.showing }} most recent</span>
          </div>

          <div class="files-list">
            <div
              v-for="file in categoryDetails.files"
              :key="file.name"
              class="file-item"
              :class="{ 'is-dir': file.is_dir }"
            >
              <i :class="file.is_dir ? 'fas fa-folder' : 'fas fa-file'"></i>
              <span class="file-name">{{ file.name }}</span>
              <span class="file-size">{{ file.size_human }}</span>
              <span class="file-modified">{{ formatDate(file.modified) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DataStorageSettings')

interface StorageCategory {
  name: string
  path: string
  size_bytes: number
  size_human: string
  file_count: number
  description: string
  can_cleanup: boolean
  cleanup_type: string
}

interface StorageStats {
  total_size_bytes: number
  total_size_human: string
  total_files: number
  total_directories: number
  categories: StorageCategory[]
}

interface DatabaseFile {
  name: string
  size_bytes: number
  size_human: string
  modified: string
  can_cleanup: boolean
}

interface DatabaseFiles {
  databases: DatabaseFile[]
  total_count: number
  total_size_bytes: number
  total_size_human: string
}

interface ConversationsSummary {
  unique_conversations: number
  transcripts: { count: number; size_bytes: number; size_human: string }
  chats: { count: number; size_bytes: number; size_human: string }
  total_size_bytes: number
  total_size_human: string
}

interface CleanupResult {
  category: string
  files_removed: number
  bytes_freed: number
  bytes_freed_human: string
  dry_run: boolean
  errors: string[]
}

interface CategoryDetails {
  category: string
  total_size_bytes: number
  total_size_human: string
  total_files: number
  files: Array<{
    name: string
    is_dir: boolean
    size_bytes: number
    size_human: string
    modified: string
  }>
  showing: number
}

const isLoading = ref(false)
const isCleaningUp = ref(false)
const error = ref<string | null>(null)
const storageStats = ref<StorageStats | null>(null)
const databaseFiles = ref<DatabaseFiles | null>(null)
const conversationsSummary = ref<ConversationsSummary | null>(null)
const cleanupResult = ref<CleanupResult | null>(null)
const categoryDetails = ref<CategoryDetails | null>(null)
const cleanupDays = ref(30)
const pendingCleanup = ref<{ category: string; older_than_days: number } | null>(null)

const sortedCategories = computed(() => {
  if (!storageStats.value) return []
  return [...storageStats.value.categories].sort((a, b) => b.size_bytes - a.size_bytes)
})

const formatDate = (isoDate: string): string => {
  try {
    const date = new Date(isoDate)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return isoDate
  }
}

const loadStorageStats = async () => {
  isLoading.value = true
  error.value = null

  try {
    const [statsRes, dbRes, convoRes] = await Promise.all([
      apiClient.get('/api/data-storage/stats'),
      apiClient.get('/api/data-storage/databases'),
      apiClient.get('/api/data-storage/conversations/summary'),
    ])

    storageStats.value = await statsRes.json() as StorageStats
    databaseFiles.value = await dbRes.json() as DatabaseFiles
    conversationsSummary.value = await convoRes.json() as ConversationsSummary

    logger.info('Storage stats loaded:', storageStats.value?.total_size_human)
  } catch (err: unknown) {
    const errorMessage = err instanceof Error ? err.message : 'Failed to load storage stats'
    error.value = errorMessage
    logger.error('Failed to load storage stats:', err)
  } finally {
    isLoading.value = false
  }
}

const previewCleanup = async (category: string) => {
  isCleaningUp.value = true

  try {
    const response = await apiClient.post('/api/data-storage/cleanup', {
      category,
      older_than_days: 0,
      dry_run: true,
    })

    cleanupResult.value = await response.json() as CleanupResult
    pendingCleanup.value = { category, older_than_days: 0 }
  } catch (err: unknown) {
    logger.error('Cleanup preview failed:', err)
  } finally {
    isCleaningUp.value = false
  }
}

const executeCleanup = async () => {
  if (!pendingCleanup.value) return

  isCleaningUp.value = true

  try {
    const response = await apiClient.post('/api/data-storage/cleanup', {
      category: pendingCleanup.value.category,
      older_than_days: pendingCleanup.value.older_than_days,
      dry_run: false,
    })

    cleanupResult.value = await response.json() as CleanupResult
    pendingCleanup.value = null

    // Refresh stats after cleanup
    await loadStorageStats()
  } catch (err: unknown) {
    logger.error('Cleanup failed:', err)
  } finally {
    isCleaningUp.value = false
  }
}

const cleanupOldBackups = async (dryRun: boolean) => {
  isCleaningUp.value = true

  try {
    const response = await apiClient.post(`/api/data-storage/cleanup/old-backups?dry_run=${dryRun}`)
    const responseData = await response.json() as { total_count: number; bytes_freed: number; bytes_freed_human: string }

    if (dryRun) {
      cleanupResult.value = {
        category: 'Old Backups',
        files_removed: responseData.total_count,
        bytes_freed: responseData.bytes_freed,
        bytes_freed_human: responseData.bytes_freed_human,
        dry_run: true,
        errors: [],
      }
    } else {
      await loadStorageStats()
      cleanupResult.value = {
        category: 'Old Backups',
        files_removed: responseData.total_count,
        bytes_freed: responseData.bytes_freed,
        bytes_freed_human: responseData.bytes_freed_human,
        dry_run: false,
        errors: [],
      }
    }
  } catch (err: unknown) {
    logger.error('Old backups cleanup failed:', err)
  } finally {
    isCleaningUp.value = false
  }
}

const cleanupConversations = async (dryRun: boolean) => {
  isCleaningUp.value = true

  try {
    const response = await apiClient.post('/api/data-storage/cleanup', {
      category: 'conversation_transcripts',
      older_than_days: cleanupDays.value,
      dry_run: dryRun,
    })

    cleanupResult.value = await response.json() as CleanupResult
    pendingCleanup.value = dryRun ? { category: 'conversation_transcripts', older_than_days: cleanupDays.value } : null

    if (!dryRun) {
      await loadStorageStats()
    }
  } catch (err: unknown) {
    logger.error('Conversations cleanup failed:', err)
  } finally {
    isCleaningUp.value = false
  }
}

const viewCategoryDetails = async (categoryPath: string) => {
  try {
    const response = await apiClient.get(`/api/data-storage/category/${categoryPath}`)
    categoryDetails.value = await response.json() as CategoryDetails
  } catch (err: unknown) {
    logger.error('Failed to load category details:', err)
  }
}

onMounted(() => {
  loadStorageStats()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.settings-section {
  padding: 20px;
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.settings-section h3 {
  margin: 0 0 20px 0;
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--color-primary);
}

.settings-section h3 i {
  color: var(--color-primary);
}

/* Loading/Error States */
.loading-state,
.error-state {
  text-align: center;
  padding: 40px;
  color: var(--text-tertiary);
}

.loading-state i,
.error-state i {
  font-size: 2rem;
  margin-bottom: 12px;
  display: block;
}

.error-state {
  color: var(--color-danger);
}

.retry-btn {
  margin-top: 12px;
  padding: 8px 16px;
  background: var(--color-primary);
  color: var(--bg-primary);
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

/* Storage Overview */
.storage-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.overview-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-light);
}

.overview-card .card-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 20px;
  color: var(--bg-primary);
}

.overview-card.total .card-icon { background: linear-gradient(135deg, #667eea, #764ba2); }
.overview-card.files .card-icon { background: linear-gradient(135deg, #4facfe, #00f2fe); }
.overview-card.directories .card-icon { background: linear-gradient(135deg, #43e97b, #38f9d7); }
.overview-card.conversations .card-icon { background: linear-gradient(135deg, #f093fb, #f5576c); }

.card-content {
  display: flex;
  flex-direction: column;
}

.card-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.card-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

/* Storage Categories */
.storage-categories {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h4 {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-btn {
  padding: 8px 16px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.refresh-btn:hover {
  background: var(--border-light);
}

.categories-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.category-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 16px;
}

.category-card.protected {
  border-left: 3px solid var(--text-tertiary);
}

.category-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.category-name {
  font-weight: 600;
  color: var(--text-primary);
  display: block;
}

.category-path {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: monospace;
}

.category-badge {
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.category-badge.manual { background: var(--color-info-bg); color: var(--color-info); }
.category-badge.protected { background: var(--bg-tertiary); color: var(--text-primary); }

.category-description {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.category-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.category-stats .stat {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-primary);
}

.category-stats .stat i {
  color: var(--text-tertiary);
}

.category-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn.preview {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.action-btn.view {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Database Files */
.database-files {
  margin-bottom: 24px;
}

.db-total {
  font-size: 14px;
  color: var(--text-tertiary);
}

.db-list {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
}

.db-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
}

.db-item:last-child {
  border-bottom: none;
}

.db-name {
  font-family: monospace;
  font-weight: 500;
  color: var(--text-primary);
}

.db-modified {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-left: 12px;
}

.db-size {
  font-weight: 600;
  color: var(--color-primary);
}

/* Cleanup Actions */
.cleanup-actions h4 {
  margin: 0 0 16px 0;
  color: var(--text-primary);
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.action-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 16px;
}

.action-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.action-header i {
  font-size: 20px;
  color: var(--text-tertiary);
}

.action-header h5 {
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
}

.action-card p {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0 0 12px 0;
}

.days-input {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.days-input label {
  font-size: 13px;
  color: var(--text-primary);
}

.days-input input {
  width: 60px;
  padding: 6px 8px;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  font-size: 13px;
}

.days-input span {
  font-size: 13px;
  color: var(--text-tertiary);
}

.cleanup-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  margin-right: 8px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.cleanup-btn.preview {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.cleanup-btn.danger {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.cleanup-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-primary);
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-content.wide {
  max-width: 700px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
}

.modal-header h4 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-tertiary);
  font-size: 18px;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
}

.result-summary {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.result-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-light);
}

.result-item:last-child {
  border-bottom: none;
}

.result-item .label {
  color: var(--text-tertiary);
}

.result-item .value {
  font-weight: 600;
  color: var(--text-primary);
}

.result-item .value.highlight {
  color: var(--color-success);
}

.result-errors {
  background: var(--color-danger-bg);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.result-errors h5 {
  margin: 0 0 8px 0;
  color: var(--color-danger);
}

.result-errors ul {
  margin: 0;
  padding-left: 20px;
  color: var(--color-danger);
}

.confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.confirm-btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.confirm-btn.danger {
  background: var(--color-danger);
  color: var(--bg-primary);
}

.confirm-btn.cancel {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Category Details */
.category-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.category-summary span {
  font-size: 14px;
  color: var(--text-tertiary);
}

.files-list {
  max-height: 400px;
  overflow-y: auto;
}

.file-item {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.file-item i {
  color: var(--text-tertiary);
}

.file-item.is-dir i {
  color: var(--color-warning);
}

.file-name {
  font-family: monospace;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 13px;
  color: var(--text-tertiary);
}

.file-modified {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* Responsive */
@media (max-width: 1024px) {
  .storage-overview {
    grid-template-columns: repeat(2, 1fr);
  }

  .categories-grid,
  .action-cards {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .storage-overview {
    grid-template-columns: 1fr;
  }

  .category-actions {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }
}

/* Dark Theme - Uses CSS custom properties automatically */
</style>
