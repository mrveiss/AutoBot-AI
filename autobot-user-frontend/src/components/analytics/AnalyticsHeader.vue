<template>
  <div class="analytics-header">
    <div class="header-content">
      <h2><i class="fas fa-code"></i> Real-time Codebase Analytics</h2>
      <div class="header-controls">
        <input
          :value="rootPath"
          @input="$emit('update:rootPath', ($event.target as HTMLInputElement).value)"
          placeholder="/path/to/analyze"
          class="path-input"
          @keyup.enter="$emit('run-full-analysis')"
        />
        <button @click="$emit('index-codebase')" :disabled="analyzing" class="btn-primary">
          <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-database'"></i>
          {{ analyzing ? 'Indexing...' : 'Index Codebase' }}
        </button>
        <button v-if="analyzing && currentJobId" @click="$emit('cancel-indexing')" class="btn-cancel">
          <i class="fas fa-stop-circle"></i>
          Cancel
        </button>
        <button @click="$emit('run-full-analysis')" :disabled="analyzing || !rootPath" class="btn-secondary">
          <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-chart-bar'"></i>
          {{ analyzing ? 'Analyzing...' : 'Analyze All' }}
        </button>

        <!-- Debug Controls -->
        <div class="debug-controls">
          <button @click="$emit('test-declarations')" class="btn-debug btn-declarations">Test Declarations</button>
          <button @click="$emit('test-duplicates')" class="btn-debug btn-duplicates">Test Duplicates</button>
          <button @click="$emit('test-hardcodes')" class="btn-debug btn-hardcodes">Test Hardcodes</button>
          <button @click="$emit('test-npu')" class="btn-debug btn-npu">Test NPU</button>
          <button @click="$emit('test-state')" class="btn-debug btn-state">Debug State</button>
          <button @click="$emit('reset-state')" class="btn-debug btn-reset">Reset State</button>
          <button @click="$emit('test-all-endpoints')" class="btn-debug btn-endpoints">Test All APIs</button>
          <!-- Code Intelligence -->
          <button @click="$emit('run-code-smell-analysis')" :disabled="analyzingCodeSmells" class="btn-debug btn-smells">
            <i :class="analyzingCodeSmells ? 'fas fa-spinner fa-spin' : 'fas fa-bug'"></i>
            {{ analyzingCodeSmells ? 'Scanning...' : 'Code Smells' }}
          </button>
          <button @click="$emit('get-code-health-score')" :disabled="analyzingCodeSmells" class="btn-debug btn-health">
            <i class="fas fa-heartbeat"></i> Health Score
          </button>
          <button @click="$emit('export-report')" :disabled="exportingReport" class="btn-debug btn-export">
            <i :class="exportingReport ? 'fas fa-spinner fa-spin' : 'fas fa-file-export'"></i>
            {{ exportingReport ? 'Exporting...' : 'Export Report' }}
          </button>
          <button @click="$emit('clear-cache')" :disabled="clearingCache" class="btn-debug btn-cache">
            <i :class="clearingCache ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
            {{ clearingCache ? 'Clearing...' : 'Clear Cache' }}
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
 * Analytics Header Component
 *
 * Header with path input and control buttons for codebase analytics.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

interface Props {
  rootPath: string
  analyzing: boolean
  currentJobId: string | null
  analyzingCodeSmells: boolean
  exportingReport: boolean
  clearingCache: boolean
}

interface Emits {
  (e: 'update:rootPath', value: string): void
  (e: 'index-codebase'): void
  (e: 'cancel-indexing'): void
  (e: 'run-full-analysis'): void
  (e: 'test-declarations'): void
  (e: 'test-duplicates'): void
  (e: 'test-hardcodes'): void
  (e: 'test-npu'): void
  (e: 'test-state'): void
  (e: 'reset-state'): void
  (e: 'test-all-endpoints'): void
  (e: 'run-code-smell-analysis'): void
  (e: 'get-code-health-score'): void
  (e: 'export-report'): void
  (e: 'clear-cache'): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.analytics-header {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-6);
  box-shadow: var(--shadow-lg);
}

.header-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.header-content h2 {
  color: var(--color-info);
  margin: 0;
  font-size: var(--text-xl);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2-5);
  align-items: center;
}

.path-input {
  flex: 1;
  min-width: 300px;
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary-alpha);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
}

.path-input::placeholder {
  color: var(--text-muted);
}

.btn-primary,
.btn-secondary,
.btn-cancel {
  padding: var(--spacing-2-5) var(--spacing-5);
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-primary {
  background: var(--color-info);
  color: var(--bg-secondary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-info-dark);
}

.btn-secondary {
  background: var(--bg-tertiary-alpha);
  color: var(--text-on-primary);
  border: 1px solid var(--border-subtle);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-cancel {
  background: var(--color-error);
  color: var(--text-on-primary);
}

.btn-cancel:hover {
  background: var(--color-error-hover);
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.debug-controls {
  margin-top: var(--spacing-2-5);
  display: flex;
  gap: var(--spacing-2-5);
  flex-wrap: wrap;
  width: 100%;
}

.btn-debug {
  padding: var(--spacing-1-5) var(--spacing-2-5);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.btn-declarations { background: var(--color-success); }
.btn-duplicates { background: var(--color-warning); }
.btn-hardcodes { background: var(--color-error); }
.btn-npu { background: var(--chart-purple); }
.btn-state { background: var(--color-info); }
.btn-reset { background: var(--chart-orange); }
.btn-endpoints { background: var(--chart-cyan); }
.btn-smells { background: var(--chart-pink); }
.btn-health { background: var(--chart-indigo); }
.btn-export { background: var(--text-tertiary); }
.btn-cache { background: var(--chart-brown); }

.btn-debug:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
