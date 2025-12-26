<template>
  <div class="memory-orphan-manager">
    <div class="section-header">
      <div class="header-content">
        <h4><i class="fas fa-brain"></i> Memory Entity Cleanup</h4>
        <p class="header-description">
          Find and remove memory entities from deleted conversations
        </p>
      </div>
    </div>

    <div class="orphan-content">
      <!-- Scan Results Summary -->
      <div v-if="orphanScanResult" class="orphan-summary">
        <div class="summary-stats">
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.total_conversation_entities }}</span>
            <span class="stat-label">Conversation Entities</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ orphanScanResult.active_sessions }}</span>
            <span class="stat-label">Active Sessions</span>
          </div>
          <div class="stat-item highlight">
            <span class="stat-value">{{ orphanScanResult.orphaned_count }}</span>
            <span class="stat-label">Orphaned Entities</span>
          </div>
        </div>

        <!-- Orphan Preview -->
        <div v-if="orphanScanResult.orphaned_entities?.length > 0" class="orphan-preview">
          <h5>Preview of Orphaned Entities:</h5>
          <div class="orphan-list">
            <div
              v-for="entity in orphanScanResult.orphaned_entities.slice(0, 10)"
              :key="entity.id"
              class="orphan-item"
            >
              <div class="orphan-meta">
                <span class="orphan-name">{{ entity.name }}</span>
              </div>
              <div v-if="entity.observations?.length" class="orphan-observations">
                <p v-for="(obs, idx) in entity.observations" :key="idx" class="observation-text">
                  {{ obs }}
                </p>
              </div>
              <small class="orphan-session">Session: {{ entity.session_id?.slice(0, 12) }}...</small>
            </div>
          </div>
          <p v-if="orphanScanResult.orphaned_entities.length > 10" class="orphan-more">
            ... and {{ orphanScanResult.orphaned_entities.length - 10 }} more orphaned entities
          </p>
        </div>
      </div>

      <!-- Actions -->
      <div class="orphan-actions">
        <div class="action-card">
          <div class="action-content">
            <div class="action-icon scan">
              <i class="fas fa-search"></i>
            </div>
            <h5>Scan for Orphans</h5>
            <p>Find memory entities from conversations that have been deleted</p>
            <small class="action-meta">Non-destructive scan</small>
          </div>
          <BaseButton
            variant="secondary"
            @click="scanOrphans"
            :disabled="isScanning || isCleaning"
            :loading="isScanning"
            class="action-btn"
          >
            <i v-if="!isScanning" class="fas fa-search"></i>
            {{ isScanning ? 'Scanning...' : 'Scan Now' }}
          </BaseButton>
        </div>

        <div class="action-card warning">
          <div class="action-content">
            <div class="action-icon cleanup">
              <i class="fas fa-broom"></i>
            </div>
            <h5>Clean Up Orphans</h5>
            <p>Remove orphaned memory entities permanently</p>
            <small class="action-meta">
              {{ orphanScanResult?.orphaned_count || 0 }} entities to clean
            </small>
          </div>
          <BaseButton
            variant="warning"
            @click="cleanupOrphans"
            :disabled="!orphanScanResult || orphanScanResult.orphaned_count === 0 || isCleaning || isScanning"
            :loading="isCleaning"
            class="action-btn"
          >
            <i v-if="!isCleaning" class="fas fa-broom"></i>
            {{ isCleaning ? 'Cleaning...' : 'Clean Up' }}
          </BaseButton>
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
import { ref } from 'vue'
import apiClient from '@/utils/ApiClient.ts'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('MemoryOrphanManager')

// Emit events for parent component
const emit = defineEmits<{
  (e: 'cleanup-complete'): void
}>()

// Types
interface OrphanedEntity {
  id: string
  name: string
  session_id: string
  created_at?: string
  observations?: string[]
}

interface OrphanScanResult {
  total_conversation_entities: number
  active_sessions: number
  orphaned_count: number
  orphaned_entities: OrphanedEntity[]
}

interface StatusMessage {
  type: 'success' | 'error' | 'warning' | 'info'
  text: string
  icon: string
}

// State
const orphanScanResult = ref<OrphanScanResult | null>(null)
const isScanning = ref(false)
const isCleaning = ref(false)
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

  // Auto-dismiss success messages
  if (type === 'success') {
    setTimeout(() => {
      if (statusMessage.value?.type === 'success') {
        statusMessage.value = null
      }
    }, 5000)
  }
}

