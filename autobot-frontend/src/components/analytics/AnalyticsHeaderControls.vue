<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1579: Extracted from CodebaseAnalytics.vue — Header with action buttons -->
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
        <button @click="emit('run-full-analysis')" :disabled="analyzing || (!rootPath && !selectedSource)" class="btn-secondary">
          <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-chart-bar'"></i>
          {{ analyzing ? $t('analytics.codebase.buttons.analyzing') : $t('analytics.codebase.buttons.analyzeAll') }}
        </button>

        <!-- Enhanced Debug Controls -->
        <div class="debug-controls" style="margin-top: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
          <button @click="emit('test-declarations')" class="btn-debug btn-debug-success">{{ $t('analytics.codebase.buttons.testDeclarations') }}</button>
          <button @click="emit('test-duplicates')" class="btn-debug btn-debug-warning">{{ $t('analytics.codebase.buttons.testDuplicates') }}</button>
          <button @click="emit('test-hardcodes')" class="btn-debug btn-debug-error">{{ $t('analytics.codebase.buttons.testHardcodes') }}</button>
          <button @click="emit('test-npu')" class="btn-debug btn-debug-purple">{{ $t('analytics.codebase.buttons.testNpu') }}</button>
          <button @click="emit('test-data-state')" class="btn-debug btn-debug-info">{{ $t('analytics.codebase.buttons.debugState') }}</button>
          <button @click="emit('reset-state')" class="btn-debug btn-debug-orange">{{ $t('analytics.codebase.buttons.resetState') }}</button>
          <button @click="emit('test-all-endpoints')" class="btn-debug btn-debug-cyan">{{ $t('analytics.codebase.buttons.testAllApis') }}</button>
          <!-- Issue #527: API Endpoint Checker -->
          <button @click="emit('api-coverage')" :disabled="loadingApiEndpoints" class="btn-debug btn-debug-indigo">
            <i :class="loadingApiEndpoints ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
            {{ loadingApiEndpoints ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.buttons.apiCoverage') }}
          </button>
          <!-- Code Intelligence / Anti-Pattern Detection -->
          <button @click="emit('code-smells')" :disabled="analyzingCodeSmells" class="btn-debug btn-debug-pink">
            <i :class="analyzingCodeSmells ? 'fas fa-spinner fa-spin' : 'fas fa-bug'"></i>
            {{ analyzingCodeSmells ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.buttons.codeSmells') }}
          </button>
          <button @click="emit('health-score')" :disabled="analyzingCodeSmells" class="btn-debug btn-debug-violet">
            <i class="fas fa-heartbeat"></i> {{ $t('analytics.codebase.buttons.healthScore') }}
          </button>
          <button @click="emit('export-report')" :disabled="exportingReport" class="btn-debug btn-debug-secondary">
            <i :class="exportingReport ? 'fas fa-spinner fa-spin' : 'fas fa-file-export'"></i>
            {{ exportingReport ? $t('analytics.codebase.buttons.exporting') : $t('analytics.codebase.buttons.exportReport') }}
          </button>
          <button @click="emit('clear-cache')" :disabled="clearingCache" class="btn-debug btn-debug-brown">
            <i :class="clearingCache ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
            {{ clearingCache ? $t('analytics.codebase.buttons.clearing') : $t('analytics.codebase.buttons.clearCache') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Analytics Header Controls Component
 *
 * Header bar with primary actions (index, analyze, stop) and debug
 * buttons for the codebase analytics dashboard.
 *
 * Issue #1579: Extracted from CodebaseAnalytics.vue
 */

import type { CodeSource } from '@/types/analytics'

defineProps<{
  analyzing: boolean
  rootPath: string
  selectedSource: CodeSource | null
  scanRunnerRunning: boolean
  loadingApiEndpoints: boolean
  analyzingCodeSmells: boolean
  exportingReport: boolean
  clearingCache: boolean
}>()

const emit = defineEmits<{
  'index-codebase': []
  'run-full-analysis': []
  'stop': []
  'test-declarations': []
  'test-duplicates': []
  'test-hardcodes': []
  'test-npu': []
  'test-data-state': []
  'reset-state': []
  'test-all-endpoints': []
  'api-coverage': []
  'code-smells': []
  'health-score': []
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

.btn-primary, .btn-secondary, .btn-debug {
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

.btn-primary:disabled, .btn-secondary:disabled {
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
</style>
