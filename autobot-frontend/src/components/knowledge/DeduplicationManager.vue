<template>
  <div class="deduplication-manager">
    <div class="manager-header">
      <h3>
        <i class="fas fa-copy"></i>
        Duplicate & Orphan Management
      </h3>
      <div class="header-actions">
        <BaseButton
          variant="primary"
          size="sm"
          @click="scanForIssues"
          :disabled="scanning"
          :loading="scanning"
          class="btn-scan"
        >
          <i v-if="!scanning" class="fas fa-search"></i>
          Scan for Issues
        </BaseButton>
      </div>
    </div>

    <!-- Scanning State -->
    <div v-if="scanning && !scanned" class="scanning-state">
      <i class="fas fa-spinner fa-spin"></i>
      Scanning knowledge base for duplicates and orphans...
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-circle"></i>
      {{ error }}
    </div>

    <!-- Results Display -->
    <div v-else-if="scanned" class="results-container">
      <!-- Duplicates Section -->
      <div class="section duplicates-section">
        <div class="section-header">
          <h4>
            <i class="fas fa-clone"></i>
            Duplicate Documents
          </h4>
          <span class="count-badge" :class="{ 'has-issues': duplicateStats.total_duplicates > 0 }">
            {{ duplicateStats.total_duplicates || 0 }} duplicates
          </span>
        </div>

        <div v-if="duplicateStats.total_duplicates > 0" class="section-content">
          <div class="stats-summary">
            <div class="stat-item">
              <span class="stat-label">Total Facts Scanned:</span>
              <span class="stat-value">{{ duplicateStats.total_facts_scanned }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Duplicate Groups:</span>
              <span class="stat-value">{{ duplicateStats.duplicate_groups_found }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Total Duplicates:</span>
              <span class="stat-value warning">{{ duplicateStats.total_duplicates }}</span>
            </div>
          </div>

          <!-- Duplicate Groups Preview -->
          <div class="duplicates-list">
            <div
              v-for="(dup, index) in duplicateStats.duplicates"
              :key="index"
              class="duplicate-group"
            >
              <div class="group-header">
                <div class="group-title">
                  <i class="fas fa-folder"></i>
                  <strong>{{ dup.category }}</strong>
                  <span class="separator">›</span>
                  {{ dup.title }}
                </div>
                <div class="group-count">
                  {{ dup.total_copies }} copies
                  <span class="removed-count">({{ dup.removed_count }} to remove)</span>
                </div>
              </div>
              <div class="group-details">
                <div class="kept-fact">
                  <i class="fas fa-check-circle"></i>
                  Keeping: {{ dup.kept_fact_id?.substring(0, 8) }}...
                  <span class="timestamp">({{ formatDate(dup.kept_created_at) }})</span>
                </div>
              </div>
            </div>
          </div>

          <div class="action-buttons">
            <BaseButton
              variant="warning"
              @click="cleanupDuplicates"
              :disabled="cleaning"
              :loading="cleaning"
              class="btn-cleanup"
            >
              <i v-if="!cleaning" class="fas fa-trash-alt"></i>
              {{ cleaning ? 'Removing Duplicates...' : 'Remove All Duplicates' }}
            </BaseButton>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-check-circle"
          message="No duplicates found!"
          variant="success"
        />
      </div>

      <!-- Orphans Section -->
      <div class="section orphans-section">
        <div class="section-header">
          <h4>
            <i class="fas fa-unlink"></i>
            Orphaned Documents
          </h4>
          <span class="count-badge" :class="{ 'has-issues': orphanStats.orphaned_count > 0 }">
            {{ orphanStats.orphaned_count || 0 }} orphans
          </span>
        </div>

        <div v-if="orphanStats.orphaned_count > 0" class="section-content">
          <div class="stats-summary">
            <div class="stat-item">
              <span class="stat-label">Facts Checked:</span>
              <span class="stat-value">{{ orphanStats.total_facts_checked }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Orphaned Facts:</span>
              <span class="stat-value warning">{{ orphanStats.orphaned_count }}</span>
            </div>
          </div>

          <!-- Orphaned Facts List -->
          <div class="orphans-list">
            <div
              v-for="(orphan, index) in orphanStats.orphaned_facts"
              :key="index"
              class="orphan-item"
            >
              <div class="orphan-header">
                <i class="fas fa-file-circle-xmark"></i>
                <span class="orphan-title">{{ orphan.title }}</span>
              </div>
              <div class="orphan-details">
                <span class="orphan-category">{{ orphan.category }}</span>
                <span class="orphan-path">{{ orphan.file_path }}</span>
              </div>
            </div>
          </div>

          <div class="action-buttons">
            <BaseButton
              variant="danger"
              @click="cleanupOrphans"
              :disabled="cleaning"
              :loading="cleaning"
              class="btn-cleanup"
            >
              <i v-if="!cleaning" class="fas fa-trash-alt"></i>
              {{ cleaning ? 'Removing Orphans...' : 'Remove All Orphans' }}
            </BaseButton>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-check-circle"
          message="No orphaned documents found!"
          variant="success"
        />
      </div>
    </div>

    <!-- Initial State -->
    <div v-else class="initial-state">
      <i class="fas fa-info-circle"></i>
      <p>Click "Scan for Issues" to check for duplicate and orphaned documents in your knowledge base.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { formatDate } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DeduplicationManager')

// Interfaces
interface DuplicateGroup {
  hash: string
  count: number
  fact_ids: string[]
  category?: string
  title?: string
  total_copies?: number
  removed_count?: number
  kept_fact_id?: string
  kept_created_at?: string
}

interface DuplicateStats {
  total_facts_scanned: number
  total_duplicates: number
  duplicate_groups_found: number
  duplicates: DuplicateGroup[]
}

interface OrphanedFact {
  fact_id: string
  content?: string
  title?: string
  category?: string
  file_path?: string
}

interface OrphanStats {
  total_facts_checked: number
  orphaned_count: number
  orphaned_facts: OrphanedFact[]
}

// State
const scanning = ref(false)
const scanned = ref(false)
const cleaning = ref(false)
const error = ref<string | null>(null)

const duplicateStats = ref<DuplicateStats>({
  total_facts_scanned: 0,
  total_duplicates: 0,
  duplicate_groups_found: 0,
  duplicates: []
})

const orphanStats = ref<OrphanStats>({
  total_facts_checked: 0,
  orphaned_count: 0,
  orphaned_facts: []
})

// Scan for both duplicates and orphans
const scanForIssues = async () => {
  scanning.value = true
  scanned.value = false
  error.value = null

  try {
    // Scan for duplicates (dry run)
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const dupResponse = await apiClient.post('/api/knowledge-maintenance/deduplicate?dry_run=true')
    const dupData = await parseApiResponse(dupResponse)

    if (dupData.status === 'success') {
      duplicateStats.value = dupData
    } else {
      throw new Error('Failed to scan for duplicates')
    }

    // Scan for orphans
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const orphanResponse = await apiClient.get('/api/knowledge-maintenance/orphans')
    const orphanData = await parseApiResponse(orphanResponse)

    if (orphanData.status === 'success') {
      orphanStats.value = orphanData
    } else {
      throw new Error('Failed to scan for orphans')
    }

    scanned.value = true
  } catch (err) {
    logger.error('Error scanning for issues:', err)
    error.value = `Error scanning: ${err}`
  } finally {
    scanning.value = false
  }
}

// Cleanup duplicates
const cleanupDuplicates = async () => {
  if (!confirm(`Are you sure you want to remove ${duplicateStats.value.total_duplicates} duplicate documents?\n\nThis will keep the oldest version of each document and remove newer copies.`)) {
    return
  }

  cleaning.value = true
  error.value = null

  try {
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const response = await apiClient.post('/api/knowledge-maintenance/deduplicate?dry_run=false')
    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      logger.info(`Successfully removed ${data.deleted_count} duplicates`)
      // Refresh scan
      await scanForIssues()
    } else {
      error.value = `Failed to remove duplicates: ${data.message || 'Unknown error'}`
    }
  } catch (err) {
    logger.error('Error removing duplicates:', err)
    error.value = `Error removing duplicates: ${err}`
  } finally {
    cleaning.value = false
  }
}

// Cleanup orphans
const cleanupOrphans = async () => {
  if (!confirm(`Are you sure you want to remove ${orphanStats.value.orphaned_count} orphaned documents?\n\nThese are documents whose source files no longer exist.`)) {
    return
  }

  cleaning.value = true
  error.value = null

  try {
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const response = await apiClient.delete('/api/knowledge-maintenance/orphans?dry_run=false')
    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      logger.info(`Successfully removed ${data.deleted_count} orphans`)
      // Refresh scan
      await scanForIssues()
    } else {
      error.value = `Failed to remove orphans: ${data.message || 'Unknown error'}`
    }
  } catch (err) {
    logger.error('Error removing orphans:', err)
    error.value = `Error removing orphans: ${err}`
  } finally {
    cleaning.value = false
  }
}

// NOTE: formatDate removed - now using shared utility from @/utils/formatHelpers
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.deduplication-manager {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  box-shadow: var(--shadow-sm);
  margin-bottom: var(--spacing-6);
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-4);
  border-bottom: 2px solid var(--border-subtle);
}

