<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Header + Debug Controls -->
<template>
  <div class="analytics-header">
    <div class="header-content">
      <h2><i class="fas fa-code"></i> {{ $t('analytics.codebase.title') }}</h2>
      <div class="header-controls">
        <router-link :to="{ name: 'analytics-codebase' }" class="btn-back">
          <i class="fas fa-arrow-left"></i>
          {{ $t('analytics.codebase.buttons.backToProjects') }}
        </router-link>

        <button @click="emit('index-codebase')" :disabled="analyzing" class="btn-primary">
          <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-database'"></i>
          {{ analyzing ? $t('analytics.codebase.buttons.indexing') : $t('analytics.codebase.buttons.indexCodebase') }}
        </button>
        <button
          v-if="analyzing || scanRunnerRunning"
          @click="emit('stop')"
          class="btn-cancel"
        >
          <i class="fas fa-stop-circle"></i>
          {{ $t('analytics.codebase.actions.stop') }}
        </button>
        <button
          @click="emit('run-full-analysis')"
          :disabled="analyzing || (!rootPath && !selectedSource)"
          class="btn-secondary"
        >
          <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-chart-bar'"></i>
          {{ analyzing ? $t('analytics.codebase.buttons.analyzing') : $t('analytics.codebase.buttons.analyzeAll') }}
        </button>

        <!-- Enhanced Debug Controls -->
        <div class="debug-controls" style="margin-top: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
          <button @click="emit('test-declarations')" class="btn-debug btn-debug-success">
            {{ $t('analytics.codebase.buttons.testDeclarations') }}
          </button>
          <button @click="emit('test-duplicates')" class="btn-debug btn-debug-warning">
            {{ $t('analytics.codebase.buttons.testDuplicates') }}
          </button>
          <button @click="emit('test-hardcodes')" class="btn-debug btn-debug-error">
            {{ $t('analytics.codebase.buttons.testHardcodes') }}
          </button>
          <button @click="emit('test-npu')" class="btn-debug btn-debug-purple">
            {{ $t('analytics.codebase.buttons.testNpu') }}
          </button>
          <button @click="emit('test-data-state')" class="btn-debug btn-debug-info">
            {{ $t('analytics.codebase.buttons.debugState') }}
          </button>
          <button @click="emit('reset-state')" class="btn-debug btn-debug-orange">
            {{ $t('analytics.codebase.buttons.resetState') }}
          </button>
          <button @click="emit('test-all-endpoints')" class="btn-debug btn-debug-cyan">
            {{ $t('analytics.codebase.buttons.testAllApis') }}
          </button>
          <!-- Issue #527: API Endpoint Checker -->
          <button
            @click="emit('get-api-coverage')"
            :disabled="loadingApiEndpoints"
            class="btn-debug btn-debug-indigo"
          >
            <i :class="loadingApiEndpoints ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
            {{ loadingApiEndpoints ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.buttons.apiCoverage') }}
          </button>
          <!-- Code Intelligence / Anti-Pattern Detection -->
          <button
            @click="emit('run-code-smells')"
            :disabled="analyzingCodeSmells"
            class="btn-debug btn-debug-pink"
          >
            <i :class="analyzingCodeSmells ? 'fas fa-spinner fa-spin' : 'fas fa-bug'"></i>
            {{ analyzingCodeSmells ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.buttons.codeSmells') }}
          </button>
          <button
            @click="emit('get-health-score')"
            :disabled="analyzingCodeSmells"
            class="btn-debug btn-debug-violet"
          >
            <i class="fas fa-heartbeat"></i> {{ $t('analytics.codebase.buttons.healthScore') }}
          </button>
          <button
            @click="emit('export-report')"
            :disabled="exportingReport"
            class="btn-debug btn-debug-secondary"
          >
            <i :class="exportingReport ? 'fas fa-spinner fa-spin' : 'fas fa-file-export'"></i>
            {{ exportingReport ? $t('analytics.codebase.buttons.exporting') : $t('analytics.codebase.buttons.exportReport') }}
          </button>
          <button
            @click="emit('clear-cache')"
            :disabled="clearingCache"
            class="btn-debug btn-debug-brown"
          >
            <i :class="clearingCache ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
            {{ clearingCache ? $t('analytics.codebase.buttons.clearing') : $t('analytics.codebase.buttons.clearCache') }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Project Header Card (#1713) -->
  <div v-if="selectedSource" class="project-header-card">
    <div class="project-header-info">
      <div class="project-header-name">
        <i :class="selectedSource.source_type === 'github' ? 'fab fa-github' : 'fas fa-folder'"></i>
        {{ selectedSource.name }}
      </div>
      <div class="project-header-meta">
        <span v-if="selectedSource.repo" class="project-meta-item">
          <i class="fas fa-code-branch"></i>
          {{ selectedSource.repo }}
        </span>
        <span v-if="selectedSource.branch" class="project-meta-item">
          <i class="fas fa-tag"></i>
          {{ selectedSource.branch }}
        </span>
        <span
          class="project-meta-item"
          :class="'status-' + (selectedSource.status || 'unknown')"
        >
          <i class="fas fa-circle" style="font-size: 0.5em; vertical-align: middle;"></i>
          {{ selectedSource.status || 'unknown' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  status: string
  clone_path: string | null
  [key: string]: unknown
}

defineProps<{
  analyzing: boolean
  scanRunnerRunning: boolean
  rootPath: string
  selectedSource: CodeSource | null
  loadingApiEndpoints: boolean
  analyzingCodeSmells: boolean
  exportingReport: boolean
  clearingCache: boolean
}>()

const emit = defineEmits<{
  'index-codebase': []
  'stop': []
  'run-full-analysis': []
  'test-declarations': []
  'test-duplicates': []
  'test-hardcodes': []
  'test-npu': []
  'test-data-state': []
  'reset-state': []
  'test-all-endpoints': []
  'get-api-coverage': []
  'run-code-smells': []
  'get-health-score': []
  'export-report': []
  'clear-cache': []
}>()
</script>

<style scoped>
.analytics-header {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  margin-bottom: var(--spacing-6);
  box-shadow: var(--shadow-lg);
}

.header-content h2 {
  margin: 0 0 16px 0;
  color: var(--text-on-primary);
  font-size: 1.5em;
  font-weight: var(--font-semibold);
}

.header-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.btn-back {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-md);
  transition: color var(--duration-200), background var(--duration-200);
}

.btn-back:hover {
  color: var(--color-info);
  background: var(--bg-tertiary);
}

.btn-primary,
.btn-secondary,
.btn-debug {
  padding: 10px 20px;
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: var(--transition-all);
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background: var(--chart-green);
  color: var(--text-on-success);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-success-dark);
  transform: translateY(-1px);
}

.btn-secondary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  transform: translateY(-1px);
}

.btn-primary:disabled,
.btn-secondary:disabled {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: not-allowed;
  transform: none;
}

.btn-cancel {
  background: var(--color-error-hover);
  color: var(--text-on-error);
  padding: 10px 20px;
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: var(--transition-all);
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-cancel:hover {
  background: var(--color-error-dark);
  transform: translateY(-1px);
}

.debug-controls {
  width: 100%;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.btn-debug {
  font-size: 0.85em;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-debug:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

/* Project Header Card (#1713) */
.project-header-card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4) var(--spacing-5);
  margin-bottom: var(--spacing-4);
  border-left: 4px solid var(--accent-primary, #3b82f6);
  box-shadow: var(--shadow-sm);
}

.project-header-name {
  font-size: 1.15em;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.project-header-meta {
  display: flex;
  gap: var(--spacing-4);
  margin-top: var(--spacing-2);
  flex-wrap: wrap;
}

.project-meta-item {
  font-size: var(--text-sm);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.project-meta-item.status-ready {
  color: var(--color-success, #22c55e);
}

.project-meta-item.status-syncing {
  color: var(--color-warning, #f59e0b);
}

.project-meta-item.status-error {
  color: var(--color-error, #ef4444);
}
</style>
