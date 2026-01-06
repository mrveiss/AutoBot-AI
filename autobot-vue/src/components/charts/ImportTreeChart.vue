<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ImportTreeChart.vue - Interactive tree view of file import relationships
-->
<template>
  <div class="import-tree-chart" :class="{ 'chart-loading': loading }">
    <div v-if="title" class="chart-header">
      <h3 class="chart-title">{{ title }}</h3>
      <span v-if="subtitle" class="chart-subtitle">{{ subtitle }}</span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="chart-loading-overlay">
      <div class="loading-spinner"></div>
      <span>Loading import tree...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="chart-error">
      <span class="error-icon">!</span>
      <span>{{ error }}</span>
    </div>

    <!-- No data state -->
    <div v-else-if="!data || data.length === 0" class="chart-no-data">
      <span>No import data available</span>
    </div>

    <!-- Tree visualization -->
    <div v-else class="tree-container" :style="{ height: containerHeight }">
      <!-- Search/Filter -->
      <div class="tree-controls">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search files..."
          class="tree-search"
        />
        <div class="tree-stats">
          <span>{{ filteredData.length }} files</span>
          <span>{{ totalImports }} imports</span>
        </div>
      </div>

      <!-- Tree nodes -->
      <div class="tree-scroll">
        <div
          v-for="file in filteredData"
          :key="file.path"
          class="tree-node"
          :class="{ expanded: expandedNodes.has(file.path) }"
        >
          <div
            class="node-header"
            @click="toggleNode(file.path)"
          >
            <span class="expand-icon">
              {{ (file.imports?.length ?? 0) > 0 || (file.imported_by?.length ?? 0) > 0 ? (expandedNodes.has(file.path) ? '▼' : '▶') : '•' }}
            </span>
            <span class="file-icon">{{ getFileIcon(file.path) }}</span>
            <span class="file-name" :title="file.path">{{ getFileName(file.path) }}</span>
            <span class="import-counts">
              <span v-if="file.imports?.length" class="imports-out" :title="`Imports ${file.imports.length} modules`">
                ↑{{ file.imports.length }}
              </span>
              <span v-if="file.imported_by?.length" class="imports-in" :title="`Imported by ${file.imported_by.length} files`">
                ↓{{ file.imported_by.length }}
              </span>
            </span>
          </div>

          <!-- Expanded content -->
          <div v-if="expandedNodes.has(file.path)" class="node-children">
            <!-- Imports (what this file imports) -->
            <div v-if="file.imports?.length" class="import-section">
              <div class="section-header">
                <span class="section-icon">↑</span>
                <span>Imports ({{ file.imports.length }})</span>
              </div>
              <div class="import-list">
                <div
                  v-for="(imp, idx) in normalizeImports(file.imports)"
                  :key="imp.module || idx"
                  class="import-item"
                  :class="{ external: imp.is_external, internal: !imp.is_external }"
                  @click="navigateToFile(imp.file)"
                >
                  <span class="import-icon">{{ imp.is_external ? '📦' : '📄' }}</span>
                  <span class="import-module">{{ imp.module }}</span>
                  <span v-if="imp.file && !imp.is_external" class="import-file">→ {{ getFileName(imp.file) }}</span>
                </div>
              </div>
            </div>

            <!-- Imported By (what files import this file) -->
            <div v-if="file.imported_by?.length" class="import-section">
              <div class="section-header">
                <span class="section-icon">↓</span>
                <span>Imported By ({{ file.imported_by.length }})</span>
              </div>
              <div class="import-list">
                <div
                  v-for="imp in file.imported_by"
                  :key="imp.file"
                  class="import-item internal"
                  @click="navigateToFile(imp.file)"
                >
                  <span class="import-icon">📄</span>
                  <span class="import-file">{{ getFileName(imp.file) }}</span>
                  <span class="import-via">via {{ imp.module }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface ImportInfo {
  module: string
  file?: string
  is_external?: boolean
}

interface ImportedByInfo {
  file: string
  module: string
}

// Support flexible data format - can be either FileImportData or ImportTreeNode
interface FileImportData {
  path: string
  name?: string
  imports?: ImportInfo[] | string[]
  imported_by?: ImportedByInfo[]
  children?: FileImportData[]
}

interface Props {
  data: FileImportData[]
  title?: string
  subtitle?: string
  height?: number | string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'File Import Tree',
  subtitle: 'View file import relationships',
  height: 600,
  loading: false,
  error: ''
})

const emit = defineEmits<{
  (e: 'navigate', file: string): void
}>()

// State
const searchQuery = ref('')
const expandedNodes = ref<Set<string>>(new Set())

// Computed
const containerHeight = computed(() => {
  if (typeof props.height === 'number') {
    return `${props.height}px`
  }
  return props.height
})

const filteredData = computed(() => {
  if (!searchQuery.value) {
    // Sort by import count (most imported first)
    return [...props.data].sort((a, b) => {
      const aCount = (a.imports?.length || 0) + (a.imported_by?.length || 0)
      const bCount = (b.imports?.length || 0) + (b.imported_by?.length || 0)
      return bCount - aCount
    })
  }

  const query = searchQuery.value.toLowerCase()
  return props.data.filter(file =>
    file.path.toLowerCase().includes(query) ||
    file.imports?.some((imp: ImportInfo | string) => {
      const module = typeof imp === 'string' ? imp : imp.module
      return module.toLowerCase().includes(query)
    }) ||
    file.imported_by?.some(imp => imp.file.toLowerCase().includes(query))
  )
})

