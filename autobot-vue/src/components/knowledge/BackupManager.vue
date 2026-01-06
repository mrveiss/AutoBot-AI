<template>
  <div class="backup-manager">
    <div class="section-header">
      <div class="header-content">
        <h4><i class="fas fa-database"></i> Backup & Restore</h4>
        <p class="header-description">
          Create and manage knowledge base backups
        </p>
      </div>
    </div>

    <div class="backup-content">
      <!-- Create Backup -->
      <div class="backup-section">
        <h5>Create Backup</h5>
        <div class="backup-options">
          <label class="option-checkbox">
            <input type="checkbox" v-model="backupOptions.includeEmbeddings" />
            <span class="checkmark"></span>
            <span>Include embeddings (larger file)</span>
          </label>
          <label class="option-checkbox">
            <input type="checkbox" v-model="backupOptions.compression" />
            <span class="checkmark"></span>
            <span>Use compression</span>
          </label>
        </div>
        <div class="backup-description">
          <input
            type="text"
            v-model="backupOptions.description"
            placeholder="Optional description for this backup..."
            class="description-input"
          />
        </div>
        <BaseButton
          variant="primary"
          @click="createBackup"
          :disabled="isCreatingBackup"
          :loading="isCreatingBackup"
        >
          <i v-if="!isCreatingBackup" class="fas fa-download"></i>
          {{ isCreatingBackup ? 'Creating Backup...' : 'Create Backup' }}
        </BaseButton>
      </div>

      <!-- Backup List -->
      <div class="backups-list-section">
        <div class="list-header">
          <h5>Available Backups</h5>
          <BaseButton
            variant="ghost"
            size="sm"
            @click="loadBackups"
            :disabled="isLoadingBackups"
          >
            <i class="fas fa-sync" :class="{ 'fa-spin': isLoadingBackups }"></i>
          </BaseButton>
        </div>

        <div v-if="isLoadingBackups" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading backups...</span>
        </div>

        <div v-else-if="backups.length === 0" class="empty-state">
          <i class="fas fa-folder-open"></i>
          <p>No backups found</p>
        </div>

        <div v-else class="backups-list">
          <div
            v-for="backup in backups"
            :key="backup.name"
            class="backup-item"
            :class="{ selected: selectedBackup === backup.name }"
            @click="selectedBackup = backup.name"
          >
            <div class="backup-icon">
              <i class="fas fa-file-archive"></i>
            </div>
            <div class="backup-info">
              <span class="backup-name">{{ backup.name }}</span>
              <span class="backup-meta">
                {{ formatFileSize(backup.size) }} | {{ formatDateTime(backup.created_at) }}
              </span>
              <span v-if="backup.description" class="backup-desc">{{ backup.description }}</span>
            </div>
            <div class="backup-actions">
              <button
                class="action-btn restore"
                @click.stop="restoreBackup(backup.name)"
                :disabled="isRestoring"
                title="Restore this backup"
              >
                <i class="fas fa-upload"></i>
              </button>
              <button
                class="action-btn delete"
                @click.stop="deleteBackup(backup.name)"
                :disabled="isDeletingBackup"
                title="Delete this backup"
              >
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Status Messages -->
      <div v-if="statusMessage" :class="['status-message', statusMessage.type]">
        <i :class="statusMessage.icon"></i>
        <span>{{ statusMessage.text }}</span>
        <button @click="statusMessage = null" class="dismiss-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { formatFileSize, formatDateTime } from '@/utils/formatHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BackupManager')

// Types
interface BackupOptions {
  includeEmbeddings: boolean
  compression: boolean
  description: string
}

interface BackupInfo {
  name: string
  size: number
  created_at: string
  description?: string
  facts_count?: number
}

interface StatusMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
  icon: string
}

// State
const backupOptions = ref<BackupOptions>({
  includeEmbeddings: true,
  compression: true,
  description: ''
})

const backups = ref<BackupInfo[]>([])
const selectedBackup = ref<string | null>(null)
const isLoadingBackups = ref(false)
const isCreatingBackup = ref(false)
const isRestoring = ref(false)
const isDeletingBackup = ref(false)
const statusMessage = ref<StatusMessage | null>(null)

// Methods
const showStatus = (type: StatusMessage['type'], text: string) => {
  const icons = {
    success: 'fas fa-check-circle',
    error: 'fas fa-exclamation-circle',
    warning: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle'
  }
  statusMessage.value = { type, text, icon: icons[type] }

  if (type === 'success') {
    setTimeout(() => {
      if (statusMessage.value?.type === 'success') {
        statusMessage.value = null
      }
    }, 5000)
  }
}

// Use shared formatDateTime from formatHelpers (code review fix)

const loadBackups = async () => {
  try {
    isLoadingBackups.value = true
    const response = await apiClient.get('/api/knowledge-maintenance/backups')
    const data = await parseApiResponse(response)

    if (data.backups) {
      backups.value = data.backups
    }
  } catch (error) {
    logger.error('Failed to load backups:', error)
    showStatus('error', 'Failed to load backups')
  } finally {
    isLoadingBackups.value = false
  }
}

