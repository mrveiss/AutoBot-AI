<template>
  <div class="backup-manager">
    <div class="section-header">
      <div class="header-content">
        <h4><i class="fas fa-database"></i> {{ $t('knowledge.backup.title') }}</h4>
        <p class="header-description">
          {{ $t('knowledge.backup.description') }}
        </p>
      </div>
    </div>

    <div class="backup-content">
      <!-- Create Backup -->
      <div class="backup-section">
        <h5>{{ $t('knowledge.backup.createBackup') }}</h5>
        <div class="backup-options">
          <label class="option-checkbox">
            <input type="checkbox" v-model="backupOptions.includeEmbeddings" />
            <span class="checkmark"></span>
            <span>{{ $t('knowledge.backup.includeEmbeddings') }}</span>
          </label>
          <label class="option-checkbox">
            <input type="checkbox" v-model="backupOptions.compression" />
            <span class="checkmark"></span>
            <span>{{ $t('knowledge.backup.useCompression') }}</span>
          </label>
        </div>
        <div class="backup-description">
          <input
            type="text"
            v-model="backupOptions.description"
            :placeholder="$t('knowledge.backup.descriptionPlaceholder')"
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
          {{ isCreatingBackup ? $t('knowledge.backup.creatingBackup') : $t('knowledge.backup.createBackup') }}
        </BaseButton>
      </div>

      <!-- Backup List -->
      <div class="backups-list-section">
        <div class="list-header">
          <h5>{{ $t('knowledge.backup.availableBackups') }}</h5>
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
          <span>{{ $t('knowledge.backup.loadingBackups') }}</span>
        </div>

        <div v-else-if="backups.length === 0" class="empty-state">
          <i class="fas fa-folder-open"></i>
          <p>{{ $t('knowledge.backup.noBackupsFound') }}</p>
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
                :title="$t('knowledge.backup.restoreTitle')"
              >
                <i class="fas fa-upload"></i>
              </button>
              <button
                class="action-btn delete"
                @click.stop="deleteBackup(backup.name)"
                :disabled="isDeletingBackup"
                :title="$t('knowledge.backup.deleteTitle')"
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
import { useI18n } from 'vue-i18n'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { formatFileSize, formatDateTime } from '@/utils/formatHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()

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
    showStatus('error', t('knowledge.backup.errorLoadBackups'))
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
      showStatus('success', t('knowledge.backup.statusBackupCreated', { name: data.backup_name }))
      backupOptions.value.description = ''
      await loadBackups()
    } else {
      throw new Error(data.message || t('knowledge.backup.errorCreateBackup'))
    }
  } catch (error: any) {
    logger.error('Failed to create backup:', error)
    showStatus('error', error.message || t('knowledge.backup.errorCreateBackup'))
  } finally {
    isCreatingBackup.value = false
  }
}

const restoreBackup = async (backupName: string) => {
  const confirmed = window.confirm(
    t('knowledge.backup.confirmRestore', { name: backupName })
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
      throw new Error(dryRunData.message || t('knowledge.backup.errorValidation'))
    }

    // Confirm actual restore
    const confirmRestore = window.confirm(
      t('knowledge.backup.backupValidated', { count: dryRunData.total_facts_in_backup })
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
      showStatus('success', t('knowledge.backup.statusRestored', { count: restoreData.restored }))
    } else {
      throw new Error(restoreData.message || t('knowledge.backup.errorRestoreBackup'))
    }
  } catch (error: any) {
    logger.error('Failed to restore backup:', error)
    showStatus('error', error.message || t('knowledge.backup.errorRestoreBackup'))
  } finally {
    isRestoring.value = false
  }
}

const deleteBackup = async (backupName: string) => {
  const confirmed = window.confirm(
    t('knowledge.backup.confirmDelete', { name: backupName })
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
      showStatus('success', t('knowledge.backup.statusDeleted'))
      await loadBackups()
    } else {
      throw new Error(data.message || t('knowledge.backup.errorDeleteBackup'))
    }
  } catch (error: any) {
    logger.error('Failed to delete backup:', error)
    showStatus('error', error.message || t('knowledge.backup.errorDeleteBackup'))
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
/** Issue #704: Migrated to design tokens */
.backup-manager {
  background: var(--bg-primary);
}

.section-header {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.section-header h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-1) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.header-description {
  color: var(--text-secondary);
  margin: 0;
  font-size: var(--text-sm);
}

.backup-content {
  padding: var(--spacing-5);
}

.backup-section {
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
}

.backup-section h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-4) 0;
}

.backup-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-4);
}

.option-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.option-checkbox input[type="checkbox"] {
  display: none;
}

.checkmark {
  width: 1rem;
  height: 1rem;
  border: 2px solid var(--border-strong);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
}

.option-checkbox input:checked ~ .checkmark {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.option-checkbox input:checked ~ .checkmark::after {
  content: '\2713';
  color: var(--text-on-primary);
  font-size: 0.625rem;
}

.backup-description {
  margin-bottom: var(--spacing-4);
}

.description-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.description-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.backups-list-section h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
}

.loading-state,
.empty-state {
  text-align: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
}

.loading-state i,
.empty-state i {
  font-size: 2rem;
  margin-bottom: var(--spacing-2);
  display: block;
}

.backups-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  max-height: 300px;
  overflow-y: auto;
}

.backup-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-200);
}

.backup-item:hover {
  border-color: var(--color-primary);
}

.backup-item.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.backup-icon {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-md);
  font-size: 1rem;
}

.backup-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.backup-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.backup-meta {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.backup-desc {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-style: italic;
}

.backup-actions {
  display: flex;
  gap: var(--spacing-2);
}

.action-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn.restore {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.action-btn.restore:hover {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.action-btn.delete {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.action-btn.delete:hover {
  background: var(--color-error);
  color: var(--text-on-primary);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.status-message {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-top: var(--spacing-4);
}

.status-message.success {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success);
  color: var(--color-success);
}

.status-message.error {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  color: var(--color-error);
}

.status-message span {
  flex: 1;
}

.dismiss-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--spacing-1);
  color: inherit;
  opacity: 0.7;
}
</style>
