<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  FunctionCallGraph.vue - Interactive function call graph visualization
  Issue #707: Added Cytoscape.js network view as default
-->
<template>
  <div class="function-call-graph" :class="{ 'chart-loading': loading, 'fullscreen': isFullscreen }">
    <div v-if="title" class="chart-header">
      <h3 class="chart-title">{{ title }}</h3>
      <span v-if="subtitle" class="chart-subtitle">{{ subtitle }}</span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="chart-loading-overlay">
      <div class="loading-spinner"></div>
      <span>Analyzing function calls...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="chart-error">
      <span class="error-icon">!</span>
      <span>{{ error }}</span>
    </div>

    <!-- No data state -->
    <div v-else-if="!data || (!data.nodes?.length && !data.edges?.length)" class="chart-no-data">
      <span>No function call data available</span>
    </div>

    <!-- Graph content -->
    <div v-else class="graph-container" :style="{ height: containerHeight }">
      <!-- Controls -->
      <div class="graph-controls">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search functions..."
          class="graph-search"
          @input="handleSearch"
        />
        <select v-model="filterModule" class="module-filter" @change="handleModuleFilter">
          <option value="">All Modules</option>
          <option v-for="mod in uniqueModules" :key="mod" :value="mod">
            {{ truncateModule(mod || '') }}
          </option>
        </select>
        <div class="view-toggle">
          <button
            :class="{ active: viewMode === 'network' }"
            @click="viewMode = 'network'"
            title="Network View (Cytoscape)"
          >
            <i class="fas fa-project-diagram"></i>
          </button>
          <button
            :class="{ active: viewMode === 'list' }"
            @click="viewMode = 'list'"
            title="List View"
          >
            <i class="fas fa-list"></i>
          </button>
          <button
            :class="{ active: viewMode === 'stats' }"
            @click="viewMode = 'stats'"
            title="Cluster View"
          >
            <i class="fas fa-circle-nodes"></i>
          </button>
          <button
            :class="{ active: viewMode === 'orphaned' }"
            @click="viewMode = 'orphaned'"
            title="Orphaned Functions (unused)"
          >
            <i class="fas fa-unlink"></i>
          </button>
        </div>
      </div>

      <!-- Stats bar -->
      <div class="stats-bar">
        <div class="stat">
          <span class="stat-value">{{ data.nodes?.length || 0 }}</span>
          <span class="stat-label">Functions</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ data.edges?.length || 0 }}</span>
          <span class="stat-label">Calls</span>
        </div>
        <div class="stat stat-resolved" :class="{ active: resolvedFilter === 'resolved' }" @click="toggleResolvedFilter('resolved')">
          <span class="stat-value">{{ summary?.resolved_calls || 0 }}</span>
          <span class="stat-label">Resolved</span>
        </div>
        <div class="stat stat-unresolved" :class="{ active: resolvedFilter === 'unresolved' }" @click="toggleResolvedFilter('unresolved')">
          <span class="stat-value">{{ unresolvedCount }}</span>
          <span class="stat-label">Unresolved</span>
        </div>
        <div class="stat stat-orphaned" :class="{ active: viewMode === 'orphaned' }" @click="viewMode = 'orphaned'">
          <span class="stat-value">{{ orphanedFunctions?.length || summary?.orphaned_functions || 0 }}</span>
          <span class="stat-label">Orphaned</span>
        </div>
      </div>

      <!-- Network view (Cytoscape) - DEFAULT -->
      <div v-show="viewMode === 'network'" class="network-view">
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
        <div v-if="selectedNodeInfo" class="node-detail-panel">
          <div class="detail-header">
            <span v-if="selectedNodeInfo.isAsync" class="async-badge">async</span>
            <span class="detail-name">{{ selectedNodeInfo.name }}</span>
            <button class="close-btn" @click="selectedNodeInfo = null" title="Close">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="detail-content">
            <div class="detail-row">
              <span class="detail-label">Full Name:</span>
              <span class="detail-value path-value">{{ selectedNodeInfo.fullName }}</span>
            </div>
            <div v-if="selectedNodeInfo.module" class="detail-row">
              <span class="detail-label">Module:</span>
              <span class="detail-value">{{ selectedNodeInfo.module }}</span>
            </div>
            <div v-if="selectedNodeInfo.className" class="detail-row">
              <span class="detail-label">Class:</span>
              <span class="detail-value class-value">{{ selectedNodeInfo.className }}</span>
            </div>
            <div v-if="selectedNodeInfo.file" class="detail-row">
              <span class="detail-label">File:</span>
              <span class="detail-value path-value">{{ selectedNodeInfo.file }}:{{ selectedNodeInfo.line }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Outgoing Calls:</span>
              <span class="detail-value calls-out">{{ selectedNodeInfo.outgoingCalls }} function{{ selectedNodeInfo.outgoingCalls !== 1 ? 's' : '' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Incoming Calls:</span>
              <span class="detail-value calls-in">{{ selectedNodeInfo.incomingCalls }} caller{{ selectedNodeInfo.incomingCalls !== 1 ? 's' : '' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- List view -->
      <div v-if="viewMode === 'list'" class="list-view">
        <div class="function-list">
          <div
            v-for="node in filteredNodes"
            :key="node.id"
            class="function-item"
            :class="{ expanded: expandedFuncs.has(node.id), selected: selectedFunc === node.id }"
            @click="toggleFunction(node.id)"
          >
            <div class="func-header">
              <span class="expand-icon">
                {{ getOutgoingCalls(node.id).length > 0 || getIncomingCalls(node.id).length > 0 ? (expandedFuncs.has(node.id) ? '▼' : '▶') : '•' }}
              </span>
              <span v-if="node.is_async" class="async-badge">async</span>
              <span v-if="node.class" class="class-badge">{{ node.class }}</span>
              <span class="func-name">{{ node.name }}</span>
              <div class="call-counts">
                <span class="outgoing" :title="`Makes ${getOutgoingCalls(node.id).length} calls`">
                  ↗{{ getOutgoingCalls(node.id).length }}
                </span>
                <span class="incoming" :title="`Called ${getIncomingCalls(node.id).length} times`">
                  ↙{{ getIncomingCalls(node.id).length }}
                </span>
              </div>
            </div>

            <!-- Expanded details -->
            <div v-if="expandedFuncs.has(node.id)" class="func-details">
              <div class="func-location">
                <i class="fas fa-file-code"></i>
                {{ node.file }}:{{ node.line }}
              </div>

              <!-- Outgoing calls -->
              <div v-if="getOutgoingCalls(node.id).length > 0" class="calls-section">
                <div class="section-label">
                  <span class="arrow">↗</span> Calls ({{ getOutgoingCalls(node.id).length }})
                </div>
                <div class="call-list">
                  <div
                    v-for="(edge, idx) in getOutgoingCalls(node.id).slice(0, 10)"
                    :key="`out-${edge.to || edge.target || idx}`"
                    class="call-item"
                    :class="{ resolved: edge.resolved !== false, unresolved: edge.resolved === false }"
                  >
                    <span class="call-name">{{ edge.to_name || getNodeName(edge.to || edge.target || '') }}</span>
                    <span v-if="(edge.count ?? 0) > 1" class="call-count">×{{ edge.count }}</span>
                    <span v-if="edge.resolved === false" class="unresolved-badge">external</span>
                  </div>
                  <div v-if="getOutgoingCalls(node.id).length > 10" class="more-calls">
                    +{{ getOutgoingCalls(node.id).length - 10 }} more
                  </div>
                </div>
              </div>

              <!-- Incoming calls -->
              <div v-if="getIncomingCalls(node.id).length > 0" class="calls-section">
                <div class="section-label">
                  <span class="arrow">↙</span> Called by ({{ getIncomingCalls(node.id).length }})
                </div>
                <div class="call-list">
                  <div
                    v-for="(edge, idx) in getIncomingCalls(node.id).slice(0, 10)"
                    :key="`in-${edge.from || edge.source || idx}`"
                    class="call-item resolved"
                  >
                    <span class="call-name">{{ getNodeName(edge.from || edge.source || '') }}</span>
                    <span v-if="(edge.count ?? 0) > 1" class="call-count">×{{ edge.count }}</span>
                  </div>
                  <div v-if="getIncomingCalls(node.id).length > 10" class="more-calls">
                    +{{ getIncomingCalls(node.id).length - 10 }} more
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Stats/Cluster view (network visualization) -->
      <div v-show="viewMode === 'stats'" class="cluster-view">
        <div class="graph-info">
          <i class="fas fa-info-circle"></i>
          <span>Top callers (green) and most called functions (purple) as clusters</span>
        </div>
        <div class="cluster-legend">
          <span class="legend-item caller"><span class="dot"></span> Top Callers</span>
          <span class="legend-item called"><span class="dot"></span> Most Called</span>
          <span class="legend-item hub"><span class="dot"></span> Hub (Both)</span>
        </div>
        <div ref="clusterContainer" class="cluster-container"></div>
        <div class="network-controls cluster-controls">
          <button @click="zoomInCluster" title="Zoom in">
            <i class="fas fa-plus"></i>
          </button>
          <span class="zoom-level">{{ Math.round(clusterZoomLevel * 100) }}%</span>
          <button @click="zoomOutCluster" title="Zoom out">
            <i class="fas fa-minus"></i>
          </button>
          <button @click="fitClusterGraph" title="Fit to view">
            <i class="fas fa-expand"></i>
          </button>
          <button @click="toggleClusterLayout" title="Toggle layout">
            <i class="fas fa-th"></i>
          </button>
        </div>
      </div>

      <!-- Orphaned Functions view -->
      <div v-show="viewMode === 'orphaned'" class="orphaned-view">
        <div class="graph-info warning">
          <i class="fas fa-exclamation-triangle"></i>
          <span>Functions that are defined but never called by other functions. Review for potential dead code or missing integrations.</span>
        </div>

        <!-- Orphaned functions search/filter -->
        <div class="orphaned-controls">
          <input
            v-model="orphanedSearch"
            type="text"
            placeholder="Search orphaned functions..."
            class="orphaned-search"
          />
          <select v-model="orphanedModuleFilter" class="orphaned-module-filter">
            <option value="">All Modules</option>
            <option v-for="mod in orphanedModules" :key="mod" :value="mod">
              {{ truncateModule(mod || '') }}
            </option>
          </select>
        </div>

        <!-- Orphaned functions list - Issue #711: Virtual scrolling for performance -->
        <div v-if="filteredOrphanedFunctions.length > 0" class="orphaned-list-container" v-bind="orphanedContainerProps">
          <div class="orphaned-list" v-bind="orphanedListProps">
            <div
              v-for="{ item: func, key } in visibleOrphanedFunctions"
              :key="key"
              class="orphaned-item"
              @click="emit('select', func.id)"
            >
              <div class="orphaned-item-header">
                <span v-if="func.is_async" class="async-badge">async</span>
                <span class="func-name">{{ func.name }}</span>
                <span v-if="func.class" class="class-badge">{{ func.class }}</span>
              </div>
              <div class="orphaned-item-details">
                <span class="detail-module" :title="func.module">
                  <i class="fas fa-cube"></i> {{ truncateModule(func.module || '') }}
                </span>
                <span class="detail-file" :title="func.file">
                  <i class="fas fa-file-code"></i> {{ truncateFile(func.file) }}:{{ func.line }}
                </span>
              </div>
            </div>
          </div>
          <!-- Virtual scroll info -->
          <div class="virtual-scroll-info">
            <span>Showing {{ visibleOrphanedFunctions.length }} of {{ filteredOrphanedFunctions.length }} functions (scroll for more)</span>
          </div>
        </div>

        <!-- Empty state -->
        <div v-else class="orphaned-empty">
          <i class="fas fa-check-circle"></i>
          <span v-if="orphanedSearch || orphanedModuleFilter">No orphaned functions match your filter</span>
          <span v-else>No orphaned functions detected - all functions are connected!</span>
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
// Issue #711: Virtual scrolling for large orphaned function lists
import { useVirtualScrollSimple } from '@/composables/useVirtualScroll'

// Register fcose layout
cytoscape.use(fcose)

// Flexible interface to support multiple data formats
interface GraphNode {
  id: string
  name: string
  full_name?: string
  module?: string
  class?: string | null
  file?: string
  line?: number
  is_async?: boolean
  type?: string
}

interface GraphEdge {
  from?: string
  source?: string
  to?: string
  target?: string
  to_name?: string
  resolved?: boolean
  count?: number
  type?: string
}

interface CallGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

interface SummaryData {
  total_functions: number
  connected_functions: number
  orphaned_functions?: number
  total_call_relationships: number
  resolved_calls: number
  unresolved_calls: number
  top_callers: { function: string; calls: number }[]
  most_called: { function: string; calls: number }[]
}

interface OrphanedFunction {
  id: string
  name: string
  full_name: string
  module: string
  class: string | null
  file: string
  line: number
  is_async: boolean
}

interface Props {
  data: CallGraphData
  summary?: SummaryData
  orphanedFunctions?: OrphanedFunction[]
  title?: string
  subtitle?: string
  height?: number | string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Function Call Graph',
  subtitle: 'View function call relationships',
  orphanedFunctions: () => [],
  height: 600,
  loading: false,
  error: ''
})

const emit = defineEmits<{
  (e: 'select', funcId: string): void
}>()

// State
const searchQuery = ref('')
const filterModule = ref('')
const resolvedFilter = ref<'all' | 'resolved' | 'unresolved'>('all')
const viewMode = ref<'network' | 'list' | 'stats' | 'orphaned'>('network') // Default to network view
const expandedFuncs = ref<Set<string>>(new Set())
const selectedFunc = ref<string | null>(null)
const zoomLevel = ref(1)
const layoutMode = ref<'force' | 'grid'>('force')

// Orphaned functions state
const orphanedSearch = ref('')
const orphanedModuleFilter = ref('')
// Issue #711: orphanedDisplayLimit removed - now using virtual scrolling

// Cytoscape instances
const cytoscapeContainer = ref<HTMLElement | null>(null)
const clusterContainer = ref<HTMLElement | null>(null)
let cy: Core | null = null
let clusterCy: Core | null = null
const clusterZoomLevel = ref(1)
const clusterLayoutMode = ref<'force' | 'grid'>('force')
const isFullscreen = ref(false)
const selectedNodeInfo = ref<{
  id: string
  name: string
  fullName: string
  module: string
  file: string
  line: number
  isAsync: boolean
  className: string | null
  outgoingCalls: number
  incomingCalls: number
} | null>(null)

// Computed
const containerHeight = computed(() => {
  if (typeof props.height === 'number') {
    return `${props.height}px`
  }
  return props.height
})

const uniqueModules = computed(() => {
  if (!props.data?.nodes) return []
  const modules = new Set(props.data.nodes.map(n => n.module).filter(Boolean))
  return Array.from(modules).sort()
})

// Calculate unresolved count from edges
const unresolvedCount = computed(() => {
  if (props.summary?.unresolved_calls !== undefined) {
    return props.summary.unresolved_calls
  }
  // Fallback: calculate from edges
  if (!props.data?.edges) return 0
  return props.data.edges.filter(e => !e.resolved).length
})

// Orphaned functions computed properties
const orphanedModules = computed(() => {
  if (!props.orphanedFunctions?.length) return []
  const modules = new Set(props.orphanedFunctions.map(f => f.module).filter(Boolean))
  return Array.from(modules).sort()
})

const filteredOrphanedFunctions = computed(() => {
  if (!props.orphanedFunctions?.length) return []

  let functions = [...props.orphanedFunctions]

  // Filter by module
  if (orphanedModuleFilter.value) {
    functions = functions.filter(f => f.module === orphanedModuleFilter.value)
  }

  // Filter by search
  if (orphanedSearch.value) {
    const query = orphanedSearch.value.toLowerCase()
    functions = functions.filter(f =>
      f.name.toLowerCase().includes(query) ||
      f.full_name?.toLowerCase().includes(query) ||
      f.module?.toLowerCase().includes(query) ||
      f.file?.toLowerCase().includes(query)
    )
  }

  return functions
})

// Issue #711: Virtual scrolling for orphaned functions list
// Renders only visible items for better performance with 500+ functions
const {
  containerProps: orphanedContainerProps,
  listProps: orphanedListProps,
  visibleItems: visibleOrphanedFunctions
} = useVirtualScrollSimple(
  filteredOrphanedFunctions,
  80, // Item height in pixels (orphaned-item height)
  {
    buffer: 5,
    containerHeight: 500,
    getKey: (item: OrphanedFunction) => item.id
  }
)

const filteredNodes = computed(() => {
  if (!props.data?.nodes) return []

  let nodes = [...props.data.nodes]

  // Filter by module
  if (filterModule.value) {
    nodes = nodes.filter(n => n.module === filterModule.value)
  }

  // Filter by search
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    nodes = nodes.filter(n =>
      n.name.toLowerCase().includes(query) ||
      (n.full_name?.toLowerCase().includes(query) ?? false) ||
      (n.module?.toLowerCase().includes(query) ?? false)
    )
  }

  // Filter by resolved status
  if (resolvedFilter.value !== 'all') {
    const showResolved = resolvedFilter.value === 'resolved'
    nodes = nodes.filter(n => {
      const outgoingCalls = getOutgoingCalls(n.id)
      if (showResolved) {
        return outgoingCalls.some(e => e.resolved)
      } else {
        return outgoingCalls.some(e => !e.resolved)
      }
    })
  }

  // Sort by call count
  return nodes.sort((a, b) => {
    const aCount = getOutgoingCalls(a.id).length + getIncomingCalls(a.id).length
    const bCount = getOutgoingCalls(b.id).length + getIncomingCalls(b.id).length
    return bCount - aCount
  })
})


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
    const funcId = node.id()
    selectedFunc.value = funcId

    // Get node data for detail panel
    const graphNode = props.data?.nodes?.find(n => n.id === funcId)
    if (graphNode) {
      selectedNodeInfo.value = {
        id: funcId,
        name: graphNode.name,
        fullName: graphNode.full_name || funcId,
        module: graphNode.module || '',
        file: graphNode.file || '',
        line: graphNode.line || 0,
        isAsync: graphNode.is_async || false,
        className: graphNode.class || null,
        outgoingCalls: getOutgoingCalls(funcId).length,
        incomingCalls: getIncomingCalls(funcId).length
      }
    }

    emit('select', funcId)
    highlightConnected(node)
  })

  cy.on('tap', (evt) => {
    if (evt.target === cy) {
      selectedFunc.value = null
      selectedNodeInfo.value = null
      clearHighlight()
    }
  })

  cy.on('mouseover', 'node', (evt) => {
    const node = evt.target as NodeSingular
    highlightConnected(node)
  })

  cy.on('mouseout', 'node', () => {
    if (!selectedFunc.value) {
      clearHighlight()
    }
  })

  cy.on('zoom', () => {
    zoomLevel.value = cy?.zoom() || 1
  })
}

