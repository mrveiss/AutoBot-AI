<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1579: Extracted from CodebaseAnalytics.vue — Progress indicators -->
<template>
  <!-- Unified Operation Progress — Issues #1190, #1365, #1366 -->
  <!-- Single status bar covering indexing and code-smell operations; shows all available detail -->
  <div
    v-if="analyzing || analyzingCodeSmells || (progressStatus && progressStatus !== 'Ready' && progressStatus !== 'Ready (state reset)')"
    class="progress-container"
    :class="{
      'progress-container--idle': !analyzing && !analyzingCodeSmells,
      'code-smells-progress': analyzingCodeSmells && !analyzing
    }"
  >
    <div class="progress-header">
      <div class="progress-title">
        <i :class="
          (analyzing || analyzingCodeSmells)
            ? 'fas fa-spinner fa-spin'
            : progressStatus.includes('completed') || progressStatus.includes('complete')
              ? 'check-circle'
              : progressStatus.includes('failed') || progressStatus.includes('cancelled')
                ? 'times-circle'
                : 'info-circle'
        "></i>
        {{ analyzing ? $t('analytics.codebase.progress.indexingInProgress') : analyzingCodeSmells ? codeSmellsProgressTitle : $t('analytics.codebase.progress.indexingStatus') }}
      </div>
      <div v-if="currentJobId && analyzing" class="job-id">{{ $t('analytics.codebase.progress.job') }}: {{ currentJobId.substring(0, 8) }}...</div>
    </div>

    <!-- Phase Progress (active indexing only) -->
    <div v-if="analyzing && jobPhases" class="phase-progress">
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
        <Icon :name="getPhaseIcon(phase.status)" />
        <span>{{ phase.name }}</span>
      </div>
    </div>

    <!-- Progress Bar: determinate for indexing/idle, indeterminate for code-smells-only -->
    <div class="progress-bar">
      <div
        class="progress-fill"
        :class="{ indeterminate: analyzingCodeSmells && !analyzing }"
        :style="analyzingCodeSmells && !analyzing ? {} : { width: progressPercent + '%' }"
      ></div>
    </div>
    <div class="progress-status">{{ progressStatus }}</div>

    <!-- Batch Progress (active indexing only) -->
    <div v-if="analyzing && jobBatches && jobBatches.total_batches > 0" class="batch-progress">
      <div class="batch-header">
        <span class="batch-label">{{ $t('analytics.codebase.progress.batchProgress') }}:</span>
        <span class="batch-count">{{ jobBatches.completed_batches }} / {{ jobBatches.total_batches }}</span>
      </div>
      <div class="batch-bar">
        <div
          class="batch-fill"
          :style="{ width: (jobBatches.completed_batches / jobBatches.total_batches * 100) + '%' }"
        ></div>
      </div>
    </div>

    <!-- Live Stats (active indexing only) -->
    <div v-if="analyzing && jobStats" class="live-stats">
      <div class="stat-item">
        <Icon name="file-code" />
        <span>{{ jobStats.files_scanned }} {{ $t('analytics.codebase.progress.files') }}</span>
      </div>
      <div class="stat-item">
        <Icon name="exclamation-triangle" />
        <span>{{ jobStats.problems_found }} {{ $t('analytics.codebase.progress.problems') }}</span>
      </div>
      <div class="stat-item">
        <Icon name="code" />
        <span>{{ jobStats.functions_found }} {{ $t('analytics.codebase.progress.functions') }}</span>
      </div>
      <div class="stat-item">
        <Icon name="cubes" />
        <span>{{ jobStats.classes_found }} {{ $t('analytics.codebase.progress.classes') }}</span>
      </div>
      <div class="stat-item" v-if="jobStats.items_stored > 0">
        <Icon name="database" />
        <span>{{ jobStats.items_stored }} {{ $t('analytics.codebase.progress.stored') }}</span>
      </div>
    </div>
  </div>

  <!-- Scan Runner Progress (#1418) -->
  <div v-if="scanRunner.running.value || scanRunner.results.value.length > 0" class="scan-runner-progress">
    <div class="scan-runner-header">
      <span class="scan-runner-title">
        <i :class="scanRunner.running.value ? 'fas fa-spinner fa-spin' : 'check-circle'"></i>
        {{ $t('analytics.codebase.scanRunner.title') }}
      </span>
      <span class="scan-runner-count">
        {{ scanRunner.completedCount.value }} / {{ scanRunner.totalCount.value }}
      </span>
    </div>
    <div class="mini-progress">
      <div class="mini-progress-bar" :style="{ width: scanRunner.progress.value + '%' }"></div>
    </div>
    <div class="scan-runner-items">
      <div
        v-for="result in scanRunner.results.value"
        :key="result.id"
        class="scan-runner-item"
        :class="'scan-' + result.status"
      >
        <i :class="{
          'fas fa-spinner fa-spin': result.status === 'running',
          'check': result.status === 'completed',
          'times': result.status === 'failed',
          'forward': result.status === 'skipped',
          'clock': result.status === 'pending',
        }"></i>
        <span class="scan-label">{{ result.label }}</span>
        <span v-if="result.durationMs != null" class="scan-duration">{{ result.durationMs }}ms</span>
        <span v-if="result.error" class="scan-error">{{ result.error }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Analytics Progress Section Component
 *
 * Displays unified operation progress (indexing + code smells) and scan
 * runner progress for the codebase analytics dashboard.
 *
 * Issue #1579: Extracted from CodebaseAnalytics.vue
 */

import Icon from '@/components/ui/Icon.vue'
import type { ScanRunnerReturn } from '@/composables/useAnalyticsScanRunner'

interface JobPhase {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed'
}

interface JobPhasesData {
  phase_list: JobPhase[]
}

interface JobBatchesData {
  total_batches: number
  completed_batches: number
}

interface JobStatsData {
  files_scanned: number
  problems_found: number
  functions_found: number
  classes_found: number
  items_stored: number
}

defineProps<{
  analyzing: boolean
  analyzingCodeSmells: boolean
  progressStatus: string
  progressPercent: number
  currentJobId: string | null
  jobPhases: JobPhasesData | null
  jobBatches: JobBatchesData | null
  jobStats: JobStatsData | null
  scanRunner: ScanRunnerReturn
  codeSmellsProgressTitle: string
}>()

defineEmits<{
  stop: []
}>()

/** Get icon class for a job phase based on its status. */
function getPhaseIcon(status: string): string {
  switch (status) {
    case 'completed':
      return 'check-circle'
    case 'running':
      return 'spinner'
    case 'pending':
    default:
      return 'circle'
  }
}
</script>

<style scoped>
.progress-container {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-6);
  border: 1px solid var(--border-default);
}

