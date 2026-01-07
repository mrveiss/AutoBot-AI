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

function getCytoscapeStyles(): cytoscape.StylesheetStyle[] {
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
        'color': '#e2e8f0',
        'text-outline-color': '#1e293b',
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
        'border-color': '#ffffff'
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 3,
        'border-color': '#fbbf24'
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
        'line-color': '#fbbf24',
        'target-arrow-color': '#fbbf24'
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

    // Color based on import pattern
    let color: string
    let borderColor: string
    if (importsCount > 0 && importedBy > 0) {
      // Hub - both imports and is imported
      color = '#f59e0b' // Amber
      borderColor = '#fbbf24'
    } else if (importsCount > importedBy) {
      // Primarily imports others
      color = '#10b981' // Green
      borderColor = '#34d399'
    } else if (importedBy > 0) {
      // Primarily imported by others
      color = '#8b5cf6' // Purple
      borderColor = '#a78bfa'
    } else {
      // Isolated
      color = '#6b7280' // Gray
      borderColor = '#9ca3af'
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
            color: '#64748b',
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

/* View Toggle */
.view-toggle {
  display: flex;
  gap: 4px;
}

.view-toggle button {
  padding: 8px 12px;
  background: var(--color-bg-tertiary, #0f172a);
  border: 1px solid var(--color-border, #334155);
  border-radius: 6px;
  color: var(--color-text-secondary, #94a3b8);
  cursor: pointer;
  transition: all 0.2s ease;
}

.view-toggle button.active {
  background: var(--color-primary, #3b82f6);
  color: white;
  border-color: var(--color-primary, #3b82f6);
}

.view-toggle button:hover:not(.active) {
  background: rgba(59, 130, 246, 0.2);
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
  gap: 16px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 6px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary, #94a3b8);
}

.legend-item .dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.legend-item.importer .dot {
  background: #10b981;
  border: 2px solid #34d399;
}

.legend-item.imported .dot {
  background: #8b5cf6;
  border: 2px solid #a78bfa;
}

.legend-item.hub .dot {
  background: #f59e0b;
  border: 2px solid #fbbf24;
}

.legend-item.external .dot {
  background: #6b7280;
  border: 2px solid #9ca3af;
}

.cytoscape-container {
  flex: 1;
  min-height: 350px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 8px;
  overflow: hidden;
}

.network-controls {
  position: absolute;
  bottom: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--color-bg-secondary, #1e293b);
  padding: 6px 10px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.network-controls button {
  width: 28px;
  height: 28px;
  border: 1px solid var(--color-border, #334155);
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary, #94a3b8);
  transition: all 0.2s;
}

.network-controls button:hover {
  background: var(--color-primary, #3b82f6);
  color: white;
  border-color: var(--color-primary, #3b82f6);
}

.zoom-level {
  font-size: 11px;
  color: var(--color-text-tertiary, #64748b);
  min-width: 36px;
  text-align: center;
}

.control-separator {
  color: var(--color-border, #334155);
  font-size: 14px;
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
  top: 12px;
  left: 12px;
  width: 320px;
  max-width: calc(100% - 24px);
  background: var(--color-bg-secondary, #1e293b);
  border: 1px solid var(--color-border, #334155);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  z-index: 10;
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  background: var(--color-bg-tertiary, #0f172a);
  border-bottom: 1px solid var(--color-border, #334155);
}

.detail-icon {
  font-size: 18px;
}

.detail-name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #e2e8f0);
  font-family: 'Fira Code', 'Monaco', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.close-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #94a3b8);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.detail-content {
  padding: 12px 14px;
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 10px;
}

.detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-tertiary, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-value {
  font-size: 13px;
  color: var(--color-text-primary, #e2e8f0);
}

.detail-value.path-value {
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 12px;
  word-break: break-all;
  padding: 6px 8px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 4px;
  margin-top: 2px;
}

.node-type-hub {
  color: #f59e0b;
}

.node-type-importer {
  color: #10b981;
}

.node-type-imported {
  color: #8b5cf6;
}

.node-type-isolated {
  color: #6b7280;
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
  z-index: 9999 !important;
  border-radius: 0 !important;
  margin: 0 !important;
  padding: 16px !important;
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
