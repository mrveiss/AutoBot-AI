<template>
  <div class="watch-folders-view">
    <div class="view-header">
      <h2>Watch Folders</h2>
      <p class="view-description">
        Automatically ingest new files from monitored directories into your knowledge base.
      </p>
    </div>

    <!-- Stats Overview -->
    <div v-if="stats" class="stats-overview">
      <div class="stat-card">
        <div class="stat-label">Total Folders</div>
        <div class="stat-value">{{ stats.total_folders }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Active</div>
        <div class="stat-value">{{ stats.active_folders }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Files Ingested</div>
        <div class="stat-value">{{ stats.total_files_ingested }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Errors</div>
        <div class="stat-value" :class="{ 'stat-error': stats.total_errors > 0 }">
          {{ stats.total_errors }}
        </div>
      </div>
    </div>

    <!-- Add New Watch Folder Button -->
    <div class="action-bar">
      <button
        class="btn-primary"
        @click="showAddDialog = true"
      >
        <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
        </svg>
        Add Watch Folder
      </button>
    </div>

    <!-- Watch Folders List -->
    <div v-if="loading" class="loading-state">
      Loading watch folders...
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-secondary" @click="loadWatchFolders">
        Retry
      </button>
    </div>

    <div v-else-if="watchFolders.length === 0" class="empty-state">
      <svg class="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
      </svg>
      <p>No watch folders configured</p>
      <p class="empty-hint">Add a watch folder to automatically ingest files into your knowledge base.</p>
    </div>

    <div v-else class="folders-list">
      <div
        v-for="folder in watchFolders"
        :key="folder.folder_id"
        class="folder-card"
      >
        <div class="folder-header">
          <div class="folder-path">
            <svg class="path-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
            </svg>
            <span>{{ folder.path }}</span>
          </div>
          <div class="folder-status">
            <span
              class="status-badge"
              :class="{
                'status-active': folder.is_watching,
                'status-inactive': !folder.is_watching
              }"
            >
              {{ folder.is_watching ? 'Watching' : 'Paused' }}
            </span>
          </div>
        </div>

        <div class="folder-details">
          <div class="detail-row">
            <span class="detail-label">Collection:</span>
            <span class="detail-value">{{ folder.collection }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Category:</span>
            <span class="detail-value">{{ folder.category }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">File Types:</span>
            <span class="detail-value">{{ folder.file_types.join(', ') }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Recursive:</span>
            <span class="detail-value">{{ folder.recursive ? 'Yes' : 'No' }}</span>
          </div>
          <div v-if="folder.tags.length > 0" class="detail-row">
            <span class="detail-label">Tags:</span>
            <span class="detail-value">{{ folder.tags.join(', ') }}</span>
          </div>
        </div>

        <div v-if="folder.stats" class="folder-stats">
          <div class="stat-item">
            <span class="stat-label">Files Ingested:</span>
            <span class="stat-value">{{ folder.stats.files_ingested }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Last Change:</span>
            <span class="stat-value">
              {{ folder.stats.last_change ? formatDate(folder.stats.last_change) : 'Never' }}
            </span>
          </div>
          <div v-if="folder.stats.errors > 0" class="stat-item">
            <span class="stat-label">Errors:</span>
            <span class="stat-value stat-error">{{ folder.stats.errors }}</span>
          </div>
        </div>

        <div class="folder-actions">
          <button
            v-if="folder.is_watching"
            class="btn-action"
            @click="folder.folder_id && handlePause(folder.folder_id)"
          >
            <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            Pause
          </button>
          <button
            v-else
            class="btn-action btn-primary"
            @click="folder.folder_id && handleResume(folder.folder_id)"
          >
            <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            Resume
          </button>
          <button
            class="btn-action btn-danger"
            @click="folder.folder_id && handleDelete(folder.folder_id)"
          >
            <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
            </svg>
            Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Add Watch Folder Dialog -->
    <div v-if="showAddDialog" class="dialog-overlay" @click.self="showAddDialog = false">
      <div class="dialog">
        <div class="dialog-header">
          <h3>Add Watch Folder</h3>
          <button class="dialog-close" @click="showAddDialog = false">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>

        <div class="dialog-content">
          <form @submit.prevent="handleSubmit">
            <div class="form-group">
              <label for="path">Folder Path *</label>
              <input
                id="path"
                v-model="newFolder.path"
                type="text"
                placeholder="/path/to/watch"
                required
              />
            </div>

            <div class="form-group">
              <label for="collection">Collection</label>
              <input
                id="collection"
                v-model="newFolder.collection"
                type="text"
                placeholder="default"
              />
            </div>

            <div class="form-group">
              <label for="category">Category</label>
              <input
                id="category"
                v-model="newFolder.category"
                type="text"
                placeholder="uploads"
              />
            </div>

            <div class="form-group">
              <label for="file-types">File Types</label>
              <div class="checkbox-group">
                <label v-for="type in availableFileTypes" :key="type" class="checkbox-label">
                  <input
                    v-model="newFolder.file_types"
                    type="checkbox"
                    :value="type"
                  />
                  {{ type.toUpperCase() }}
                </label>
              </div>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input
                  v-model="newFolder.recursive"
                  type="checkbox"
                />
                Watch subdirectories recursively
              </label>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input
                  v-model="newFolder.enabled"
                  type="checkbox"
                />
                Start watching immediately
              </label>
            </div>

            <div class="form-group">
              <label for="tags">Tags (comma-separated)</label>
              <input
                id="tags"
                v-model="newFolderTags"
                type="text"
                placeholder="tag1, tag2, tag3"
              />
            </div>

            <div class="dialog-actions">
              <button type="button" class="btn-secondary" @click="showAddDialog = false">
                Cancel
              </button>
              <button type="submit" class="btn-primary">
                Add Watch Folder
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWatchFolders, type WatchFolderConfig } from '@/composables/knowledge/useWatchFolders'
import { useConfirmDialog } from '@/composables/useConfirmDialog'

const {
  watchFolders,
  stats,
  loading,
  error,
  loadWatchFolders,
  createWatchFolder,
  deleteWatchFolder,
  enableWatchFolder,
  disableWatchFolder,
  loadStats,
} = useWatchFolders()

const { t } = useI18n()
const { confirm } = useConfirmDialog()

const showAddDialog = ref(false)
const newFolderTags = ref('')
const availableFileTypes = ['pdf', 'docx', 'txt', 'md', 'csv', 'html']

const newFolder = ref<Omit<WatchFolderConfig, 'folder_id' | 'created_at' | 'is_watching' | 'stats'>>({
  path: '',
  collection: 'default',
  enabled: true,
  file_types: ['pdf', 'docx', 'txt', 'md', 'csv', 'html'],
  recursive: true,
  category: 'uploads',
  tags: [],
})

function formatDate(dateString: string): string {
  try {
    return new Date(dateString).toLocaleString()
  } catch {
    return dateString
  }
}

async function handleSubmit() {
  // Parse tags
  newFolder.value.tags = newFolderTags.value
    .split(',')
    .map(t => t.trim())
    .filter(t => t.length > 0)

  const result = await createWatchFolder(newFolder.value)

  if (result) {
    showAddDialog.value = false
    // Reset form
    newFolder.value = {
      path: '',
      collection: 'default',
      enabled: true,
      file_types: ['pdf', 'docx', 'txt', 'md', 'csv', 'html'],
      recursive: true,
      category: 'uploads',
      tags: [],
    }
    newFolderTags.value = ''
    // Reload stats
    await loadStats()
  }
}

async function handlePause(folderId: string) {
  await disableWatchFolder(folderId)
  await loadStats()
}

async function handleResume(folderId: string) {
  await enableWatchFolder(folderId)
  await loadStats()
}

async function handleDelete(folderId: string) {
  if (await confirm({ title: t('common.confirm'), message: t('knowledge.watchFolders.confirmDelete') })) {
    await deleteWatchFolder(folderId)
    await loadStats()
  }
}

onMounted(async () => {
  await loadWatchFolders()
  await loadStats()
})
</script>

<style scoped>
.watch-folders-view {
  padding: 2rem;
}

.view-header h2 {
  font-size: 1.875rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
}

.view-description {
  color: var(--text-secondary);
  margin: 0 0 2rem 0;
}

.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: 0.5rem;
  padding: 1.5rem;
}

.stat-label {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-error {
  color: var(--error);
}

.action-bar {
  margin-bottom: 2rem;
}

.btn-primary,
.btn-secondary,
.btn-action,
.btn-danger {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn-primary {
  background: var(--primary);
  color: white;
}

.btn-primary:hover {
  background: var(--primary-hover);
}

.btn-secondary {
  background: var(--surface-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
}

.btn-secondary:hover {
  background: var(--surface-tertiary);
}

.btn-action {
  background: var(--surface-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
}

.btn-action:hover {
  background: var(--surface-tertiary);
}

.btn-danger {
  background: var(--error);
  color: white;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
}

.btn-danger:hover {
  background: var(--error-hover);
}

.btn-icon {
  width: 1.25rem;
  height: 1.25rem;
}

.loading-state,
.error-state,
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--text-secondary);
}

.empty-icon {
  width: 4rem;
  height: 4rem;
  margin: 0 auto 1rem;
  color: var(--text-tertiary);
}

.empty-hint {
  font-size: 0.875rem;
  margin-top: 0.5rem;
}

.folders-list {
  display: grid;
  gap: 1.5rem;
}

.folder-card {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: 0.5rem;
  padding: 1.5rem;
}

.folder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border-primary);
}

.folder-path {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: var(--text-primary);
}

.path-icon {
  width: 1.25rem;
  height: 1.25rem;
  color: var(--primary);
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
}

.status-active {
  background: var(--success-bg);
  color: var(--success);
}

.status-inactive {
  background: var(--surface-tertiary);
  color: var(--text-tertiary);
}

.folder-details,
.folder-stats {
  margin-bottom: 1rem;
}

.detail-row,
.stat-item {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0;
  font-size: 0.875rem;
}

.detail-label,
.stat-label {
  color: var(--text-secondary);
}

.detail-value,
.stat-value {
  color: var(--text-primary);
  font-weight: 500;
}

.folder-actions {
  display: flex;
  gap: 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-primary);
}

.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: var(--surface-primary);
  border-radius: 0.5rem;
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-primary);
}

.dialog-header h3 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.dialog-close {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem;
  color: var(--text-secondary);
}

.dialog-close:hover {
  color: var(--text-primary);
}

.dialog-close svg {
  width: 1.5rem;
  height: 1.5rem;
}

.dialog-content {
  padding: 1.5rem;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.form-group input[type="text"] {
  width: 100%;
  padding: 0.625rem;
  border: 1px solid var(--border-primary);
  border-radius: 0.375rem;
  background: var(--surface-secondary);
  color: var(--text-primary);
  font-size: 0.875rem;
}

.checkbox-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-primary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  cursor: pointer;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 2rem;
}
</style>