.manager-header h3 {
  margin: 0;
  font-size: var(--text-xl);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

/* Button styling handled by BaseButton component */

.scanning-state,
.error-state,
.initial-state {
  text-align: center;
  padding: var(--spacing-12) var(--spacing-4);
  color: var(--text-secondary);
}

.scanning-state i,
.error-state i,
.initial-state i {
  font-size: 3rem;
  margin-bottom: var(--spacing-4);
  display: block;
}

.error-state {
  color: var(--color-error);
}

.results-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.section {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.section-header h4 {
  margin: 0;
  font-size: var(--text-lg);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.count-badge {
  padding: var(--spacing-1) var(--spacing-3);
  background: var(--color-success);
  color: var(--text-on-primary);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.count-badge.has-issues {
  background: var(--color-error);
}

.section-content {
  padding: var(--spacing-6);
}

.stats-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.stat-value.warning {
  color: var(--color-error);
}

.duplicates-list,
.orphans-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-6);
  max-height: 400px;
  overflow-y: auto;
}

.duplicate-group {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  background: var(--color-error-bg);
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.group-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.separator {
  color: var(--text-tertiary);
}

.group-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.removed-count {
  color: var(--color-error);
  font-weight: var(--font-medium);
}

.group-details {
  padding-left: var(--spacing-6);
}

.kept-fact {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--color-success);
}

.kept-fact i {
  color: var(--color-success);
}

.timestamp {
  color: var(--text-secondary);
  margin-left: var(--spacing-2);
}

.orphan-item {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  background: var(--color-warning-bg);
}

.orphan-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--color-warning);
}

.orphan-details {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding-left: var(--spacing-6);
  font-size: var(--text-sm);
}

.orphan-category {
  color: var(--color-warning);
  font-weight: var(--font-medium);
}

.orphan-path {
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.action-buttons {
  display: flex;
  gap: var(--spacing-4);
  justify-content: flex-end;
}

/* Button styling handled by BaseButton component */
</style>
