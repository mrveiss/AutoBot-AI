<template>
  <div class="backup-manager">
    <div class="section-header">
      <div class="header-content">
        <h4><Icon name="database" /> {{ $t('knowledge.backup.title') }}</h4>
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
          <Icon name="download" v-if="!isCreatingBackup" />
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
            <Icon name="sync" />
          </BaseButton>
        </div>

        <div v-if="isLoadingBackups" class="loading-state">
          <Icon name="spinner" class="animate-spin" />
          <span>{{ $t('knowledge.backup.loadingBackups') }}</span>
        </div>

        <div v-else-if="backups.length === 0" class="empty-state">
          <Icon name="folder-open" />
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
              <Icon name="file" />
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
                <Icon name="upload" />
              </button>
              <button
                class="action-btn delete"
                @click.stop="deleteBackup(backup.name)"
                :disabled="isDeletingBackup"
                :title="$t('knowledge.backup.deleteTitle')"
              >
                <Icon name="trash" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Status Messages -->
      <div v-if="statusMessage" :class="['status-message', statusMessage.type]">
        <Icon :name="statusMessage.icon" />
        <span>{{ statusMessage.text }}</span>
        <button
          @click="statusMessage = null"
          class="dismiss-btn"
          :aria-label="$t('common.dismiss')"
        >
          <Icon name="times" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatFileSize, formatDateTime } from '@/utils/formatHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useKnowledgeBackup, type BackupOptions } from '@/composables/knowledge/useKnowledgeBackup'

const { t } = useI18n()

const logger = createLogger('BackupManager')

interface StatusMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
  icon: string
}

// Composable
const {
  backups,
  isLoadingBackups,
  isCreatingBackup,
  isRestoring,
  isDeletingBackup,
  loadBackups,
  createBackup: _createBackup,
  restoreBackupDryRun,
  restoreBackupActual,
  deleteBackup: _deleteBackup,
} = useKnowledgeBackup()

// Local state
const backupOptions = ref<BackupOptions>({
  includeEmbeddings: true,
  compression: true,
  description: '',
})

const selectedBackup = ref<string | null>(null)
const statusMessage = ref<StatusMessage | null>(null)

// Methods
const showStatus = (type: StatusMessage['type'], text: string) => {
  const icons = {
    success: 'check-circle',
    error: 'exclamation-circle',
    warning: 'exclamation-triangle',
    info: 'info-circle',
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

const createBackup = async () => {
  try {
    const data = await _createBackup(backupOptions.value)
    if (data.status === 'success') {
      showStatus('success', t('knowledge.backup.statusBackupCreated', { name: data.backup_name }))
      backupOptions.value.description = ''
      await loadBackups()
    } else {
      throw new Error(data.message || t('knowledge.backup.errorCreateBackup'))
    }
  } catch (error: unknown) {
    logger.error('Failed to create backup:', error)
    showStatus('error', (error instanceof Error ? error.message : null) || t('knowledge.backup.errorCreateBackup'))
  }
}

const restoreBackup = async (backupName: string) => {
  const confirmed = window.confirm(t('knowledge.backup.confirmRestore', { name: backupName }))
  if (!confirmed) return

  try {
    const dryRunData = await restoreBackupDryRun(backupName)
    if (dryRunData.status !== 'success') {
      throw new Error(dryRunData.message || t('knowledge.backup.errorValidation'))
    }

    const confirmRestore = window.confirm(
      t('knowledge.backup.backupValidated', { count: dryRunData.total_facts_in_backup }),
    )
    if (!confirmRestore) return

    const restoreData = await restoreBackupActual(backupName)
    if (restoreData.status === 'success') {
      showStatus('success', t('knowledge.backup.statusRestored', { count: restoreData.restored }))
    } else {
      throw new Error(restoreData.message || t('knowledge.backup.errorRestoreBackup'))
    }
  } catch (error: unknown) {
    logger.error('Failed to restore backup:', error)
    showStatus('error', (error instanceof Error ? error.message : null) || t('knowledge.backup.errorRestoreBackup'))
  }
}

const deleteBackup = async (backupName: string) => {
  const confirmed = window.confirm(t('knowledge.backup.confirmDelete', { name: backupName }))
  if (!confirmed) return

  try {
    const data = await _deleteBackup(backupName)
    if (data.status === 'success') {
      showStatus('success', t('knowledge.backup.statusDeleted'))
      await loadBackups()
    } else {
      throw new Error(data.message || t('knowledge.backup.errorDeleteBackup'))
    }
  } catch (error: unknown) {
    logger.error('Failed to delete backup:', error)
    showStatus('error', (error instanceof Error ? error.message : null) || t('knowledge.backup.errorDeleteBackup'))
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
  margin: var(--spacing-0);
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
.description-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.backups-list-section h5 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
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
  font-size: var(--text-base);
}

.backup-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
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
