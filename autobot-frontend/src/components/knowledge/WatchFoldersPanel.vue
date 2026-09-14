<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <div class="watch-folders-panel">
    <div class="watch-folders-header">
      <p class="watch-folders-description">
        {{ $t('knowledge.watchFolders.description') }}
      </p>
    </div>

    <!-- Stats Overview -->
    <div v-if="stats" class="stats-overview">
      <div class="stat-card">
        <div class="stat-label">{{ $t('knowledge.watchFolders.statsTotalFolders') }}</div>
        <div class="stat-value">{{ stats.total_folders }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ $t('knowledge.watchFolders.statsActive') }}</div>
        <div class="stat-value">{{ stats.active_folders }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ $t('knowledge.watchFolders.statsFilesIngested') }}</div>
        <div class="stat-value">{{ stats.total_files_ingested }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ $t('knowledge.watchFolders.statsErrors') }}</div>
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
        <Icon name="plus" class="btn-icon" />
        {{ $t('knowledge.watchFolders.addButton') }}
      </button>
    </div>

    <!-- Watch Folders List -->
    <div v-if="loading" class="loading-state">
      {{ $t('common.loading') }}
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="btn-secondary" @click="loadWatchFolders">
        {{ $t('common.retry') }}
      </button>
    </div>

    <div v-else-if="watchFolders.length === 0" class="empty-state">
      <Icon name="folder" class="empty-icon" />
      <p>{{ $t('knowledge.watchFolders.emptyTitle') }}</p>
      <p class="empty-hint">{{ $t('knowledge.watchFolders.emptyHint') }}</p>
    </div>

    <div v-else class="folders-list">
      <div
        v-for="folder in watchFolders"
        :key="folder.folder_id"
        class="folder-card"
      >
        <div class="folder-header">
          <div class="folder-path">
            <Icon name="folder" class="path-icon" />
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
              {{ folder.is_watching ? $t('knowledge.watchFolders.statusWatching') : $t('knowledge.watchFolders.statusPaused') }}
            </span>
          </div>
        </div>

        <div class="folder-details">
          <div class="detail-row">
            <span class="detail-label">{{ $t('knowledge.watchFolders.detailCollection') }}</span>
            <span class="detail-value">{{ folder.collection }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">{{ $t('knowledge.watchFolders.detailCategory') }}</span>
            <span class="detail-value">{{ folder.category }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">{{ $t('knowledge.watchFolders.detailFileTypes') }}</span>
            <span class="detail-value">{{ folder.file_types.join(', ') }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">{{ $t('knowledge.watchFolders.detailRecursive') }}</span>
            <span class="detail-value">{{ folder.recursive ? $t('common.yes') : $t('common.no') }}</span>
          </div>
          <div v-if="folder.tags.length > 0" class="detail-row">
            <span class="detail-label">{{ $t('knowledge.watchFolders.detailTags') }}</span>
            <span class="detail-value">{{ folder.tags.join(', ') }}</span>
          </div>
        </div>

        <div v-if="folder.stats" class="folder-stats">
          <div class="stat-item">
            <span class="stat-label">{{ $t('knowledge.watchFolders.statFilesIngested') }}</span>
            <span class="stat-value">{{ folder.stats.files_ingested }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">{{ $t('knowledge.watchFolders.lastChange') }}</span>
            <span class="stat-value">
              {{ folder.stats.last_change ? formatDate(folder.stats.last_change) : $t('knowledge.watchFolders.never') }}
            </span>
          </div>
          <div v-if="folder.stats.errors > 0" class="stat-item">
            <span class="stat-label">{{ $t('knowledge.watchFolders.statsErrors') }}</span>
            <span class="stat-value stat-error">{{ folder.stats.errors }}</span>
          </div>
        </div>

        <div class="folder-actions">
          <button
            v-if="folder.is_watching"
            class="btn-action"
            @click="folder.folder_id && handlePause(folder.folder_id)"
          >
            <Icon name="pause" class="btn-icon" />
            {{ $t('knowledge.watchFolders.pause') }}
          </button>
          <button
            v-else
            class="btn-action btn-primary"
            @click="folder.folder_id && handleResume(folder.folder_id)"
          >
            <Icon name="play" class="btn-icon" />
            {{ $t('knowledge.watchFolders.resume') }}
          </button>
          <button
            class="btn-action btn-danger"
            @click="folder.folder_id && handleDelete(folder.folder_id)"
          >
            <Icon name="trash-alt" class="btn-icon" />
            {{ $t('common.delete') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Add Watch Folder Dialog -->
    <BaseModal
      :close-label="$t('ui.modal.closeDialog')"
      :model-value="showAddDialog"
      :title="$t('knowledge.watchFolders.dialogTitle')"
      size="md"
      @close="showAddDialog = false"
    >
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label for="path">{{ $t('knowledge.watchFolders.folderPathLabel') }}</label>
          <input
            id="path"
            v-model="newFolder.path"
            type="text"
            class="form-input"
            :placeholder="$t('knowledge.watchFolders.folderPathPlaceholder')"
            required
          />
        </div>

        <div class="form-group">
          <label for="collection">{{ $t('knowledge.watchFolders.collectionLabel') }}</label>
          <input
            id="collection"
            v-model="newFolder.collection"
            type="text"
            class="form-input"
            :placeholder="$t('knowledge.watchFolders.collectionPlaceholder')"
          />
        </div>

        <div class="form-group">
          <label for="category">{{ $t('knowledge.watchFolders.categoryLabel') }}</label>
          <input
            id="category"
            v-model="newFolder.category"
            type="text"
            class="form-input"
            :placeholder="$t('knowledge.watchFolders.categoryPlaceholder')"
          />
        </div>

        <div class="form-group">
          <label for="file-types">{{ $t('knowledge.watchFolders.fileTypesLabel') }}</label>
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
            {{ $t('knowledge.watchFolders.recursiveLabel') }}
          </label>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input
              v-model="newFolder.enabled"
              type="checkbox"
            />
            {{ $t('knowledge.watchFolders.enabledLabel') }}
          </label>
        </div>

        <div class="form-group">
          <label for="tags">{{ $t('knowledge.watchFolders.tagsLabel') }}</label>
          <input
            id="tags"
            v-model="newFolderTags"
            type="text"
            class="form-input"
            :placeholder="$t('knowledge.watchFolders.tagsPlaceholder')"
          />
        </div>
      </form>

      <template #actions>
        <button type="button" class="btn-secondary" @click="showAddDialog = false">
          {{ $t('common.cancel') }}
        </button>
        <button type="submit" class="btn-primary" @click="handleSubmit">
          {{ $t('knowledge.watchFolders.addButton') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { BaseModal } from '@autobot/ui'
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
.watch-folders-panel {
  padding: var(--spacing-6);
}

.watch-folders-header {
  margin-bottom: var(--spacing-6);
}

.watch-folders-description {
  color: var(--text-secondary);
  margin: 0;
  font-size: var(--text-sm);
}

.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-error {
  color: var(--color-danger);
}

.action-bar {
  margin-bottom: var(--spacing-6);
}

.btn-primary,
.btn-secondary,
.btn-action,
.btn-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200);
  border: none;
}

.btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
}

.btn-action {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-xs);
}

.btn-action:hover {
  background: var(--bg-tertiary);
}

.btn-danger {
  background: var(--color-danger);
  color: var(--text-on-primary);
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-xs);
}

.btn-danger:hover {
  background: var(--color-danger-hover);
}

.btn-icon {
  width: 1.25rem;
  height: 1.25rem;
}

.loading-state,
.error-state,
.empty-state {
  text-align: center;
  padding: var(--spacing-12) var(--spacing-4);
  color: var(--text-secondary);
}

.empty-icon {
  width: 4rem;
  height: 4rem;
  margin: 0 auto var(--spacing-4);
  color: var(--text-tertiary);
}

.empty-hint {
  font-size: var(--text-sm);
  margin-top: var(--spacing-2);
}

.folders-list {
  display: grid;
  gap: var(--spacing-6);
}

.folder-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.folder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.folder-path {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.path-icon {
  width: 1.25rem;
  height: 1.25rem;
  color: var(--color-primary);
}

.status-badge {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.status-active {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-inactive {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.folder-details,
.folder-stats {
  margin-bottom: var(--spacing-4);
}

.detail-row,
.stat-item {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-2) 0;
  font-size: var(--text-sm);
}

.detail-label,
.stat-label {
  color: var(--text-secondary);
}

.detail-value,
.stat-value {
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.folder-actions {
  display: flex;
  gap: var(--spacing-3);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.form-group {
  margin-bottom: var(--spacing-5);
}

.form-group label {
  display: block;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.form-input {
  width: 100%;
  padding: var(--spacing-2-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  transition: all var(--duration-200);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--ring-primary);
}

.form-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.checkbox-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-3);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  cursor: pointer;
}
</style>
