<template>
  <div class="analytics-header">
    <div class="header-content">
      <h2><i class="fas fa-code"></i> Real-time Codebase Analytics</h2>
      <div class="header-controls">
        <!-- Source selector row -->
        <div class="source-selector-row">
          <!-- Project selector dropdown -->
          <div class="source-selector-wrapper">
            <select
              class="source-select"
              :value="selectedSource ? selectedSource.id : '__custom__'"
              @change="handleSourceChange"
              :title="selectedSource ? selectedSource.name : 'Custom path'"
            >
              <option value="__custom__">Custom path...</option>
              <option
                v-for="source in sources"
                :key="source.id"
                :value="source.id"
              >
                {{ source.name }}
                <template v-if="source.source_type === 'github'"> ({{ source.repo ?? '' }})</template>
                <template v-else> (local)</template>
              </option>
            </select>
            <i class="fas fa-chevron-down select-chevron"></i>
          </div>

          <!-- Manage Sources button -->
          <button class="btn-manage" @click="$emit('open-source-manager')" title="Manage code sources">
            <i class="fas fa-code-branch"></i>
            Manage Sources
          </button>
        </div>

        <!-- Path input (shown when custom path selected or no sources) -->
        <input
          v-if="!selectedSource"
          :value="rootPath"
          @input="$emit('update:rootPath', ($event.target as HTMLInputElement).value)"
          placeholder="/path/to/analyze"
          class="path-input"
          @keyup.enter="$emit('run-full-analysis')"
        />

        <!-- Selected source info bar -->
        <div v-if="selectedSource" class="selected-source-bar">
          <i :class="selectedSource.source_type === 'github' ? 'fab fa-github' : 'fas fa-folder'"></i>
          <span class="selected-source-name">{{ selectedSource.name }}</span>
          <span class="selected-source-path">
            {{ selectedSource.repo ?? selectedSource.clone_path ?? '' }}
          </span>
          <span class="selected-source-status" :class="`status--${selectedSource.status}`">
            {{ selectedSource.status }}
          </span>
          <button class="btn-clear-source" @click="$emit('clear-source')" title="Use custom path instead">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <button @click="$emit('index-codebase')" :disabled="analyzing" class="btn-primary">
          <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-database'"></i>
          {{ analyzing ? 'Indexing...' : 'Index Codebase' }}
        </button>
        <button v-if="analyzing && currentJobId" @click="$emit('cancel-indexing')" class="btn-cancel">
          <i class="fas fa-stop-circle"></i>
          Cancel
        </button>
        <button @click="$emit('run-full-analysis')" :disabled="analyzing || (!rootPath && !selectedSource)" class="btn-secondary">
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
 * Header with project source selector and control buttons for codebase analytics.
 * Issue #1133: Added source registry selector and Manage Sources button.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

// ---- Types ----------------------------------------------------------------

interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  credential_id: string | null
  clone_path: string | null
  last_synced: string | null
  status: 'configured' | 'syncing' | 'ready' | 'error'
  error_message: string | null
  owner_id: string | null
  access: 'private' | 'shared' | 'public'
  shared_with: string[]
  created_at: string
}

// ---- Props & Emits --------------------------------------------------------

interface Props {
  rootPath: string
  analyzing: boolean
  currentJobId: string | null
  analyzingCodeSmells: boolean
  exportingReport: boolean
  clearingCache: boolean
  sources: CodeSource[]
  selectedSource: CodeSource | null
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
  (e: 'select-source', source: CodeSource): void
  (e: 'clear-source'): void
  (e: 'open-source-manager'): void
}

const props = withDefaults(defineProps<Props>(), {
  sources: () => [],
  selectedSource: null
})

const emit = defineEmits<Emits>()

// ---- Handlers -------------------------------------------------------------

function handleSourceChange(event: Event) {
  const select = event.target as HTMLSelectElement
  const value = select.value
  if (value === '__custom__') {
    emit('clear-source')
    return
  }
  const found = props.sources.find(s => s.id === value)
  if (found) {
    emit('select-source', found)
  }
}
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
/** Issue #1133: Source selector additions */

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

/* Source Selector Row */
.source-selector-row {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
  width: 100%;
}

.source-selector-wrapper {
  position: relative;
  flex: 2;
}

.source-select {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-8) var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary-alpha);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  appearance: none;
  cursor: pointer;
  transition: border-color var(--duration-200);
}

.source-select:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
}

.select-chevron {
  position: absolute;
  right: var(--spacing-3);
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.btn-manage {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary-alpha);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  white-space: nowrap;
  transition: all var(--duration-200);
}

.btn-manage:hover {
  background: var(--bg-hover);
  border-color: var(--color-info);
  color: var(--color-info);
}

/* Selected source info bar */
.selected-source-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: var(--radius-lg);
  padding: var(--spacing-2) var(--spacing-4);
  width: 100%;
  min-width: 0;
}

.selected-source-bar > i {
  color: var(--color-info);
  flex-shrink: 0;
}

.selected-source-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  color: var(--text-primary);
  white-space: nowrap;
}

.selected-source-path {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.selected-source-status {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: 0.1rem var(--spacing-2);
  border-radius: var(--radius-full);
  text-transform: capitalize;
  flex-shrink: 0;
}

.status--configured {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.status--syncing {
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
}

.status--ready {
  background: rgba(16, 185, 129, 0.15);
  color: var(--color-success);
}

.status--error {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
}

.btn-clear-source {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--spacing-1);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  flex-shrink: 0;
  font-size: var(--text-xs);
  transition: color var(--duration-200);
}

.btn-clear-source:hover {
  color: var(--color-error);
}

/* Path Input */
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

/* Action Buttons */
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

/* Debug Controls */
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
