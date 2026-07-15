<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ImportTreeChart.vue - Interactive tree view of file import relationships
  Issue #707: Added Cytoscape.js network view as default
  Issue #3998: Lazy-load Cytoscape (300KB) on demand
-->
<template>
  <div class="import-tree-chart" :class="{ 'chart-loading': loading, 'fullscreen': isFullscreen }">
    <div v-if="title" class="chart-header">
      <h3 class="chart-title">{{ title ?? $t('charts.importTree.title') }}</h3>
      <span v-if="subtitle" class="chart-subtitle">{{ subtitle ?? $t('charts.importTree.subtitle') }}</span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="chart-loading-overlay">
      <div class="loading-spinner"></div>
      <span>{{ $t('charts.importTree.loading') }}</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="chart-error">
      <span class="error-icon">!</span>
      <span>{{ error }}</span>
    </div>

    <!-- No data state -->
    <div v-else-if="!data || data.length === 0" class="chart-no-data">
      <span>{{ $t('charts.importTree.noData') }}</span>
    </div>

    <!-- Main visualization -->
    <div v-else class="tree-container" :style="{ height: containerHeight }">
      <!-- Search/Filter and View Toggle -->
      <div class="tree-controls">
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="$t('charts.importTree.searchPlaceholder')"
          class="tree-search"
          @input="handleSearch"
        />
        <div class="tree-stats">
          <span>{{ filteredData.length }} {{ $t('charts.importTree.statsFiles') }}</span>
          <span>{{ totalImports }} {{ $t('charts.importTree.statsImports') }}</span>
        </div>
        <div class="view-toggle">
          <button
            :class="{ active: viewMode === 'network' }"
            @click="viewMode = 'network'"
            :title="$t('charts.importTree.networkView')"
          >
            <Icon name="project-diagram" />
          </button>
          <button
            :class="{ active: viewMode === 'tree' }"
            @click="viewMode = 'tree'"
            :title="$t('charts.importTree.treeView')"
          >
            <Icon name="list" />
          </button>
        </div>
      </div>

      <!-- Network view (Cytoscape) - Lazy-loaded on demand -->
      <div v-show="viewMode === 'network'" class="network-view">
        <!-- Loading Cytoscape library -->
        <div v-if="cytoscapeLoading && !cy" class="cytoscape-loading">
          <div class="loading-spinner"></div>
          <span>{{ $t('charts.importTree.loadingVisualization') }}</span>
        </div>

        <!-- Cytoscape error -->
        <div v-else-if="cytoscapeError" class="chart-error">
          <span class="error-icon">!</span>
          <span>{{ cytoscapeError }}</span>
          <button @click="retryCytoscape" class="btn-link">{{ $t('charts.importTree.retry') }}</button>
        </div>

        <!-- Cytoscape container (only when loaded) -->
        <template v-else>
          <div class="network-legend">
            <span class="legend-item importer"><span class="dot"></span> {{ $t('charts.importTree.legend.importsOthers') }}</span>
            <span class="legend-item imported"><span class="dot"></span> {{ $t('charts.importTree.legend.importedByOthers') }}</span>
            <span class="legend-item hub"><span class="dot"></span> {{ $t('charts.importTree.legend.hub') }}</span>
            <span class="legend-item external"><span class="dot"></span> {{ $t('charts.importTree.legend.externalPackage') }}</span>
          </div>
          <div ref="cytoscapeContainer" class="cytoscape-container"></div>
          <div class="network-controls">
            <button @click="zoomIn" :title="$t('charts.importTree.controls.zoomIn')" :aria-label="$t('charts.importTree.controls.zoomIn')">
              <Icon name="plus" />
            </button>
            <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
            <button @click="zoomOut" :title="$t('charts.importTree.controls.zoomOut')" :aria-label="$t('charts.importTree.controls.zoomOut')">
              <Icon name="minus" />
            </button>
            <button @click="fitGraph" :title="$t('charts.importTree.controls.fitToView')" :aria-label="$t('charts.importTree.controls.fitToView')">
              <Icon name="expand" />
            </button>
            <button @click="toggleLayout" :title="$t('charts.importTree.controls.toggleLayout')" :aria-label="$t('charts.importTree.controls.toggleLayout')">
              <Icon name="th" />
            </button>
            <span class="control-separator">|</span>
            <button @click="toggleFullscreen" :title="isFullscreen ? $t('charts.importTree.controls.exitFullscreen') : $t('charts.importTree.controls.fullscreen')" :aria-label="isFullscreen ? $t('charts.importTree.controls.exitFullscreen') : $t('charts.importTree.controls.fullscreen')">
              <Icon :name="isFullscreen ? 'compress' : 'expand-arrows-alt'" />
            </button>
          </div>

          <!-- Node Detail Panel -->
          <div v-if="selectedNode" class="node-detail-panel">
            <div class="detail-header">
              <span class="detail-icon">{{ getFileIcon(selectedNode.path) }}</span>
              <span class="detail-name">{{ selectedNode.shortName }}</span>
              <button class="close-btn" @click="selectedNode = null" :title="$t('charts.importTree.controls.close')" :aria-label="$t('charts.importTree.controls.close')">
                <Icon name="times" />
              </button>
            </div>
            <div class="detail-content">
              <div class="detail-row">
                <span class="detail-label">{{ $t('charts.importTree.detail.fullPath') }}</span>
                <span class="detail-value path-value">{{ selectedNode.path }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{{ $t('charts.importTree.detail.type') }}</span>
                <span class="detail-value" :class="'node-type-' + selectedNode.nodeType">
                  {{ getNodeTypeLabel(selectedNode.nodeType) }}
                </span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{{ $t('charts.importTree.detail.imports') }}</span>
                <span class="detail-value">{{ selectedNode.importsCount }} module{{ selectedNode.importsCount !== 1 ? 's' : '' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{{ $t('charts.importTree.detail.importedBy') }}</span>
                <span class="detail-value">{{ selectedNode.importedByCount }} file{{ selectedNode.importedByCount !== 1 ? 's' : '' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{{ $t('charts.importTree.detail.extension') }}</span>
                <span class="detail-value">{{ getFileExtension(selectedNode.path) }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{{ $t('charts.importTree.detail.directory') }}</span>
                <span class="detail-value path-value">{{ getFileDirectory(selectedNode.path) }}</span>
              </div>
            </div>
          </div>
        </template>
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
                <span v-if="file.imports?.length" class="imports-out" :title="$t('charts.importTree.importsModules', { count: file.imports.length })">
                  ↑{{ file.imports.length }}
                </span>
                <span v-if="file.imported_by?.length" class="imports-in" :title="$t('charts.importTree.importedByFiles', { count: file.imported_by.length })">
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
                  <span>{{ $t('charts.importTree.sections.imports') }} ({{ file.imports.length }})</span>
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
                  <span>{{ $t('charts.importTree.sections.importedBy') }} ({{ file.imported_by.length }})</span>
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
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import { useI18n } from 'vue-i18n'
import { getCssVar } from '@/composables/useCssVars'
import { useDebounce } from '@/composables/useTimeout'

// Type imports only — runtime load handled by the shared composable (#5206)
import type { Core, NodeSingular } from 'cytoscape'

// fcose is a third-party cytoscape layout — its options are not part of the
// core LayoutOptions union (#9724).
interface FcoseLayoutOptions extends cytoscape.BaseLayoutOptions {
  quality?: 'draft' | 'default' | 'proof'
  randomize?: boolean
  componentSpacing?: number
  nodeRepulsion?: number
  edgeElasticity?: number
  nestingFactor?: number
  gravity?: number
  numIter?: number
  animate?: boolean
  fit?: boolean
  padding?: number
}
import { useCytoscapeLibrary } from '@/composables/charts/useCytoscapeLibrary'

const { t } = useI18n()

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
  title: undefined,
  subtitle: undefined,
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
const nodeExpansion = useExpansion<string>()
const expandedNodes = nodeExpansion.expanded
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

// Cytoscape lazy-load state is owned by the shared composable (#5206).
// `onReady` below is the chart-specific init for the network view; retry
// re-invokes it if the initial load failed.
const {
  loading: cytoscapeLoading,
  error: cytoscapeError,
  cytoscapeModule,
  ensureReady: ensureCytoscapeReady,
  retry: retryCytoscape,
} = useCytoscapeLibrary(async () => {
  await nextTick()
  if (viewMode.value === 'network' && !cy && cytoscapeContainer.value) {
    initCytoscape()
    updateCytoscapeElements()
  }
})

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
  nodeExpansion.toggle(path)
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
  if (!path) return t('charts.importTree.detail.unknown')
  const lastDot = path.lastIndexOf('.')
  if (lastDot === -1) return t('charts.importTree.detail.noExtension')
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
    case 'hub': return t('charts.importTree.nodeTypes.hub')
    case 'importer': return t('charts.importTree.nodeTypes.importer')
    case 'imported': return t('charts.importTree.nodeTypes.imported')
    case 'isolated': return t('charts.importTree.nodeTypes.isolated')
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

const debouncedUpdateCytoscapeElements = useDebounce(() => {
  updateCytoscapeElements()
}, 300)

function handleSearch() {
  debouncedUpdateCytoscapeElements()
}

// ============================================================================
// Cytoscape Methods
// ============================================================================

function initCytoscape() {
  if (!cytoscapeModule.value || !cytoscapeContainer.value) return

  cy = cytoscapeModule.value({
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

function getCytoscapeStyles(): Array<{ selector: string; style: Record<string, string | number> }> {
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

  const elements: Array<{ data: Record<string, unknown>; position?: { x: number; y: number } }> = []
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
        importedBy,
        type: determineNodeType(importsCount, importedBy)
      }
    })

    // Add edges for imports
    // const imports = normalizeImports(file.imports)
    const importsForEdges = normalizeImports(file.imports)
    for (const imp of importsForEdges) {
      if (imp.file && nodeIds.has(imp.file)) {
        elements.push({
          data: {
            id: `${file.path}→${imp.file}`,
            source: file.path,
            target: imp.file,
            color: getCssVar('--chart-teal', '#14b8a6'),
            width: 1.5
          }
        })
      }
    }
  }

  cy.elements().remove()
  cy.add(elements)

  // Apply layout
  if (layoutMode.value === 'force') {
    cy.layout({
      name: 'fcose',
      quality: 'default',
      randomize: true,
      componentSpacing: 40,
      nodeRepulsion: 4500,
      edgeElasticity: 0.5,
      nestingFactor: 0.1,
      gravity: 250,
      numIter: 2500,
      tile: true,
      tilingPaddingVertical: 10,
      tilingPaddingHorizontal: 10,
      gravityRangeCompound: 1.5,
      initialEnergyOnMultiLevel: 0.15,
      multiLevelSpacing: 1.5
    } as FcoseLayoutOptions).run()
  } else {
    const cols = Math.ceil(Math.sqrt(nodeIds.size))
    let i = 0
    for (const node of cy.nodes()) {
      const row = Math.floor(i / cols)
      const col = i % cols
      node.position({
        x: col * 150 + 75,
        y: row * 150 + 75
      })
      i++
    }
  }

  fitGraph()
}

function zoomIn() {
  if (!cy) return
  const currentZoom = cy.zoom()
  cy.zoom(currentZoom * 1.2)
}

function zoomOut() {
  if (!cy) return
  const currentZoom = cy.zoom()
  cy.zoom(currentZoom / 1.2)
}

function fitGraph() {
  if (!cy) return
  cy.fit(undefined, 50)
}

function toggleLayout() {
  layoutMode.value = layoutMode.value === 'force' ? 'grid' : 'force'
  updateCytoscapeElements()
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  nextTick(() => {
    if (cy) {
      cy.resize()
      fitGraph()
    }
  })
}

function highlightConnected(node: NodeSingular) {
  if (!cy) return

  const connectedEdges = node.connectedEdges()
  const connectedNodes = node.neighborhood().nodes()

  cy.elements().addClass('dimmed')
  node.removeClass('dimmed')
  connectedEdges.removeClass('dimmed')
  connectedNodes.removeClass('dimmed')

  node.addClass('highlighted')
  connectedEdges.addClass('highlighted')
  connectedNodes.addClass('highlighted')
}

function clearHighlight() {
  if (!cy) return
  cy.elements().removeClass('dimmed').removeClass('highlighted')
}

// Watch for view mode changes to lazy-load Cytoscape
watch(() => viewMode.value, async (newMode) => {
  if (newMode === 'network' && !cy && !cytoscapeLoading.value) {
    await ensureCytoscapeReady()
  }
})

// Watch for data changes to update graph
watch(() => props.data, () => {
  if (cy) {
    updateCytoscapeElements()
  }
})

// Watch for filtered data changes
watch(() => filteredData.value, () => {
  if (cy) {
    updateCytoscapeElements()
  }
})

// Cleanup on unmount
onUnmounted(() => {
  if (cy) {
    cy.destroy()
    cy = null
  }
})
</script>

<style scoped>
.import-tree-chart {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.chart-header {
  padding: var(--spacing-3);
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.chart-title {
  margin: var(--spacing-0);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.chart-subtitle {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.chart-loading,
.chart-error,
.chart-no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  gap: var(--spacing-2);
  color: var(--text-secondary);
  font-size: 0.95rem;
  contain: layout style paint;
}

.chart-loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  z-index: 10;
  gap: var(--spacing-2);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.chart-error {
  background: var(--bg-error, rgba(239, 68, 68, 0.1));
  border: 1px solid var(--border-error, #ef4444);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  gap: var(--spacing-2);
}

.error-icon {
  font-weight: bold;
  font-size: var(--text-xl);
  color: var(--color-error, #ef4444);
}

.btn-link {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  text-decoration: underline;
  font-size: var(--text-sm);
  padding: var(--spacing-0);
}

.tree-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  position: relative;
}

.tree-controls {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
  padding: var(--spacing-2);
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-wrap: wrap;
}

.tree-search {
  flex: 1;
  min-width: 200px;
  padding: var(--spacing-1) var(--spacing-2);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.tree-search::placeholder {
  color: var(--text-tertiary);
}

.tree-stats {
  display: flex;
  gap: var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
}

.view-toggle {
  display: flex;
  gap: var(--spacing-1);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  padding: var(--spacing-0-5);
}

.view-toggle button {
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--duration-200) var(--ease-out);
}

.view-toggle button.active {
  background: var(--color-primary-light, rgba(59, 130, 246, 0.1));
  color: var(--color-primary);
}

.network-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  position: relative;
}

.cytoscape-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: var(--spacing-2);
  color: var(--text-secondary);
}

.network-legend {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-wrap: wrap;
  font-size: 0.85rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  color: var(--text-secondary);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.legend-item.importer .dot {
  background: var(--color-success, #10b981);
}

.legend-item.imported .dot {
  background: var(--chart-purple, #8b5cf6);
}

.legend-item.hub .dot {
  background: var(--color-warning, #f59e0b);
}

.legend-item.external .dot {
  background: var(--text-tertiary, #6b7280);
}

.cytoscape-container {
  flex: 1;
  width: 100%;
  border-bottom: 1px solid var(--border-color);
}

.network-controls {
  display: flex;
  gap: var(--spacing-1);
  align-items: center;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  flex-wrap: wrap;
}

.network-controls button {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--duration-200) var(--ease-out);
}

.network-controls button:hover {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
}

.zoom-level {
  padding: 0 var(--spacing-1);
  font-size: 0.8rem;
  color: var(--text-secondary);
  min-width: 40px;
  text-align: center;
}

.control-separator {
  color: var(--border-color);
  margin: 0 var(--spacing-1);
}

.node-detail-panel {
  position: absolute;
  right: 0;
  top: 0;
  width: 280px;
  max-height: 100%;
  background: var(--bg-primary);
  border-left: 1px solid var(--border-color);
  border-radius: 0;
  overflow-y: auto;
  z-index: 100;
  box-shadow: var(--shadow-sm);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  position: sticky;
  top: 0;
  z-index: 101;
}

.detail-icon {
  font-size: var(--text-2xl);
  min-width: 24px;
}

.detail-name {
  flex: 1;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  word-break: break-word;
  font-size: 0.95rem;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-lg);
  padding: var(--spacing-0);
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: var(--text-primary);
}

.detail-content {
  padding: var(--spacing-2);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.detail-label {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  word-break: break-word;
}

.detail-value.path-value {
  font-family: monospace;
  font-size: 0.8rem;
  background: var(--bg-secondary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.detail-value.node-type-hub {
  color: var(--color-warning, #f59e0b);
  font-weight: var(--font-semibold);
}

.detail-value.node-type-importer {
  color: var(--color-success, #10b981);
  font-weight: var(--font-semibold);
}

.detail-value.node-type-imported {
  color: var(--chart-purple, #8b5cf6);
  font-weight: var(--font-semibold);
}

.detail-value.node-type-isolated {
  color: var(--text-tertiary, #6b7280);
  font-weight: var(--font-semibold);
}

.tree-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.tree-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.tree-node {
  border-bottom: 1px solid var(--border-color);
}

.node-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  cursor: pointer;
  background: var(--bg-primary);
  transition: background var(--duration-150) var(--ease-out);
}

.node-header:hover {
  background: var(--bg-secondary);
}

.tree-node.expanded .node-header {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.expand-icon {
  width: 20px;
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.file-icon {
  font-size: var(--text-base);
  flex-shrink: 0;
}

.file-name {
  flex: 1;
  color: var(--text-primary);
  font-weight: var(--font-medium);
  font-size: 0.95rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.import-counts {
  display: flex;
  gap: var(--spacing-1);
  font-size: 0.8rem;
  flex-shrink: 0;
}

.imports-out {
  color: var(--color-success, #10b981);
  font-weight: var(--font-medium);
}

.imports-in {
  color: var(--chart-purple, #8b5cf6);
  font-weight: var(--font-medium);
}

.node-children {
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-color);
  padding: var(--spacing-2);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.import-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: 0.8rem;
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: var(--spacing-1);
}

.section-icon {
  font-size: var(--text-xs);
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
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  font-size: 0.8rem;
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-out);
  color: var(--text-secondary);
}

.import-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.import-item.external {
  color: var(--text-tertiary);
}

.import-item.internal {
  color: var(--text-primary);
}

.import-icon {
  flex-shrink: 0;
}

.import-module {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.import-file {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

.import-via {
  flex-shrink: 0;
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.import-tree-chart.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 100%;
  z-index: var(--z-modal);
  border-radius: 0;
}

.import-tree-chart.fullscreen .cytoscape-container {
  border-bottom: none;
}

.chart-no-data {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}
</style>
