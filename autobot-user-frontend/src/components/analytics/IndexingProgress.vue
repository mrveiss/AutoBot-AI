<template>
  <div v-if="analyzing" class="progress-container">
    <div class="progress-header">
      <div class="progress-title">
        <i class="fas fa-spinner fa-spin"></i>
        Indexing in Progress
      </div>
      <div v-if="currentJobId" class="job-id">Job: {{ currentJobId.substring(0, 8) }}...</div>
    </div>

    <!-- Phase Progress -->
    <div v-if="jobPhases" class="phase-progress">
      <div
        v-for="phase in jobPhases.phase_list"
        :key="phase.id"
        class="phase-item"
        :class="{
          'phase-completed': phase.status === 'completed',
          'phase-running': phase.status === 'running',
          'phase-pending': phase.status === 'pending'
        }"
      >
        <i :class="getPhaseIcon(phase.status)"></i>
        <span>{{ phase.name }}</span>
      </div>
    </div>

    <!-- Main Progress Bar -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
    </div>
    <div class="progress-status">{{ progressStatus }}</div>

    <!-- Batch Progress -->
    <div v-if="jobBatches && jobBatches.total_batches > 0" class="batch-progress">
      <div class="batch-header">
        <span class="batch-label">Batch Progress:</span>
        <span class="batch-count">{{ jobBatches.completed_batches }} / {{ jobBatches.total_batches }}</span>
      </div>
      <div class="batch-bar">
        <div
          class="batch-fill"
          :style="{ width: (jobBatches.completed_batches / jobBatches.total_batches * 100) + '%' }"
        ></div>
      </div>
    </div>

    <!-- Live Stats -->
    <div v-if="jobStats" class="live-stats">
      <div class="stat-item">
        <i class="fas fa-file-code"></i>
        <span>{{ jobStats.files_scanned }} files</span>
      </div>
      <div class="stat-item">
        <i class="fas fa-exclamation-triangle"></i>
        <span>{{ jobStats.problems_found }} problems</span>
      </div>
      <div class="stat-item">
        <i class="fas fa-code"></i>
        <span>{{ jobStats.functions_found }} functions</span>
      </div>
      <div class="stat-item">
        <i class="fas fa-cubes"></i>
        <span>{{ jobStats.classes_found }} classes</span>
      </div>
      <div class="stat-item" v-if="jobStats.items_stored > 0">
        <i class="fas fa-database"></i>
        <span>{{ jobStats.items_stored }} stored</span>
      </div>
    </div>
  </div>

  <!-- Code Smells Analysis Progress -->
  <div v-if="analyzingCodeSmells" class="progress-container code-smells-progress">
    <div class="progress-header">
      <div class="progress-title">
        <i class="fas fa-spinner fa-spin"></i>
        {{ codeSmellsProgressTitle }}
      </div>
    </div>
    <div class="progress-bar">
      <div class="progress-fill indeterminate"></div>
    </div>
    <div class="progress-status">{{ progressStatus }}</div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Indexing Progress Component
 *
 * Displays indexing progress with phases, batches, and live stats.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 * Issue #704: Migrated to design tokens
 */

interface Phase {
  id: string
  name: string
  status: 'completed' | 'running' | 'pending'
}

interface JobPhases {
  phase_list: Phase[]
}

interface JobBatches {
  total_batches: number
  completed_batches: number
}

interface JobStats {
  files_scanned: number
  problems_found: number
  functions_found: number
  classes_found: number
  items_stored: number
}

interface Props {
  analyzing: boolean
  currentJobId: string | null
  progressPercent: number
  progressStatus: string
  jobPhases: JobPhases | null
  jobBatches: JobBatches | null
  jobStats: JobStats | null
  analyzingCodeSmells: boolean
  codeSmellsProgressTitle: string
}

defineProps<Props>()

const getPhaseIcon = (status: string): string => {
  switch (status) {
    case 'completed': return 'fas fa-check-circle'
    case 'running': return 'fas fa-spinner fa-spin'
    case 'pending':
    default: return 'fas fa-circle'
  }
}
</script>

<style scoped>
.progress-container {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  margin-bottom: var(--spacing-6);
  border: 1px solid var(--border-default);
}

.code-smells-progress {
  background: var(--bg-secondary);
  border-color: var(--border-default);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
}

.progress-title {
  color: var(--chart-cyan);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.job-id {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.phase-progress {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
  flex-wrap: wrap;
}

.phase-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-sm);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-full);
  transition: var(--transition-all);
}

.phase-pending {
  color: var(--text-muted);
  background: var(--bg-hover);
}

.phase-running {
  color: var(--chart-cyan);
  background: rgba(6, 182, 212, 0.15);
}

.phase-completed {
  color: var(--color-success);
  background: var(--color-success-bg);
}

.progress-bar {
  height: 8px;
  background: var(--bg-active);
  border-radius: var(--radius-default);
  overflow: hidden;
  margin-bottom: var(--spacing-2);
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: var(--radius-default);
  transition: width var(--duration-300) var(--ease-out);
}

.progress-fill.indeterminate {
  width: 30%;
  animation: indeterminate 1.5s infinite ease-in-out;
}

@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

.progress-status {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.batch-progress {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--bg-active);
}

.batch-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.batch-label {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.batch-count {
  color: var(--chart-cyan);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.batch-bar {
  height: 4px;
  background: var(--bg-active);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.batch-fill {
  height: 100%;
  background: var(--color-success-light);
  border-radius: var(--radius-xs);
  transition: width var(--duration-300);
}

.live-stats {
  display: flex;
  gap: var(--spacing-5);
  flex-wrap: wrap;
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--bg-active);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.stat-item i {
  color: var(--chart-cyan);
}
</style>
