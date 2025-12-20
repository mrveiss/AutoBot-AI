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
.analytics-header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
}

.header-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-content h2 {
  color: #00d4ff;
  margin: 0;
  font-size: 1.5rem;
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.path-input {
  flex: 1;
  min-width: 300px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  color: white;
  font-size: 14px;
}

.path-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}

.btn-primary,
.btn-secondary,
.btn-cancel {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-primary {
  background: #00d4ff;
  color: #1a1a2e;
}

.btn-primary:hover:not(:disabled) {
  background: #00b8e0;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.1);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.2);
}

.btn-cancel {
  background: #e74c3c;
  color: white;
}

.btn-cancel:hover {
  background: #c0392b;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.debug-controls {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  width: 100%;
}

.btn-debug {
  padding: 5px 10px;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.btn-declarations { background: #4CAF50; }
.btn-duplicates { background: #FF9800; }
.btn-hardcodes { background: #F44336; }
.btn-npu { background: #9C27B0; }
.btn-state { background: #2196F3; }
.btn-reset { background: #FF5722; }
.btn-endpoints { background: #00BCD4; }
.btn-smells { background: #E91E63; }
.btn-health { background: #673AB7; }
.btn-export { background: #607D8B; }
.btn-cache { background: #795548; }

.btn-debug:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