/* Issue #1190: Idle state — lighter styling when showing last-known status */
.progress-container--idle {
  opacity: 0.85;
  border-color: var(--border-subtle, var(--border-default));
}

.progress-container--idle .progress-title {
  color: var(--text-secondary);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-3);
}

.progress-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--chart-green);
  font-weight: var(--font-semibold);
}

.job-id {
  color: var(--text-tertiary);
  font-size: 0.8em;
  font-family: var(--font-mono);
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
  margin-bottom: var(--spacing-2);
}

.progress-fill {
  height: 100%;
  background: var(--color-success);
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-default);
}

.progress-fill.indeterminate {
  width: 30%;
  animation: indeterminate 1.5s infinite ease-in-out;
}

@keyframes indeterminate {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(400%);
  }
}

.code-smells-progress {
  border-left: 4px solid var(--chart-pink);
}

.code-smells-progress .progress-fill {
  background: var(--chart-purple);
}

.progress-status {
  color: var(--text-primary);
  font-size: 0.9em;
  font-weight: var(--font-medium);
}

/* Phase Progress */
.phase-progress {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
}

.phase-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
  font-size: 0.85em;
  transition: var(--transition-all);
}

.phase-item.phase-completed {
  color: var(--chart-green);
  background: var(--color-success-bg-hover);
  border: 1px solid var(--color-success-border);
}

.phase-item.phase-running {
  color: var(--chart-blue);
  background: var(--color-info-bg-hover);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.phase-item.phase-pending {
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
}

.phase-item i {
  font-size: 0.9em;
}

/* Batch Progress */
.batch-progress {
  margin-top: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
}

.batch-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.batch-label {
  color: var(--text-secondary);
  font-size: 0.85em;
}

.batch-count {
  color: var(--chart-green);
  font-weight: var(--font-semibold);
  font-family: var(--font-mono);
}

.batch-bar {
  width: 100%;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.batch-fill {
  height: 100%;
  background: var(--color-success);
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-default);
}

/* Live Stats */
.live-stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
  margin-top: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-card);
  border-radius: var(--radius-md);
}

.live-stats .stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  color: var(--text-secondary);
  font-size: 0.85em;
}

.live-stats .stat-item i {
  color: var(--chart-blue);
  width: 16px;
  text-align: center;
}

/* Scan Runner Progress (#1418) */
.scan-runner-progress {
  margin: var(--spacing-3) 0;
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}
.scan-runner-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}
.scan-runner-title {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}
.scan-runner-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.scan-runner-progress .mini-progress {
  width: 100%;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-xs);
  overflow: hidden;
  margin-bottom: var(--spacing-2);
}
.scan-runner-progress .mini-progress-bar {
  height: 100%;
  background: var(--color-purple);
  transition: width var(--duration-300) var(--ease-out);
}
.scan-runner-items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}
.scan-runner-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: 2px var(--spacing-2);
  font-size: var(--text-xs);
  border-radius: var(--radius-xs);
  background: var(--bg-tertiary);
}
.scan-runner-item.scan-completed { color: var(--color-success); }
.scan-runner-item.scan-failed { color: var(--color-error); }
.scan-runner-item.scan-running { color: var(--color-info); }
.scan-runner-item.scan-skipped { color: var(--text-tertiary); }
.scan-runner-item.scan-pending { color: var(--text-secondary); }
.scan-label {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scan-duration {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}
.scan-error {
  color: var(--color-error);
  font-size: var(--text-xs);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