const totalImports = computed(() => {
  return props.data.reduce((sum, file) => sum + (file.imports?.length || 0), 0)
})

// Methods

// Normalize imports array to handle both string[] and ImportInfo[] formats
function normalizeImports(imports: ImportInfo[] | string[] | undefined): ImportInfo[] {
  if (!imports) return []
  return imports.map((imp: ImportInfo | string) => {
    if (typeof imp === 'string') {
      return {
        module: imp,
        is_external: imp.startsWith('@') || !imp.startsWith('.'),
        file: undefined
      }
    }
    return imp
  })
}

function toggleNode(path: string) {
  if (expandedNodes.value.has(path)) {
    expandedNodes.value.delete(path)
  } else {
    expandedNodes.value.add(path)
  }
  // Force reactivity
  expandedNodes.value = new Set(expandedNodes.value)
}

function getFileName(path: string): string {
  if (!path) return ''
  const parts = path.split('/')
  return parts[parts.length - 1]
}

function getFileIcon(path: string): string {
  if (path.endsWith('.py')) return '🐍'
  if (path.endsWith('.ts') || path.endsWith('.tsx')) return '📘'
  if (path.endsWith('.js') || path.endsWith('.jsx')) return '📜'
  if (path.endsWith('.vue')) return '💚'
  if (path.endsWith('.json')) return '📋'
  if (path.endsWith('.md')) return '📝'
  return '📄'
}

function navigateToFile(file?: string) {
  if (file) {
    emit('navigate', file)
  }
}

// Watch for data changes and auto-expand highly connected files
watch(() => props.data, (newData) => {
  if (newData && newData.length > 0) {
    // Auto-expand top 3 most connected files
    const sorted = [...newData].sort((a, b) => {
      const aCount = (a.imports?.length || 0) + (a.imported_by?.length || 0)
      const bCount = (b.imports?.length || 0) + (b.imported_by?.length || 0)
      return bCount - aCount
    })

    sorted.slice(0, 3).forEach(file => {
      if (file.imports?.length || file.imported_by?.length) {
        expandedNodes.value.add(file.path)
      }
    })
  }
}, { immediate: true })
</script>

<style scoped>
.import-tree-chart {
  background: var(--color-bg-secondary, #1e293b);
  border-radius: 12px;
  padding: 20px;
  position: relative;
}

.chart-header {
  margin-bottom: 16px;
}

.chart-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary, #e2e8f0);
  margin: 0 0 4px 0;
}

.chart-subtitle {
  font-size: 12px;
  color: var(--color-text-secondary, #94a3b8);
}

.chart-loading-overlay,
.chart-error,
.chart-no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--color-text-secondary, #94a3b8);
  gap: 12px;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border, #475569);
  border-top-color: var(--color-primary, #3b82f6);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  border-radius: 50%;
  font-size: 20px;
  font-weight: bold;
}

.tree-container {
  display: flex;
  flex-direction: column;
}

.tree-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border, #334155);
}

.tree-search {
  flex: 1;
  padding: 10px 14px;
  background: var(--color-bg-tertiary, #0f172a);
  border: 1px solid var(--color-border, #334155);
  border-radius: 8px;
  color: var(--color-text-primary, #e2e8f0);
  font-size: 14px;
}

.tree-search:focus {
  outline: none;
  border-color: var(--color-primary, #3b82f6);
}

.tree-search::placeholder {
  color: var(--color-text-tertiary, #64748b);
}

.tree-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--color-text-secondary, #94a3b8);
}

.tree-stats span {
  padding: 4px 10px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 4px;
}

.tree-scroll {
  overflow-y: auto;
  flex: 1;
  padding-right: 8px;
}

.tree-node {
  margin-bottom: 4px;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.node-header:hover {
  background: rgba(59, 130, 246, 0.1);
}

.tree-node.expanded > .node-header {
  background: rgba(59, 130, 246, 0.15);
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.expand-icon {
  width: 16px;
  font-size: 10px;
  color: var(--color-text-tertiary, #64748b);
}

.file-icon {
  font-size: 16px;
}

.file-name {
  flex: 1;
  font-size: 14px;
  color: var(--color-text-primary, #e2e8f0);
  font-family: 'Fira Code', 'Monaco', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.import-counts {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.imports-out {
  color: #10b981;
  padding: 2px 6px;
  background: rgba(16, 185, 129, 0.15);
  border-radius: 4px;
}

.imports-in {
  color: #8b5cf6;
  padding: 2px 6px;
  background: rgba(139, 92, 246, 0.15);
  border-radius: 4px;
}

.node-children {
  background: var(--color-bg-tertiary, #0f172a);
  border: 1px solid var(--color-border, #334155);
  border-top: none;
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
  padding: 12px;
}

.import-section {
  margin-bottom: 12px;
}

.import-section:last-child {
  margin-bottom: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary, #94a3b8);
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--color-border, #334155);
}

.section-icon {
  font-size: 14px;
}

.import-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 8px;
}

.import-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.import-item:hover {
  background: rgba(59, 130, 246, 0.1);
}

.import-item.external {
  opacity: 0.7;
}

.import-item.internal .import-module,
.import-item.internal .import-file {
  color: #10b981;
}

.import-icon {
  font-size: 14px;
}

.import-module {
  font-family: 'Fira Code', 'Monaco', monospace;
  color: var(--color-text-primary, #e2e8f0);
}

.import-file {
  font-size: 12px;
  color: var(--color-text-secondary, #94a3b8);
}

.import-via {
  font-size: 11px;
  color: var(--color-text-tertiary, #64748b);
  font-style: italic;
}
</style>