/**
 * Gets a CSS variable value from the document root
 * Issue #704: Use design tokens for theming
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/**
 * Returns Cytoscape graph styles using design tokens
 * Issue #704: All colors now use CSS custom properties for theming
 */
function getCytoscapeStyles(): cytoscape.StylesheetStyle[] {
  // Issue #704: Read colors from design tokens at style creation time
  const textPrimary = getCssVar('--text-primary', '#e2e8f0')
  const bgSecondary = getCssVar('--bg-secondary', '#1e293b')
  const bgTertiary = getCssVar('--bg-tertiary', '#334155')
  const colorPrimary = getCssVar('--color-primary', '#3b82f6')
  const colorSuccess = getCssVar('--color-success', '#10b981')

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
        'border-color': bgTertiary,
        'text-max-width': '80px',
        'text-wrap': 'ellipsis'
      }
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 3,
        'border-color': colorPrimary
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 3,
        'border-color': colorSuccess
      }
    },
    {
      selector: 'node.dimmed',
      style: {
        'opacity': 0.2
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
        'opacity': 0.6
      }
    },
    {
      selector: 'edge.highlighted',
      style: {
        'opacity': 1,
        'width': 3,
        'line-color': colorSuccess,
        'target-arrow-color': colorSuccess
      }
    },
    {
      selector: 'edge.dimmed',
      style: {
        'opacity': 0.1
      }
    }
  ]
}

