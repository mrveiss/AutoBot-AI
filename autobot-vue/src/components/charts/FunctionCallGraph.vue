<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  FunctionCallGraph.vue - Interactive function call graph visualization
-->
<template>
  <div class="function-call-graph" :class="{ 'chart-loading': loading }">
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
        />
        <select v-model="filterModule" class="module-filter">
          <option value="">All Modules</option>
          <option v-for="mod in uniqueModules" :key="mod" :value="mod">
            {{ truncateModule(mod || '') }}
          </option>
        </select>
        <div class="view-toggle">
          <button
            :class="{ active: viewMode === 'list' }"
            @click="viewMode = 'list'"
            title="List View"
          >
            <i class="fas fa-list"></i>
          </button>
          <button
            :class="{ active: viewMode === 'graph' }"
            @click="viewMode = 'graph'"
            title="Graph View"
          >
            <i class="fas fa-project-diagram"></i>
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

      <!-- Graph view (simplified network representation) -->
      <div v-else class="graph-view">
        <div class="graph-info">
          <i class="fas fa-info-circle"></i>
          <span>Graph view shows top callers and most called functions</span>
        </div>

        <!-- Top Callers -->
        <div class="graph-section">
          <h4><i class="fas fa-arrow-right"></i> Top Callers</h4>
          <div class="bar-chart">
            <div
              v-for="item in summary?.top_callers || []"
              :key="item.function"
              class="bar-item"
            >
              <div class="bar-label" :title="item.function">
                {{ truncateFunc(item.function) }}
              </div>
              <div class="bar-container">
                <div
                  class="bar-fill caller"
                  :style="{ width: getBarWidth(item.calls, maxOutgoing) + '%' }"
                ></div>
                <span class="bar-value">{{ item.calls }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Most Called -->
        <div class="graph-section">
          <h4><i class="fas fa-arrow-left"></i> Most Called</h4>
          <div class="bar-chart">
            <div
              v-for="item in summary?.most_called || []"
              :key="item.function"
              class="bar-item"
            >
              <div class="bar-label" :title="item.function">
                {{ truncateFunc(item.function) }}
              </div>
              <div class="bar-container">
                <div
                  class="bar-fill called"
                  :style="{ width: getBarWidth(item.calls, maxIncoming) + '%' }"
                ></div>
                <span class="bar-value">{{ item.calls }}</span>
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
const viewMode = ref<'list' | 'graph'>('list')
const expandedFuncs = ref<Set<string>>(new Set())
const selectedFunc = ref<string | null>(null)

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
        // Show functions that have at least one resolved outgoing call
        return outgoingCalls.some(e => e.resolved)
      } else {
        // Show functions that have at least one unresolved outgoing call
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

const maxOutgoing = computed(() => {
  if (!props.summary?.top_callers?.length) return 1
  return Math.max(...props.summary.top_callers.map(c => c.calls))
})

const maxIncoming = computed(() => {
  if (!props.summary?.most_called?.length) return 1
  return Math.max(...props.summary.most_called.map(c => c.calls))
})

// Methods

// Helper to get edge source - supports both 'from' and 'source' formats
function getEdgeSource(edge: GraphEdge): string | undefined {
  return edge.from ?? edge.source
}

// Helper to get edge target - supports both 'to' and 'target' formats
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

function getBarWidth(value: number, max: number): number {
  return Math.max(5, (value / max) * 100)
}

// Auto-expand top functions
watch(() => props.data, (newData) => {
  if (newData?.nodes?.length) {
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

/* Graph View */
.graph-view {
  flex: 1;
  overflow-y: auto;
}

.graph-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #60a5fa;
}

.graph-section {
  margin-bottom: 24px;
}

.graph-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: var(--color-text-primary, #e2e8f0);
  display: flex;
  align-items: center;
  gap: 8px;
}

.graph-section h4 i {
  color: #60a5fa;
}

.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bar-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bar-label {
  width: 200px;
  font-size: 12px;
  font-family: 'Fira Code', 'Monaco', monospace;
  color: var(--color-text-secondary, #94a3b8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bar-container {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.bar-fill {
  height: 20px;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.bar-fill.caller {
  background: linear-gradient(90deg, #10b981, #34d399);
}

.bar-fill.called {
  background: linear-gradient(90deg, #8b5cf6, #a78bfa);
}

.bar-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary, #e2e8f0);
  min-width: 30px;
}
</style>