const createBackup = async () => {
  try {
    isCreatingBackup.value = true

    const response = await apiClient.post('/api/knowledge-maintenance/backup', {
      include_embeddings: backupOptions.value.includeEmbeddings,
      compression: backupOptions.value.compression,
      description: backupOptions.value.description || undefined
    })

    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      showStatus('success', `Backup created: ${data.backup_name}`)
      backupOptions.value.description = ''
      await loadBackups()
    } else {
      throw new Error(data.message || 'Failed to create backup')
    }
  } catch (error: any) {
    logger.error('Failed to create backup:', error)
    showStatus('error', error.message || 'Failed to create backup')
  } finally {
    isCreatingBackup.value = false
  }
}

const restoreBackup = async (backupName: string) => {
  const confirmed = window.confirm(
    `Are you sure you want to restore from "${backupName}"?\n\n` +
    `This will first run in dry-run mode to validate the backup.`
  )

  if (!confirmed) return

  try {
    isRestoring.value = true

    // First, dry run to validate
    const dryRunResponse = await apiClient.post('/api/knowledge-maintenance/restore', {
      backup_file: backupName,
      dry_run: true
    })

    const dryRunData = await parseApiResponse(dryRunResponse)

    if (dryRunData.status !== 'success') {
      throw new Error(dryRunData.message || 'Backup validation failed')
    }

    // Confirm actual restore
    const confirmRestore = window.confirm(
      `Backup validated successfully!\n\n` +
      `Facts in backup: ${dryRunData.total_facts_in_backup}\n\n` +
      `Proceed with restore?`
    )

    if (!confirmRestore) return

    // Actual restore
    const restoreResponse = await apiClient.post('/api/knowledge-maintenance/restore', {
      backup_file: backupName,
      dry_run: false,
      skip_duplicates: true
    })

    const restoreData = await parseApiResponse(restoreResponse)

    if (restoreData.status === 'success') {
      showStatus('success', `Restored ${restoreData.restored} facts from backup`)
    } else {
      throw new Error(restoreData.message || 'Restore failed')
    }
  } catch (error: any) {
    logger.error('Failed to restore backup:', error)
    showStatus('error', error.message || 'Failed to restore backup')
  } finally {
    isRestoring.value = false
  }
}

const deleteBackup = async (backupName: string) => {
  const confirmed = window.confirm(
    `Are you sure you want to delete "${backupName}"?\n\nThis cannot be undone.`
  )

  if (!confirmed) return

  try {
    isDeletingBackup.value = true

    const response = await apiClient.delete('/api/knowledge-maintenance/backup', {
      body: JSON.stringify({ backup_file: backupName }),
      headers: { 'Content-Type': 'application/json' }
    } as any)

    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      showStatus('success', 'Backup deleted')
      await loadBackups()
    } else {
      throw new Error(data.message || 'Failed to delete backup')
    }
  } catch (error: any) {
    logger.error('Failed to delete backup:', error)
    showStatus('error', error.message || 'Failed to delete backup')
  } finally {
    isDeletingBackup.value = false
  }
}

// Lifecycle
onMounted(() => {
  loadBackups()
})
</script>

<style scoped>
.backup-manager {
  background: white;
}

.section-header {
  padding: 1.25rem;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}

.section-header h4 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 0.25rem 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.header-description {
  color: #6b7280;
  margin: 0;
  font-size: 0.875rem;
}

.backup-content {
  padding: 1.25rem;
}

.backup-section {
  margin-bottom: 1.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.backup-section h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  margin: 0 0 1rem 0;
}

.backup-options {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.option-checkbox {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.875rem;
  color: #374151;
}

.option-checkbox input[type="checkbox"] {
  display: none;
}

.checkmark {
  width: 1rem;
  height: 1rem;
  border: 2px solid #d1d5db;
  border-radius: 0.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.option-checkbox input:checked ~ .checkmark {
  background: #3b82f6;
  border-color: #3b82f6;
}

.option-checkbox input:checked ~ .checkmark::after {
  content: '\2713';
  color: white;
  font-size: 0.625rem;
}

.backup-description {
  margin-bottom: 1rem;
}

.description-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.description-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.backups-list-section h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  margin: 0;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 2rem;
  color: #9ca3af;
}

.loading-state i,
.empty-state i {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  display: block;
}

.backups-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 300px;
  overflow-y: auto;
}

.backup-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.backup-item:hover {
  border-color: #3b82f6;
}

.backup-item.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

.backup-icon {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #dbeafe;
  color: #3b82f6;
  border-radius: 0.375rem;
  font-size: 1rem;
}

.backup-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.backup-name {
  font-weight: 500;
  color: #1f2937;
  font-size: 0.875rem;
}

.backup-meta {
  font-size: 0.75rem;
  color: #6b7280;
}

.backup-desc {
  font-size: 0.75rem;
  color: #9ca3af;
  font-style: italic;
}

.backup-actions {
  display: flex;
  gap: 0.5rem;
}

.action-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn.restore {
  background: #dbeafe;
  color: #3b82f6;
}

.action-btn.restore:hover {
  background: #3b82f6;
  color: white;
}

.action-btn.delete {
  background: #fee2e2;
  color: #ef4444;
}

.action-btn.delete:hover {
  background: #ef4444;
  color: white;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.status-message {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 0.5rem;
  margin-top: 1rem;
}

.status-message.success {
  background: #f0fdf4;
  border: 1px solid #10b981;
  color: #065f46;
}

.status-message.error {
  background: #fef2f2;
  border: 1px solid #ef4444;
  color: #991b1b;
}

.status-message span {
  flex: 1;
}

.dismiss-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem;
  color: inherit;
  opacity: 0.7;
}
</style>