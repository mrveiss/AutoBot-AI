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
                  Keeping: {{ dup.kept_fact_id.substring(0, 8) }}...
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

// Interfaces
interface DuplicateGroup {
  hash: string
  count: number
  fact_ids: string[]
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
    const dupResponse = await apiClient.post('/api/knowledge_base/deduplicate?dry_run=true')
    const dupData = await parseApiResponse(dupResponse)

    if (dupData.status === 'success') {
      duplicateStats.value = dupData
    } else {
      throw new Error('Failed to scan for duplicates')
    }

    // Scan for orphans
    const orphanResponse = await apiClient.get('/api/knowledge_base/orphans')
    const orphanData = await parseApiResponse(orphanResponse)

    if (orphanData.status === 'success') {
      orphanStats.value = orphanData
    } else {
      throw new Error('Failed to scan for orphans')
    }

    scanned.value = true
  } catch (err) {
    console.error('Error scanning for issues:', err)
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
    const response = await apiClient.post('/api/knowledge_base/deduplicate?dry_run=false')
    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      console.log(`Successfully removed ${data.deleted_count} duplicates`)
      // Refresh scan
      await scanForIssues()
    } else {
      error.value = `Failed to remove duplicates: ${data.message || 'Unknown error'}`
    }
  } catch (err) {
    console.error('Error removing duplicates:', err)
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
    const response = await apiClient.delete('/api/knowledge_base/orphans?dry_run=false')
    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      console.log(`Successfully removed ${data.deleted_count} orphans`)
      // Refresh scan
      await scanForIssues()
    } else {
      error.value = `Failed to remove orphans: ${data.message || 'Unknown error'}`
    }
  } catch (err) {
    console.error('Error removing orphans:', err)
    error.value = `Error removing orphans: ${err}`
  } finally {
    cleaning.value = false
  }
}

// NOTE: formatDate removed - now using shared utility from @/utils/formatHelpers
</script>

<style scoped>
.deduplication-manager {
  background: white;
  border-radius: 0.5rem;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  margin-bottom: 1.5rem;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid #f3f4f6;
}

.manager-header h3 {
  margin: 0;
  font-size: 1.25rem;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Button styling handled by BaseButton component */

.scanning-state,
.error-state,
.initial-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #6b7280;
}

.scanning-state i,
.error-state i,
.initial-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  display: block;
}

.error-state {
  color: #dc2626;
}

.results-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.section {
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.section-header h4 {
  margin: 0;
  font-size: 1.1rem;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.count-badge {
  padding: 0.25rem 0.75rem;
  background: #10b981;
  color: white;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 500;
}

.count-badge.has-issues {
  background: #ef4444;
}

.section-content {
  padding: 1.5rem;
}

.stats-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.375rem;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.875rem;
  color: #6b7280;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: #1f2937;
}

.stat-value.warning {
  color: #ef4444;
}

.duplicates-list,
.orphans-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
  max-height: 400px;
  overflow-y: auto;
}

.duplicate-group {
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  padding: 1rem;
  background: #fef2f2;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: #1f2937;
}

.separator {
  color: #9ca3af;
}

.group-count {
  font-size: 0.875rem;
  color: #6b7280;
}

.removed-count {
  color: #dc2626;
  font-weight: 500;
}

.group-details {
  padding-left: 1.5rem;
}

.kept-fact {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #059669;
}

.kept-fact i {
  color: #10b981;
}

.timestamp {
  color: #6b7280;
  margin-left: 0.5rem;
}

.orphan-item {
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  padding: 1rem;
  background: #fffbeb;
}

.orphan-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #92400e;
}

.orphan-details {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding-left: 1.5rem;
  font-size: 0.875rem;
}

.orphan-category {
  color: #d97706;
  font-weight: 500;
}

.orphan-path {
  color: #6b7280;
  font-family: monospace;
}

.action-buttons {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
}

/* Button styling handled by BaseButton component */
</style>
