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
  background: linear-gradient(135deg, #1e3a5f 0%, #1a1a2e 100%);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  border: 1px solid rgba(0, 212, 255, 0.3);
}

.code-smells-progress {
  background: linear-gradient(135deg, #3d1e5f 0%, #1a1a2e 100%);
  border-color: rgba(233, 30, 99, 0.3);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.progress-title {
  color: #00d4ff;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.job-id {
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  font-family: monospace;
}

.phase-progress {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.phase-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 20px;
  transition: all 0.3s;
}

.phase-pending {
  color: rgba(255, 255, 255, 0.4);
  background: rgba(255, 255, 255, 0.05);
}

.phase-running {
  color: #00d4ff;
  background: rgba(0, 212, 255, 0.15);
}

.phase-completed {
  color: #4caf50;
  background: rgba(76, 175, 80, 0.15);
}

.progress-bar {
  height: 8px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #00d4ff, #00ff88);
  border-radius: 4px;
  transition: width 0.3s ease;
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
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
}

.batch-progress {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.batch-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.batch-label {
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
}

.batch-count {
  color: #00d4ff;
  font-size: 12px;
  font-weight: 600;
}

.batch-bar {
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
}

.batch-fill {
  height: 100%;
  background: #00ff88;
  border-radius: 2px;
  transition: width 0.3s;
}

.live-stats {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
}

.stat-item i {
  color: #00d4ff;
}
</style>
