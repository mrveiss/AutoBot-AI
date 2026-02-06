<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ImportTreeChart.vue - Interactive tree view of file import relationships
  Issue #707: Added Cytoscape.js network view as default
-->
<template>
  <div class="import-tree-chart" :class="{ 'chart-loading': loading, 'fullscreen': isFullscreen }">
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

    <!-- Main visualization -->
    <div v-else class="tree-container" :style="{ height: containerHeight }">
      <!-- Search/Filter and View Toggle -->
      <div class="tree-controls">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search files..."
          class="tree-search"
          @input="handleSearch"
        />
        <div class="tree-stats">
          <span>{{ filteredData.length }} files</span>
          <span>{{ totalImports }} imports</span>
        </div>
        <div class="view-toggle">
          <button
            :class="{ active: viewMode === 'network' }"
            @click="viewMode = 'network'"
            title="Network View"
          >
            <i class="fas fa-project-diagram"></i>
          </button>
          <button
            :class="{ active: viewMode === 'tree' }"
            @click="viewMode = 'tree'"
            title="Tree View"
          >
            <i class="fas fa-list-tree"></i>
          </button>
        </div>
      </div>

      <!-- Network view (Cytoscape) - DEFAULT -->
      <div v-show="viewMode === 'network'" class="network-view">
        <div class="network-legend">
          <span class="legend-item importer"><span class="dot"></span> Imports Others</span>
          <span class="legend-item imported"><span class="dot"></span> Imported By Others</span>
          <span class="legend-item hub"><span class="dot"></span> Hub (Both)</span>
          <span class="legend-item external"><span class="dot"></span> External Package</span>
        </div>
        <div ref="cytoscapeContainer" class="cytoscape-container"></div>
        <div class="network-controls">
          <button @click="zoomIn" title="Zoom in">
            <i class="fas fa-plus"></i>
          </button>
          <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
          <button @click="zoomOut" title="Zoom out">
            <i class="fas fa-minus"></i>
          </button>
          <button @click="fitGraph" title="Fit to view">
            <i class="fas fa-expand"></i>
          </button>
          <button @click="toggleLayout" title="Toggle layout">
            <i class="fas fa-th"></i>
          </button>
          <span class="control-separator">|</span>
          <button @click="toggleFullscreen" :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'">
            <i :class="isFullscreen ? 'fas fa-compress' : 'fas fa-expand-arrows-alt'"></i>
          </button>
        </div>

        <!-- Node Detail Panel -->
        <div v-if="selectedNode" class="node-detail-panel">
          <div class="detail-header">
            <span class="detail-icon">{{ getFileIcon(selectedNode.path) }}</span>
            <span class="detail-name">{{ selectedNode.shortName }}</span>
            <button class="close-btn" @click="selectedNode = null" title="Close">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="detail-content">
            <div class="detail-row">
              <span class="detail-label">Full Path:</span>
              <span class="detail-value path-value">{{ selectedNode.path }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Type:</span>
              <span class="detail-value" :class="'node-type-' + selectedNode.nodeType">
                {{ getNodeTypeLabel(selectedNode.nodeType) }}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Imports:</span>
              <span class="detail-value">{{ selectedNode.importsCount }} module{{ selectedNode.importsCount !== 1 ? 's' : '' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Imported By:</span>
              <span class="detail-value">{{ selectedNode.importedByCount }} file{{ selectedNode.importedByCount !== 1 ? 's' : '' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Extension:</span>
              <span class="detail-value">{{ getFileExtension(selectedNode.path) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Directory:</span>
              <span class="detail-value path-value">{{ getFileDirectory(selectedNode.path) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Tree view -->
      <div v-if="viewMode === 'tree'" class="tree-view">
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import cytoscape, { type Core, type NodeSingular } from 'cytoscape'
// @ts-expect-error - cytoscape-fcose has no type declarations
import fcose from 'cytoscape-fcose'

// Register fcose layout
cytoscape.use(fcose)

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
  (e: 'select', file: string): void
}>()

// State
const searchQuery = ref('')
const expandedNodes = ref<Set<string>>(new Set())
const viewMode = ref<'network' | 'tree'>('network') // Default to network view
const zoomLevel = ref(1)
const layoutMode = ref<'force' | 'grid'>('force')
const selectedNode = ref<{
  path: string
  shortName: string
  importsCount: number
  importedByCount: number
  nodeType: 'hub' | 'importer' | 'imported' | 'isolated'
} | null>(null)
const isFullscreen = ref(false)

// Cytoscape instance
const cytoscapeContainer = ref<HTMLElement | null>(null)
let cy: Core | null = null

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

function getFileExtension(path: string): string {
  if (!path) return 'Unknown'
  const lastDot = path.lastIndexOf('.')
  if (lastDot === -1) return 'No extension'
  return path.substring(lastDot)
}

function getFileDirectory(path: string): string {
  if (!path) return ''
  const lastSlash = path.lastIndexOf('/')
  if (lastSlash === -1) return '.'
  return path.substring(0, lastSlash) || '/'
}

function getNodeTypeLabel(nodeType: string): string {
  switch (nodeType) {
    case 'hub': return 'Hub (Imports & Imported)'
    case 'importer': return 'Importer (Imports Others)'
    case 'imported': return 'Library (Imported by Others)'
    case 'isolated': return 'Isolated (No Connections)'
    default: return nodeType
  }
}

function determineNodeType(importsCount: number, importedByCount: number): 'hub' | 'importer' | 'imported' | 'isolated' {
  if (importsCount > 0 && importedByCount > 0) return 'hub'
  if (importsCount > importedByCount) return 'importer'
  if (importedByCount > 0) return 'imported'
  return 'isolated'
}

function navigateToFile(file?: string) {
  if (file) {
    emit('navigate', file)
  }
}

function handleSearch() {
  updateCytoscapeElements()
}

// ============================================================================
// Cytoscape Methods
// ============================================================================

function initCytoscape() {
  if (!cytoscapeContainer.value) return

  cy = cytoscape({
    container: cytoscapeContainer.value,
    style: getCytoscapeStyles(),
    elements: [],
    minZoom: 0.1,
    maxZoom: 3,
    wheelSensitivity: 0.3,
    boxSelectionEnabled: false
  })

  // Event handlers
  cy.on('tap', 'node', (evt) => {
    const node = evt.target as NodeSingular
    const filePath = node.id()
    const nodeData = node.data()

    // Populate selectedNode for detail panel
    selectedNode.value = {
      path: filePath,
      shortName: nodeData.label || getFileName(filePath),
      importsCount: nodeData.importsCount || 0,
      importedByCount: nodeData.importedBy || 0,
      nodeType: determineNodeType(nodeData.importsCount || 0, nodeData.importedBy || 0)
    }

    emit('select', filePath)
    highlightConnected(node)
  })

  cy.on('tap', (evt) => {
    if (evt.target === cy) {
      selectedNode.value = null
      clearHighlight()
    }
  })

  cy.on('mouseover', 'node', (evt) => {
    const node = evt.target as NodeSingular
    highlightConnected(node)
  })

  cy.on('mouseout', 'node', () => {
    clearHighlight()
  })

  cy.on('zoom', () => {
    zoomLevel.value = cy?.zoom() || 1
  })
}

/**
 * Get CSS variable value from the document
 * Issue #704: Use design tokens for theming
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function getCytoscapeStyles(): cytoscape.StylesheetStyle[] {
  // Read design tokens for theming (Issue #704)
  const textPrimary = getCssVar('--text-primary', '#e2e8f0')
  const bgSecondary = getCssVar('--bg-secondary', '#1e293b')
  const colorWarningLight = getCssVar('--color-warning-light', '#fbbf24')

  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'label': 'data(label)',
        'width': 'data(size)',
        'height': 'data(size)',
        'font-size': '10px',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 6,
        'color': textPrimary,
        'text-outline-color': bgSecondary,
        'text-outline-width': 2,
        'border-width': 2,
        'border-color': 'data(borderColor)',
        'text-max-width': '80px',
        'text-wrap': 'ellipsis'
      }
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 3,
        'border-color': getCssVar('--text-primary', '#ffffff')
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 3,
        'border-color': colorWarningLight
      }
    },
    {
      selector: 'node.dimmed',
      style: {
        'opacity': 0.15
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 'data(width)',
        'line-color': 'data(color)',
        'target-arrow-color': 'data(color)',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'opacity': 0.5
      }
    },
    {
      selector: 'edge.highlighted',
      style: {
        'opacity': 1,
        'width': 3,
        'line-color': colorWarningLight,
        'target-arrow-color': colorWarningLight
      }
    },
    {
      selector: 'edge.dimmed',
      style: {
        'opacity': 0.05
      }
    }
  ]
}

function updateCytoscapeElements() {
  if (!cy) return

  const elements: cytoscape.ElementDefinition[] = []
  const nodeIds = new Set<string>()

  // Build map of imports and importers for quick lookup
  const importerCount = new Map<string, number>() // How many modules this file imports
  const importedByCount = new Map<string, number>() // How many files import this module

  for (const file of filteredData.value) {
    const imports = normalizeImports(file.imports)
    importerCount.set(file.path, imports.length)

    // Count how many times each module is imported
    for (const imp of imports) {
      if (imp.file) {
        importedByCount.set(imp.file, (importedByCount.get(imp.file) || 0) + 1)
      }
    }

    if (file.imported_by) {
      importedByCount.set(file.path, (importedByCount.get(file.path) || 0) + file.imported_by.length)
    }
  }

  // Add nodes for files
  for (const file of filteredData.value) {
    const imports = normalizeImports(file.imports)
    const importsCount = imports.length
    const importedBy = importedByCount.get(file.path) || 0

    const totalConnections = importsCount + importedBy
    const size = 25 + Math.min(totalConnections * 2, 35)

    // Color based on import pattern - Using design tokens (Issue #704)
    let color: string
    let borderColor: string
    if (importsCount > 0 && importedBy > 0) {
      // Hub - both imports and is imported
      color = getCssVar('--color-warning', '#f59e0b')
      borderColor = getCssVar('--color-warning-light', '#fbbf24')
    } else if (importsCount > importedBy) {
      // Primarily imports others
      color = getCssVar('--color-success', '#10b981')
      borderColor = getCssVar('--color-success-light', '#34d399')
    } else if (importedBy > 0) {
      // Primarily imported by others
      color = getCssVar('--chart-purple', '#8b5cf6')
      borderColor = getCssVar('--chart-purple-light', '#a78bfa')
    } else {
      // Isolated
      color = getCssVar('--text-tertiary', '#6b7280')
      borderColor = getCssVar('--text-secondary', '#9ca3af')
    }

    const shortName = getFileName(file.path)
    nodeIds.add(file.path)

    elements.push({
      data: {
        id: file.path,
        label: shortName,
        color,
        borderColor,
        size,
        importsCount,
        importedBy
      }
    })
  }

  // Add edges for imports
  for (const file of filteredData.value) {
    const imports = normalizeImports(file.imports)

    for (const imp of imports) {
      // Only add internal imports (those with resolved file paths)
      if (imp.file && !imp.is_external && nodeIds.has(imp.file)) {
        elements.push({
          data: {
            id: `${file.path}->${imp.file}`,
            source: file.path,
            target: imp.file,
            color: getCssVar('--text-tertiary', '#64748b'),
            width: 1.5
          }
        })
      }
    }
  }

  // Update graph
  cy.elements().remove()
  cy.add(elements)

  // Run layout
  runLayout()
}

function runLayout() {
  if (!cy || cy.nodes().length === 0) return

  const layoutOptions = layoutMode.value === 'force'
    ? {
        name: 'fcose',
        animate: true,
        animationDuration: 400,
        fit: true,
        padding: 30,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 120,
        nodeRepulsion: 6000,
        gravity: 0.3
      }
    : {
        name: 'grid',
        animate: true,
        animationDuration: 300,
        fit: true,
        padding: 30,
        avoidOverlap: true
      }

  cy.layout(layoutOptions as cytoscape.LayoutOptions).run()
}

function highlightConnected(node: NodeSingular) {
  if (!cy) return
  const neighborhood = node.neighborhood().add(node)
  cy.elements().addClass('dimmed')
  neighborhood.removeClass('dimmed').addClass('highlighted')
}

function clearHighlight() {
  if (!cy) return
  cy.elements().removeClass('dimmed').removeClass('highlighted')
}

function zoomIn() {
  if (!cy) return
  cy.zoom(cy.zoom() * 1.25)
  cy.center()
}

function zoomOut() {
  if (!cy) return
  cy.zoom(cy.zoom() * 0.8)
  cy.center()
}

function fitGraph() {
  if (!cy) return
  cy.fit(undefined, 30)
  zoomLevel.value = cy.zoom()
}

function toggleLayout() {
  layoutMode.value = layoutMode.value === 'force' ? 'grid' : 'force'
  runLayout()
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  // Re-fit the graph after transition
  nextTick(() => {
    setTimeout(() => {
      if (cy) {
        cy.resize()
        fitGraph()
      }
    }, 100)
  })
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(async () => {
  await nextTick()
  if (cytoscapeContainer.value && props.data?.length) {
    initCytoscape()
    updateCytoscapeElements()
  }
})

onUnmounted(() => {
  if (cy) {
    cy.destroy()
    cy = null
  }
})

// Watch for data changes and auto-expand highly connected files
watch(() => props.data, async (newData) => {
  if (newData && newData.length > 0) {
    // Auto-expand top 3 most connected files (for tree view)
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

    // Update Cytoscape if initialized
    await nextTick()
    if (!cy && cytoscapeContainer.value) {
      initCytoscape()
    }
    updateCytoscapeElements()
  }
}, { immediate: true })

// Watch for view mode changes
watch(viewMode, async (newMode) => {
  if (newMode === 'network') {
    await nextTick()
    if (!cy && cytoscapeContainer.value) {
      initCytoscape()
      updateCytoscapeElements()
    }
  }
})
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */
.import-tree-chart {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  position: relative;
}

.chart-header {
  margin-bottom: var(--spacing-md);
}

.chart-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-1) 0;
}

.chart-subtitle {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.chart-loading-overlay,
.chart-error,
.chart-no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-secondary);
  gap: var(--spacing-sm);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-default);
  border-top-color: var(--color-primary);
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
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: 50%;
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
}

.tree-container {
  display: flex;
  flex-direction: column;
}

.tree-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-default);
}

.tree-search {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.tree-search:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.tree-search::placeholder {
  color: var(--text-tertiary);
}

.tree-stats {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.tree-stats span {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.tree-scroll {
  overflow-y: auto;
  flex: 1;
  padding-right: var(--spacing-2);
}

.tree-node {
  margin-bottom: var(--spacing-1);
}

.node-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-200) ease;
}

.node-header:hover {
  background: var(--color-primary-bg);
}

.tree-node.expanded > .node-header {
  background: var(--color-primary-bg-hover);
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.expand-icon {
  width: 16px;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.file-icon {
  font-size: var(--text-base);
}

.file-name {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.import-counts {
  display: flex;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
}

.imports-out {
  color: var(--color-success);
  padding: var(--spacing-px) var(--spacing-1);
  background: var(--color-success-bg);
  border-radius: var(--radius-sm);
}

.imports-in {
  color: var(--chart-purple);
  padding: var(--spacing-px) var(--spacing-1);
  background: var(--chart-purple-bg);
  border-radius: var(--radius-sm);
}

.node-children {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-top: none;
  border-bottom-left-radius: var(--radius-lg);
  border-bottom-right-radius: var(--radius-lg);
  padding: var(--spacing-3);
}

.import-section {
  margin-bottom: var(--spacing-3);
}

.import-section:last-child {
  margin-bottom: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
  padding-bottom: var(--spacing-1);
  border-bottom: 1px solid var(--border-default);
}

.section-icon {
  font-size: var(--text-sm);
}

.import-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding-left: var(--spacing-2);
}

.import-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-200) ease;
}

.import-item:hover {
  background: var(--color-primary-bg);
}

.import-item.external {
  opacity: 0.7;
}

.import-item.internal .import-module,
.import-item.internal .import-file {
  color: var(--color-success);
}

.import-icon {
  font-size: var(--text-sm);
}

.import-module {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.import-file {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.import-via {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-style: italic;
}

/* View Toggle */
.view-toggle {
  display: flex;
  gap: var(--spacing-1);
}

.view-toggle button {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200) ease;
}

.view-toggle button.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}

.view-toggle button:hover:not(.active) {
  background: var(--color-primary-bg);
}

/* Network View */
.network-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-height: 400px;
}

.network-legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.legend-item .dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.legend-item.importer .dot {
  background: var(--color-success);
  border: 2px solid var(--color-success-light);
}

.legend-item.imported .dot {
  background: var(--chart-purple);
  border: 2px solid var(--chart-purple-light);
}

.legend-item.hub .dot {
  background: var(--color-warning);
  border: 2px solid var(--color-warning-light);
}

.legend-item.external .dot {
  background: var(--text-tertiary);
  border: 2px solid var(--text-secondary);
}

.cytoscape-container {
  flex: 1;
  min-height: 350px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.network-controls {
  position: absolute;
  bottom: var(--spacing-3);
  right: var(--spacing-3);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  background: var(--bg-secondary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
}

.network-controls button {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--duration-200);
}

.network-controls button:hover {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}

.zoom-level {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  min-width: 36px;
  text-align: center;
}

.control-separator {
  color: var(--border-default);
  font-size: var(--text-sm);
}

/* Tree View */
.tree-view {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Node Detail Panel */
.node-detail-panel {
  position: absolute;
  top: var(--spacing-3);
  left: var(--spacing-3);
  width: 320px;
  max-width: calc(100% - 24px);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-10);
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.detail-icon {
  font-size: var(--text-lg);
}

.detail-name {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.close-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-200);
}

.close-btn:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.detail-content {
  padding: var(--spacing-3);
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-px);
  margin-bottom: var(--spacing-2);
}

.detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.detail-value.path-value {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  word-break: break-all;
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  margin-top: var(--spacing-px);
}

.node-type-hub {
  color: var(--color-warning);
}

.node-type-importer {
  color: var(--color-success);
}

.node-type-imported {
  color: var(--chart-purple);
}

.node-type-isolated {
  color: var(--text-tertiary);
}

/* Fullscreen mode */
.import-tree-chart.fullscreen {
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  z-index: var(--z-maximum) !important;
  border-radius: 0 !important;
  margin: 0 !important;
  padding: var(--spacing-md) !important;
}

.import-tree-chart.fullscreen .tree-container {
  height: calc(100vh - 100px) !important;
}

.import-tree-chart.fullscreen .network-view {
  min-height: calc(100vh - 200px);
}

.import-tree-chart.fullscreen .cytoscape-container {
  min-height: calc(100vh - 240px);
}
</style>