function updateCytoscapeElements() {
  if (!cy) return

  const elements: cytoscape.ElementDefinition[] = []
  const nodeIds = new Set(filteredNodes.value.map(n => n.id))

  // Add nodes
  for (const node of filteredNodes.value) {
    const outgoing = getOutgoingCalls(node.id).length
    const incoming = getIncomingCalls(node.id).length
    const totalCalls = outgoing + incoming
    const size = 20 + Math.min(totalCalls * 2, 30)

    // Issue #704: Color based on call ratio - using design tokens
    let color = getCssVar('--text-tertiary', '#6b7280') // Default gray
    if (outgoing > incoming) {
      color = getCssVar('--color-success', '#10b981') // Green for callers
    } else if (incoming > outgoing) {
      color = getCssVar('--chart-purple', '#8b5cf6') // Purple for called
    } else if (totalCalls > 0) {
      color = getCssVar('--color-primary', '#3b82f6') // Blue for balanced
    }

    // Async functions get special color
    if (node.is_async) {
      color = getCssVar('--color-warning', '#f59e0b')
    }

    elements.push({
      data: {
        id: node.id,
        label: node.name,
        color,
        size,
        module: node.module,
        isAsync: node.is_async
      }
    })
  }

  // Add edges (only between visible nodes)
  if (props.data?.edges) {
    for (const edge of props.data.edges) {
      const source = edge.from || edge.source
      const target = edge.to || edge.target

      if (source && target && nodeIds.has(source) && nodeIds.has(target)) {
        // Issue #704: Edge colors using design tokens
        const edgeColor = edge.resolved === false
          ? getCssVar('--chart-orange', '#fb923c')
          : getCssVar('--text-tertiary', '#64748b')
        const edgeWidth = Math.min(1 + (edge.count || 1) * 0.5, 5)

        elements.push({
          data: {
            id: `${source}-${target}`,
            source,
            target,
            color: edgeColor,
            width: edgeWidth,
            resolved: edge.resolved
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
        idealEdgeLength: 100,
        nodeRepulsion: 5000,
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
      if (clusterCy) {
        clusterCy.resize()
        fitClusterGraph()
      }
    }, 100)
  })
}

// ============================================================================
// Cluster View Cytoscape Methods
// ============================================================================

function initClusterCytoscape() {
  if (!clusterContainer.value) return

  clusterCy = cytoscape({
    container: clusterContainer.value,
    style: getClusterCytoscapeStyles(),
    elements: [],
    minZoom: 0.1,
    maxZoom: 3,
    wheelSensitivity: 0.3,
    boxSelectionEnabled: false
  })

  // Event handlers
  clusterCy.on('tap', 'node', (evt) => {
    const node = evt.target as NodeSingular
    const funcId = node.id()
    selectedFunc.value = funcId
    emit('select', funcId)
    highlightClusterConnected(node)
  })

  clusterCy.on('tap', (evt) => {
    if (evt.target === clusterCy) {
      selectedFunc.value = null
      clearClusterHighlight()
    }
  })

  clusterCy.on('mouseover', 'node', (evt) => {
    const node = evt.target as NodeSingular
    highlightClusterConnected(node)
  })

  clusterCy.on('mouseout', 'node', () => {
    if (!selectedFunc.value) {
      clearClusterHighlight()
    }
  })

  clusterCy.on('zoom', () => {
    clusterZoomLevel.value = clusterCy?.zoom() || 1
  })
}

function getClusterCytoscapeStyles(): cytoscape.StylesheetStyle[] {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'label': 'data(label)',
        'width': 'data(size)',
        'height': 'data(size)',
        'font-size': '11px',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 8,
        'color': getCssVar('--text-secondary', '#e2e8f0'),
        'text-outline-color': getCssVar('--bg-secondary', '#1e293b'),
        'text-outline-width': 2,
        'border-width': 3,
        'border-color': 'data(borderColor)',
        'text-max-width': '100px',
        'text-wrap': 'ellipsis'
      }
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': getCssVar('--text-primary', '#ffffff')
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 4,
        'border-color': getCssVar('--color-warning-light', '#fbbf24')
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
        'width': 4,
        'line-color': getCssVar('--color-warning-light', '#fbbf24'),
        'target-arrow-color': getCssVar('--color-warning-light', '#fbbf24')
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

function updateClusterElements() {
  if (!clusterCy) return

  const elements: cytoscape.ElementDefinition[] = []
  const topCallers = new Set((props.summary?.top_callers || []).map(c => c.function))
  const mostCalled = new Set((props.summary?.most_called || []).map(c => c.function))

  // Create a map to track function call counts
  const callerCounts = new Map<string, number>()
  const calledCounts = new Map<string, number>()

  for (const item of props.summary?.top_callers || []) {
    callerCounts.set(item.function, item.calls)
  }
  for (const item of props.summary?.most_called || []) {
    calledCounts.set(item.function, item.calls)
  }

  // Add nodes for top callers and most called
  const allFunctions = new Set([...topCallers, ...mostCalled])

  for (const funcName of allFunctions) {
    const isCaller = topCallers.has(funcName)
    const isCalled = mostCalled.has(funcName)
    const isHub = isCaller && isCalled

    // Calculate size based on call count
    const callerCount = callerCounts.get(funcName) || 0
    const calledCount = calledCounts.get(funcName) || 0
    const maxCount = Math.max(callerCount, calledCount, 1)
    const maxPossible = Math.max(
      ...(props.summary?.top_callers?.map(c => c.calls) || [1]),
      ...(props.summary?.most_called?.map(c => c.calls) || [1])
    )
    const size = 30 + (maxCount / maxPossible) * 40

    // Issue #704: Color based on type - using design tokens
    let color: string
    let borderColor: string
    if (isHub) {
      color = getCssVar('--color-warning', '#f59e0b') // Amber for hubs (both caller and called)
      borderColor = getCssVar('--color-warning-light', '#fbbf24')
    } else if (isCaller) {
      color = getCssVar('--color-success', '#10b981') // Green for callers
      borderColor = getCssVar('--color-success-light', '#34d399')
    } else {
      color = getCssVar('--chart-purple', '#8b5cf6') // Purple for called
      borderColor = getCssVar('--chart-purple-light', '#a78bfa')
    }

    // Get short name for label
    const shortName = funcName.split('.').slice(-2).join('.')

    elements.push({
      data: {
        id: funcName,
        label: shortName,
        fullName: funcName,
        color,
        borderColor,
        size,
        callerCount,
        calledCount,
        isHub
      }
    })
  }

  // Add edges between related functions
  if (props.data?.edges) {
    for (const edge of props.data.edges) {
      const source = edge.from || edge.source
      const target = edge.to || edge.target

      if (source && target && allFunctions.has(source) && allFunctions.has(target)) {
        const edgeWidth = Math.min(1 + (edge.count || 1) * 0.5, 5)
        // Issue #704: Edge colors using design tokens
        const edgeColor = edge.resolved === false
          ? getCssVar('--chart-orange', '#fb923c')
          : getCssVar('--text-tertiary', '#64748b')

        elements.push({
          data: {
            id: `cluster-${source}-${target}`,
            source,
            target,
            color: edgeColor,
            width: edgeWidth
          }
        })
      }
    }
  }

  // Update graph
  clusterCy.elements().remove()
  clusterCy.add(elements)

  // Run layout
  runClusterLayout()
}

function runClusterLayout() {
  if (!clusterCy || clusterCy.nodes().length === 0) return

  const layoutOptions = clusterLayoutMode.value === 'force'
    ? {
        name: 'fcose',
        animate: true,
        animationDuration: 500,
        fit: true,
        padding: 40,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 150,
        nodeRepulsion: 8000,
        gravity: 0.25,
        gravityRange: 3.8
      }
    : {
        name: 'grid',
        animate: true,
        animationDuration: 300,
        fit: true,
        padding: 40,
        avoidOverlap: true,
        avoidOverlapPadding: 20
      }

  clusterCy.layout(layoutOptions as cytoscape.LayoutOptions).run()
}

function highlightClusterConnected(node: NodeSingular) {
  if (!clusterCy) return
  const neighborhood = node.neighborhood().add(node)
  clusterCy.elements().addClass('dimmed')
  neighborhood.removeClass('dimmed').addClass('highlighted')
}

function clearClusterHighlight() {
  if (!clusterCy) return
  clusterCy.elements().removeClass('dimmed').removeClass('highlighted')
}

function zoomInCluster() {
  if (!clusterCy) return
  clusterCy.zoom(clusterCy.zoom() * 1.25)
  clusterCy.center()
}

function zoomOutCluster() {
  if (!clusterCy) return
  clusterCy.zoom(clusterCy.zoom() * 0.8)
  clusterCy.center()
}

function fitClusterGraph() {
  if (!clusterCy) return
  clusterCy.fit(undefined, 40)
  clusterZoomLevel.value = clusterCy.zoom()
}

function toggleClusterLayout() {
  clusterLayoutMode.value = clusterLayoutMode.value === 'force' ? 'grid' : 'force'
  runClusterLayout()
}

function handleSearch() {
  updateCytoscapeElements()
}

function handleModuleFilter() {
  updateCytoscapeElements()
}

// ============================================================================
// List View Methods
// ============================================================================

function getEdgeSource(edge: GraphEdge): string | undefined {
  return edge.from ?? edge.source
}

function getEdgeTarget(edge: GraphEdge): string | undefined {
  return edge.to ?? edge.target
}

function getOutgoingCalls(funcId: string): GraphEdge[] {
  if (!props.data?.edges) return []
  return props.data.edges.filter(e => getEdgeSource(e) === funcId)
}

function getIncomingCalls(funcId: string): GraphEdge[] {
  if (!props.data?.edges) return []
  return props.data.edges.filter(e => getEdgeTarget(e) === funcId && (e.resolved !== false))
}

function getNodeName(nodeId: string): string {
  const node = props.data?.nodes?.find(n => n.id === nodeId)
  return node?.name || nodeId.split('.').pop() || nodeId
}

function toggleFunction(funcId: string) {
  if (expandedFuncs.value.has(funcId)) {
    expandedFuncs.value.delete(funcId)
  } else {
    expandedFuncs.value.add(funcId)
  }
  expandedFuncs.value = new Set(expandedFuncs.value)
  selectedFunc.value = funcId
  emit('select', funcId)
}

function toggleResolvedFilter(filter: 'resolved' | 'unresolved') {
  if (resolvedFilter.value === filter) {
    resolvedFilter.value = 'all'
  } else {
    resolvedFilter.value = filter
  }
  updateCytoscapeElements()
}

function truncateModule(mod: string): string {
  const parts = mod.split('.')
  if (parts.length <= 2) return mod
  return '...' + parts.slice(-2).join('.')
}

function truncateFile(filePath: string): string {
  if (!filePath) return ''
  const parts = filePath.split('/')
  if (parts.length <= 2) return filePath
  return '...' + parts.slice(-2).join('/')
}

function truncateFunc(funcId: string): string {
  const parts = funcId.split('.')
  if (parts.length <= 2) return funcId
  return parts.slice(-2).join('.')
}


// ============================================================================
// Lifecycle
// ============================================================================

onMounted(async () => {
  await nextTick()
  if (cytoscapeContainer.value && props.data?.nodes?.length) {
    initCytoscape()
    updateCytoscapeElements()
  }
})

onUnmounted(() => {
  if (cy) {
    cy.destroy()
    cy = null
  }
  if (clusterCy) {
    clusterCy.destroy()
    clusterCy = null
  }
})

// Watch for data changes
watch(() => props.data, async (newData) => {
  if (newData?.nodes?.length) {
    await nextTick()
    if (!cy && cytoscapeContainer.value) {
      initCytoscape()
    }
    updateCytoscapeElements()

    // Auto-expand top functions in list view
    const sorted = [...newData.nodes].sort((a, b) => {
      const aCount = getOutgoingCalls(a.id).length + getIncomingCalls(a.id).length
      const bCount = getOutgoingCalls(b.id).length + getIncomingCalls(b.id).length
      return bCount - aCount
    })
    sorted.slice(0, 3).forEach(node => {
      if (getOutgoingCalls(node.id).length || getIncomingCalls(node.id).length) {
        expandedFuncs.value.add(node.id)
      }
    })
  }
}, { immediate: true })

// Watch for view mode changes - init cytoscape when switching to network or cluster
watch(viewMode, async (newMode) => {
  if (newMode === 'network') {
    await nextTick()
    if (!cy && cytoscapeContainer.value) {
      initCytoscape()
      updateCytoscapeElements()
    }
  } else if (newMode === 'stats') {
    await nextTick()
    if (!clusterCy && clusterContainer.value) {
      initClusterCytoscape()
    }
    updateClusterElements()
  }
})
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */
.function-call-graph {
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

.graph-container {
  display: flex;
  flex-direction: column;
}

.graph-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.graph-search,
.module-filter {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.graph-search {
  flex: 1;
}

.module-filter {
  min-width: 180px;
}

.graph-search:focus,
.module-filter:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

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

.stats-bar {
  display: flex;
  gap: var(--spacing-xl);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.stat {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--color-primary);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
}

/* Clickable resolved/unresolved filter stats */
.stat-resolved,
.stat-unresolved {
  cursor: pointer;
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  transition: all var(--duration-200) ease;
  border: 1px solid transparent;
}

.stat-resolved:hover,
.stat-unresolved:hover {
  background: var(--color-primary-bg);
}

.stat-resolved.active {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.stat-resolved.active .stat-value {
  color: var(--color-success);
}

.stat-resolved.active .stat-label {
  color: var(--color-success-light);
}

.stat-unresolved.active {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
}

.stat-unresolved.active .stat-value {
  color: var(--color-warning);
}

.stat-unresolved.active .stat-label {
  color: var(--color-warning-light);
}

/* Network View (Cytoscape) */
.network-view {
  flex: 1;
  position: relative;
  min-height: 400px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.cytoscape-container {
  width: 100%;
  height: 100%;
  min-height: 400px;
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

/* List View */
.list-view {
  flex: 1;
  overflow-y: auto;
}

.function-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.function-item {
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.func-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  cursor: pointer;
  transition: background var(--duration-200) ease;
}

.func-header:hover {
  background: var(--color-primary-bg);
}

.function-item.expanded > .func-header {
  background: var(--color-primary-bg-hover);
}

.expand-icon {
  width: 16px;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.async-badge {
  padding: var(--spacing-px) var(--spacing-1);
  font-size: var(--text-xs);
  background: var(--chart-purple-bg);
  color: var(--chart-purple-light);
  border-radius: var(--radius-sm);
}

.class-badge {
  padding: var(--spacing-px) var(--spacing-1);
  font-size: var(--text-xs);
  background: var(--color-success-bg);
  color: var(--color-success-light);
  border-radius: var(--radius-sm);
}

.func-name {
  flex: 1;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.call-counts {
  display: flex;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
}

.call-counts .outgoing {
  color: var(--color-success);
}

.call-counts .incoming {
  color: var(--chart-purple);
}

.func-details {
  padding: var(--spacing-3);
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary-alpha);
}

.func-location {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-3);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.calls-section {
  margin-top: var(--spacing-3);
}

.section-label {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.section-label .arrow {
  color: var(--color-success);
}

.call-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
  padding-left: var(--spacing-4);
}

.call-item {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-tertiary-alpha);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
}

.call-item.resolved {
  color: var(--text-primary);
}

.call-item.unresolved {
  color: var(--text-secondary);
  border: 1px dashed var(--border-default);
}

.call-name {
  font-family: var(--font-mono);
}

.call-count {
  color: var(--chart-blue-light);
  font-size: var(--text-xs);
}

.unresolved-badge {
  font-size: 9px;
  padding: 1px var(--spacing-1);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border-radius: 3px;
}

.more-calls {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-style: italic;
}

/* Cluster View */
.cluster-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-height: 400px;
}

.graph-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--color-info-bg);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--color-info);
}

.cluster-legend {
  display: flex;
  gap: var(--spacing-lg);
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

.legend-item.caller .dot {
  background: var(--color-success);
  border: 2px solid var(--color-success-light);
}

.legend-item.called .dot {
  background: var(--chart-purple);
  border: 2px solid var(--chart-purple-light);
}

.legend-item.hub .dot {
  background: var(--color-warning);
  border: 2px solid var(--color-warning-light);
}

.cluster-container {
  flex: 1;
  min-height: 350px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.cluster-controls {
  position: absolute;
  bottom: var(--spacing-3);
  right: var(--spacing-3);
}

.control-separator {
  color: var(--border-default);
  font-size: var(--text-sm);
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
  padding: var(--spacing-3) var(--spacing-3);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
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

.detail-value.class-value {
  color: var(--color-success-light);
}

.detail-value.calls-out {
  color: var(--color-success);
}

.detail-value.calls-in {
  color: var(--chart-purple);
}

/* Fullscreen mode */
.function-call-graph.fullscreen {
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

.function-call-graph.fullscreen .graph-container {
  height: calc(100vh - 100px) !important;
}

.function-call-graph.fullscreen .network-view,
.function-call-graph.fullscreen .cluster-view {
  min-height: calc(100vh - 220px);
}

.function-call-graph.fullscreen .cytoscape-container,
.function-call-graph.fullscreen .cluster-container {
  min-height: calc(100vh - 260px);
}

/* Orphaned Functions View */
.orphaned-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.graph-info.warning {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
  color: var(--color-warning, #f59e0b);
}

.orphaned-controls {
  display: flex;
  gap: var(--spacing-3);
}

.orphaned-search,
.orphaned-module-filter {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-sm);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
}

.orphaned-search:focus,
.orphaned-module-filter:focus {
  outline: none;
  border-color: var(--color-primary);
}

.orphaned-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  max-height: 500px;
  overflow-y: auto;
}

.orphaned-item {
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s ease;
}

.orphaned-item:hover {
  background: var(--bg-hover);
  border-color: var(--color-warning);
}

.orphaned-item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.orphaned-item-header .func-name {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.orphaned-item-header .async-badge {
  padding: 2px 6px;
  font-size: var(--text-xs);
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-sm);
}

.orphaned-item-header .class-badge {
  padding: 2px 6px;
  font-size: var(--text-xs);
  background: var(--color-secondary-bg, rgba(139, 92, 246, 0.1));
  color: var(--color-secondary, #8b5cf6);
  border-radius: var(--radius-sm);
}

.orphaned-item-details {
  display: flex;
  gap: var(--spacing-lg);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.orphaned-item-details i {
  margin-right: var(--spacing-1);
  opacity: 0.7;
}

.show-more {
  padding: var(--spacing-3);
  text-align: center;
}

.btn-show-more {
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-show-more:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.orphaned-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  text-align: center;
  color: var(--text-muted);
}

.orphaned-empty i {
  font-size: 2rem;
  margin-bottom: var(--spacing-3);
  color: var(--color-success);
}

/* Orphaned stat styling */
.stat-orphaned {
  cursor: pointer;
  transition: all 0.15s ease;
}

.stat-orphaned:hover,
.stat-orphaned.active {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
}

.stat-orphaned .stat-value {
  color: var(--color-warning, #f59e0b);
}

/* Issue #711: Virtual scroll container for orphaned functions */
.orphaned-list-container {
  height: 500px;
  overflow-y: auto;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-tertiary);
}

.virtual-scroll-info {
  position: sticky;
  bottom: 0;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-default);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-align: center;
}
</style>