const scanOrphans = async () => {
  if (isScanning.value || isCleaning.value) return

  try {
    isScanning.value = true
    orphanScanResult.value = null
    statusMessage.value = null

    const response = await apiClient.get('/api/memory/entities/orphans')

    // Check if we got a valid Response object
    if (!response || typeof response.ok === 'undefined') {
      throw new Error('Invalid response from server - request may have timed out')
    }

    if (!response.ok) {
      // Safely get error text - response.text may not exist if request failed
      const errorText = typeof response.text === 'function'
        ? await response.text().catch(() => '')
        : ''
      throw new Error(errorText || `Server error: ${response.status}`)
    }

    const data = await response.json()

    if (data.success) {
      orphanScanResult.value = data.data as OrphanScanResult

      if (data.data.orphaned_count > 0) {
        showStatus('warning',
          `Found ${data.data.orphaned_count} orphaned memory entities from deleted conversations`)
      } else {
        showStatus('success',
          `All ${data.data.total_conversation_entities} conversation entities belong to active sessions`)
      }
    } else {
      throw new Error(data.message || 'Failed to scan for orphans')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    logger.error('Failed to scan for memory orphans:', error)
    showStatus('error', errorMessage || 'An error occurred while scanning for orphaned entities')
  } finally {
    isScanning.value = false
  }
}

const cleanupOrphans = async () => {
  if (isCleaning.value || isScanning.value) return
  if (!orphanScanResult.value || orphanScanResult.value.orphaned_count === 0) return

  // Confirm before cleanup
  const confirmed = window.confirm(
    `Are you sure you want to delete ${orphanScanResult.value.orphaned_count} orphaned memory entities?\n\n` +
    `This will permanently remove conversation data from deleted sessions.\n` +
    `This action cannot be undone.`
  )

  if (!confirmed) return

  try {
    isCleaning.value = true

    const response = await apiClient.delete('/api/memory/entities/orphans?dry_run=false')

    // Check if we got a valid Response object
    if (!response || typeof response.ok === 'undefined') {
      throw new Error('Invalid response from server - request may have timed out')
    }

    if (!response.ok) {
      // Safely get error text - response.text may not exist if request failed
      const errorText = typeof response.text === 'function'
        ? await response.text().catch(() => '')
        : ''
      throw new Error(errorText || `Server error: ${response.status}`)
    }

    const data = await response.json()

    if (data.success) {
      const deletedCount = data.data.deleted_count
      const failedCount = data.data.failed_count || 0

      if (failedCount > 0) {
        showStatus('warning', `Deleted ${deletedCount} entities. ${failedCount} failed to delete.`)
      } else {
        showStatus('success', `Successfully removed ${deletedCount} orphaned memory entities.`)
      }

      // Clear the scan result after cleanup
      orphanScanResult.value = null

      // Emit event so parent can refresh
      emit('cleanup-complete')
    } else {
      throw new Error(data.message || 'Failed to cleanup orphans')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    logger.error('Failed to cleanup memory orphans:', error)
    showStatus('error', errorMessage || 'An error occurred while cleaning up orphaned entities')
  } finally {
    isCleaning.value = false
  }
}
</script>

<style scoped>
.memory-orphan-manager {
  background: white;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.section-header {
  padding: 1.25rem;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 0.5rem 0.5rem 0 0;
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

.orphan-content {
  padding: 1.25rem;
}

.orphan-summary {
  margin-bottom: 1.5rem;
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-item {
  text-align: center;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.5rem;
  border: 1px solid #e5e7eb;
}

.stat-item.highlight {
  background: #fef3c7;
  border-color: #f59e0b;
}

.stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: #1f2937;
}

.stat-item.highlight .stat-value {
  color: #b45309;
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 0.25rem;
}

.orphan-preview {
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 0.5rem;
  padding: 1rem;
}

.orphan-preview h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #854d0e;
  margin: 0 0 0.75rem 0;
}

.orphan-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 300px;
  overflow-y: auto;
}

.orphan-item {
  background: white;
  border: 1px solid #fde68a;
  border-radius: 0.375rem;
  padding: 0.75rem;
}

.orphan-meta {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.orphan-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: #1f2937;
}

.orphan-observations {
  margin-bottom: 0.5rem;
}

.observation-text {
  font-size: 0.8125rem;
  color: #4b5563;
  margin: 0.25rem 0;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orphan-session {
  font-size: 0.75rem;
  color: #9ca3af;
}

.orphan-more {
  font-size: 0.875rem;
  color: #6b7280;
  font-style: italic;
  margin: 0.75rem 0 0 0;
  text-align: center;
}

.orphan-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

.action-card {
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 200px;
  transition: all 0.2s;
}

.action-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.action-card.warning {
  border-color: #fcd34d;
  background: #fffbeb;
}

.action-card.warning:hover {
  border-color: #f59e0b;
}

.action-content {
  flex: 1;
}

.action-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  margin-bottom: 1rem;
}

.action-icon.scan {
  background: #dbeafe;
  color: #3b82f6;
}

.action-icon.cleanup {
  background: #fef3c7;
  color: #f59e0b;
}

.action-card h5 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 0.5rem 0;
}

.action-card p {
  color: #6b7280;
  margin: 0 0 1rem 0;
  line-height: 1.5;
}

.action-meta {
  color: #9ca3af;
  font-size: 0.75rem;
  display: block;
  margin-bottom: 1rem;
}

.action-btn {
  width: 100%;
}

/* Status Messages */
.status-message {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 0.5rem;
  margin-top: 1.5rem;
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

.status-message.warning {
  background: #fffbeb;
  border: 1px solid #f59e0b;
  color: #92400e;
}

.status-message.info {
  background: #eff6ff;
  border: 1px solid #3b82f6;
  color: #1e40af;
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

.dismiss-btn:hover {
  opacity: 1;
}

/* Responsive */
@media (max-width: 768px) {
  .orphan-actions {
    grid-template-columns: 1fr;
  }

  .summary-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
