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
  total_call_relationships: number
  resolved_calls: number
  unresolved_calls: number
  top_callers: { function: string; calls: number }[]
  most_called: { function: string; calls: number }[]
}

interface Props {
  data: CallGraphData
  summary?: SummaryData
  title?: string
  subtitle?: string
  height?: number | string
  loading?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Function Call Graph',
  subtitle: 'View function call relationships',
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
const viewMode = ref<'network' | 'list' | 'stats'>('network') // Default to network view
const expandedFuncs = ref<Set<string>>(new Set())
const selectedFunc = ref<string | null>(null)
const zoomLevel = ref(1)
const layoutMode = ref<'force' | 'grid'>('force')

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
        'border-color': '#334155',
        'text-max-width': '80px',
        'text-wrap': 'ellipsis'
      }
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 3,
        'border-color': '#3b82f6'
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 3,
        'border-color': '#10b981'
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
        'line-color': '#10b981',
        'target-arrow-color': '#10b981'
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

    // Color based on call ratio
    let color = '#6b7280' // Default gray
    if (outgoing > incoming) {
      color = '#10b981' // Green for callers
    } else if (incoming > outgoing) {
      color = '#8b5cf6' // Purple for called
    } else if (totalCalls > 0) {
      color = '#3b82f6' // Blue for balanced
    }

    // Async functions get special color
    if (node.is_async) {
      color = '#f59e0b'
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
        const edgeColor = edge.resolved === false ? '#fb923c' : '#64748b'
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
        'color': '#e2e8f0',
        'text-outline-color': '#1e293b',
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
        'border-color': '#ffffff'
      }
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 4,
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
        'width': 4,
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

    // Color based on type
    let color: string
    let borderColor: string
    if (isHub) {
      color = '#f59e0b' // Amber for hubs (both caller and called)
      borderColor = '#fbbf24'
    } else if (isCaller) {
      color = '#10b981' // Green for callers
      borderColor = '#34d399'
    } else {
      color = '#8b5cf6' // Purple for called
      borderColor = '#a78bfa'
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
        const edgeColor = edge.resolved === false ? '#fb923c' : '#64748b'

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
.function-call-graph {
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

.graph-container {
  display: flex;
  flex-direction: column;
}

.graph-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.graph-search,
.module-filter {
  padding: 8px 12px;
  background: var(--color-bg-tertiary, #0f172a);
  border: 1px solid var(--color-border, #334155);
  border-radius: 6px;
  color: var(--color-text-primary, #e2e8f0);
  font-size: 13px;
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
  border-color: var(--color-primary, #3b82f6);
}

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

.stats-bar {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 8px;
}

.stat {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-primary, #3b82f6);
}

.stat-label {
  font-size: 11px;
  color: var(--color-text-tertiary, #64748b);
  text-transform: uppercase;
}

/* Clickable resolved/unresolved filter stats */
.stat-resolved,
.stat-unresolved {
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 6px;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.stat-resolved:hover,
.stat-unresolved:hover {
  background: rgba(59, 130, 246, 0.1);
}

.stat-resolved.active {
  background: rgba(16, 185, 129, 0.15);
  border-color: rgba(16, 185, 129, 0.3);
}

.stat-resolved.active .stat-value {
  color: #10b981;
}

.stat-resolved.active .stat-label {
  color: #34d399;
}

.stat-unresolved.active {
  background: rgba(251, 146, 60, 0.15);
  border-color: rgba(251, 146, 60, 0.3);
}

.stat-unresolved.active .stat-value {
  color: #fb923c;
}

.stat-unresolved.active .stat-label {
  color: #fdba74;
}

/* Network View (Cytoscape) */
.network-view {
  flex: 1;
  position: relative;
  min-height: 400px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 8px;
  overflow: hidden;
}

.cytoscape-container {
  width: 100%;
  height: 100%;
  min-height: 400px;
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

/* List View */
.list-view {
  flex: 1;
  overflow-y: auto;
}

.function-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.function-item {
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 8px;
  overflow: hidden;
}

.func-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.func-header:hover {
  background: rgba(59, 130, 246, 0.1);
}

.function-item.expanded > .func-header {
  background: rgba(59, 130, 246, 0.15);
}

.expand-icon {
  width: 16px;
  font-size: 10px;
  color: var(--color-text-tertiary, #64748b);
}

.async-badge {
  padding: 2px 6px;
  font-size: 10px;
  background: rgba(139, 92, 246, 0.2);
  color: #a78bfa;
  border-radius: 4px;
}

.class-badge {
  padding: 2px 6px;
  font-size: 10px;
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
  border-radius: 4px;
}

.func-name {
  flex: 1;
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 13px;
  color: var(--color-text-primary, #e2e8f0);
}

.call-counts {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.call-counts .outgoing {
  color: #10b981;
}

.call-counts .incoming {
  color: #8b5cf6;
}

.func-details {
  padding: 12px;
  border-top: 1px solid var(--color-border, #334155);
  background: rgba(30, 41, 59, 0.5);
}

.func-location {
  font-size: 12px;
  color: var(--color-text-secondary, #94a3b8);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.calls-section {
  margin-top: 12px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary, #94a3b8);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-label .arrow {
  color: #10b981;
}

.call-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-left: 16px;
}

.call-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: rgba(51, 65, 85, 0.5);
  border-radius: 4px;
  font-size: 12px;
}

.call-item.resolved {
  color: #e2e8f0;
}

.call-item.unresolved {
  color: #94a3b8;
  border: 1px dashed #475569;
}

.call-name {
  font-family: 'Fira Code', 'Monaco', monospace;
}

.call-count {
  color: #60a5fa;
  font-size: 10px;
}

.unresolved-badge {
  font-size: 9px;
  padding: 1px 4px;
  background: rgba(251, 146, 60, 0.2);
  color: #fb923c;
  border-radius: 3px;
}

.more-calls {
  font-size: 11px;
  color: var(--color-text-tertiary, #64748b);
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
  gap: 8px;
  padding: 12px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #60a5fa;
}

.cluster-legend {
  display: flex;
  gap: 20px;
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

.legend-item.caller .dot {
  background: #10b981;
  border: 2px solid #34d399;
}

.legend-item.called .dot {
  background: #8b5cf6;
  border: 2px solid #a78bfa;
}

.legend-item.hub .dot {
  background: #f59e0b;
  border: 2px solid #fbbf24;
}

.cluster-container {
  flex: 1;
  min-height: 350px;
  background: var(--color-bg-tertiary, #0f172a);
  border-radius: 8px;
  overflow: hidden;
}

.cluster-controls {
  position: absolute;
  bottom: 12px;
  right: 12px;
}

.control-separator {
  color: var(--color-border, #334155);
  font-size: 14px;
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

.detail-value.class-value {
  color: #34d399;
}

.detail-value.calls-out {
  color: #10b981;
}

.detail-value.calls-in {
  color: #8b5cf6;
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
  z-index: 9999 !important;
  border-radius: 0 !important;
  margin: 0 !important;
  padding: 16px !important;
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
</style>
