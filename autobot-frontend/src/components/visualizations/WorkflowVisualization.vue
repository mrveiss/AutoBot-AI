<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  WorkflowVisualization.vue - Interactive workflow execution flowchart
  Displays workflow steps, status, and execution flow
  Issue #62: Enhanced Visualizations
  Issue #704: Migrated to CSS design tokens
-->
<template>
  <div class="workflow-visualization">
    <div class="workflow-header">
      <div class="header-info">
        <h3>{{ workflow?.name || t('visualizations.workflowViz.defaultTitle') }}</h3>
        <span class="workflow-id" v-if="workflow?.id">ID: {{ workflow.id }}</span>
      </div>
      <div class="header-actions">
        <div class="status-badge" :class="workflowStatus">
          <Icon :name="statusIcon" />
          {{ statusText }}
        </div>
        <button @click="toggleLayout" class="layout-btn" :title="t('visualizations.workflowViz.toggleLayout')">
          <i :class="layoutMode === 'horizontal' ? 'arrows-alt-v' : 'arrows-alt-h'"></i>
        </button>
        <button @click="fitToView" class="fit-btn" :title="t('visualizations.workflowViz.fitToView')">
          <Icon name="expand" />
        </button>
      </div>
    </div>

    <div class="workflow-container" ref="containerRef">
      <svg
        ref="svgRef"
        class="workflow-svg"
        :viewBox="viewBox"
        @mousedown="startPan"
        @mousemove="handlePan"
        @mouseup="endPan"
        @mouseleave="endPan"
        @wheel.prevent="handleZoom"
      >
        <defs>
          <!-- Arrow markers -->
          <marker
            id="arrow-default"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" :fill="getCssVar('--text-tertiary', '#64748b')" />
          </marker>
          <marker
            id="arrow-active"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" :fill="getCssVar('--chart-blue', '#3b82f6')" />
          </marker>
          <marker
            id="arrow-success"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" :fill="getCssVar('--color-success', '#10b981')" />
          </marker>
          <marker
            id="arrow-error"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" :fill="getCssVar('--color-error', '#ef4444')" />
          </marker>

          <!-- Glow filters -->
          <filter id="glow-active" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feFlood :flood-color="getCssVar('--chart-blue', '#3b82f6')" flood-opacity="0.5" />
            <feComposite in2="blur" operator="in" />
            <feMerge>
              <feMergeNode />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g :transform="`translate(${panOffset.x}, ${panOffset.y}) scale(${zoomLevel})`">
          <!-- Connections -->
          <g class="connections">
            <path
              v-for="(connection, idx) in connections"
              :key="`conn-${idx}`"
              :d="getConnectionPath(connection as any)"
              class="connection-line"
              :class="connection.status"
              :marker-end="`url(#arrow-${connection.status || 'default'})`"
            />
          </g>

          <!-- Nodes -->
          <g class="nodes">
            <g
              v-for="node in nodes"
              :key="node.id"
              class="workflow-node"
              :class="[node.type, node.status, { selected: selectedNode?.id === node.id }]"
              :transform="`translate(${node.x}, ${node.y})`"
              @click="selectNode(node)"
            >
              <!-- Node shape based on type -->
              <rect
                v-if="node.type === 'action' || node.type === 'task'"
                :x="-nodeWidth / 2"
                :y="-nodeHeight / 2"
                :width="nodeWidth"
                :height="nodeHeight"
                rx="8"
                class="node-bg"
              />
              <circle
                v-else-if="node.type === 'start'"
                r="24"
                class="node-bg"
              />
              <circle
                v-else-if="node.type === 'end'"
                r="24"
                class="node-bg"
              />
              <polygon
                v-else-if="node.type === 'decision'"
                :points="diamondPoints"
                class="node-bg"
              />
              <rect
                v-else
                :x="-nodeWidth / 2"
                :y="-nodeHeight / 2"
                :width="nodeWidth"
                :height="nodeHeight"
                rx="8"
                class="node-bg"
              />

              <!-- Node icon -->
              <text class="node-icon" dy="0.35em" text-anchor="middle">
                {{ getNodeIcon(node) }}
              </text>

              <!-- Node label -->
              <text
                class="node-label"
                :y="node.type === 'decision' ? 45 : nodeHeight / 2 + 18"
                text-anchor="middle"
              >
                {{ truncate(node.name, 18) }}
              </text>

              <!-- Status indicator -->
              <circle
                v-if="node.status"
                :cx="nodeWidth / 2 - 8"
                :cy="-nodeHeight / 2 + 8"
                r="6"
                class="status-indicator"
                :class="node.status"
              />

              <!-- Duration badge -->
              <text
                v-if="node.duration && node.status === 'completed'"
                class="duration-badge"
                :y="nodeHeight / 2 + 35"
                text-anchor="middle"
              >
                {{ formatDuration(node.duration) }}
              </text>
            </g>
          </g>
        </g>
      </svg>

      <!-- Zoom controls -->
      <div class="zoom-controls">
        <button @click="zoomIn" :title="t('visualizations.workflowViz.zoomIn')">
          <Icon name="plus" />
        </button>
        <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
        <button @click="zoomOut" :title="t('visualizations.workflowViz.zoomOut')">
          <Icon name="minus" />
        </button>
      </div>

      <!-- Mini progress -->
      <div class="progress-bar" v-if="workflow">
        <div
          class="progress-fill"
          :style="{ width: `${progressPercent}%` }"
        ></div>
        <span class="progress-text">{{ t('visualizations.workflowViz.stepsProgress', { completed: completedSteps, total: totalSteps }) }}</span>
      </div>
    </div>

    <!-- Node details panel -->
    <Transition name="slide">
      <div v-if="selectedNode" class="node-details">
        <div class="details-header">
          <div class="details-icon" :class="selectedNode.status">
            {{ getNodeIcon(selectedNode) }}
          </div>
          <div class="details-title">
            <h4>{{ selectedNode.name }}</h4>
            <span class="node-type">{{ formatNodeType(selectedNode.type) }}</span>
          </div>
          <button @click="selectedNode = null" class="close-btn">
            <Icon name="times" />
          </button>
        </div>

        <div class="details-content">
          <div class="detail-row">
            <span class="label">{{ t('visualizations.workflowViz.statusLabel') }}</span>
            <span class="value status-badge" :class="selectedNode.status">
              {{ formatStatus(selectedNode.status) }}
            </span>
          </div>
          <div class="detail-row" v-if="selectedNode.duration">
            <span class="label">{{ t('visualizations.workflowViz.duration') }}</span>
            <span class="value">{{ formatDuration(selectedNode.duration) }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.startTime">
            <span class="label">{{ t('visualizations.workflowViz.started') }}</span>
            <span class="value">{{ formatTime(selectedNode.startTime) }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.endTime">
            <span class="label">{{ t('visualizations.workflowViz.ended') }}</span>
            <span class="value">{{ formatTime(selectedNode.endTime) }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.error">
            <span class="label">{{ t('visualizations.workflowViz.errorLabel') }}</span>
            <span class="value error">{{ selectedNode.error }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.output">
            <span class="label">{{ t('visualizations.workflowViz.outputLabel') }}</span>
            <pre class="output">{{ selectedNode.output }}</pre>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { getCssVar } from '@/composables/useCssVars'

const { t } = useI18n()

const logger = createLogger('WorkflowVisualization')

// Types
interface WorkflowNode {
  id: string
  name: string
  type: 'start' | 'end' | 'action' | 'task' | 'decision' | 'parallel'
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  x: number
  y: number
  duration?: number
  startTime?: number
  endTime?: number
  error?: string
  output?: string
}

interface Connection {
  from: string
  to: string
  status?: 'default' | 'active' | 'success' | 'error'
  label?: string
}

interface Workflow {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  nodes: WorkflowNode[]
  connections: Connection[]
}

// Props
interface Props {
  workflow?: Workflow
  layoutMode?: 'horizontal' | 'vertical'
}

const props = withDefaults(defineProps<Props>(), {
  layoutMode: 'horizontal'
})

// Emit
const emit = defineEmits<{
  (e: 'node-click', node: WorkflowNode): void
  (e: 'layout-change', mode: 'horizontal' | 'vertical'): void
}>()

// State
const containerRef = ref<HTMLElement | null>(null)
const svgRef = ref<SVGElement | null>(null)
const selectedNode = ref<WorkflowNode | null>(null)
const layoutMode = ref(props.layoutMode)
const zoomLevel = ref(1)
const panOffset = ref({ x: 50, y: 50 })
const isPanning = ref(false)
const lastPanPoint = ref({ x: 0, y: 0 })

// Constants
const nodeWidth = 140
const nodeHeight = 60
const nodeSpacingX = 180
const nodeSpacingY = 100

// Computed
const nodes = computed(() => {
  if (!props.workflow?.nodes) {
    return getSampleNodes()
  }
  return calculateNodePositions(props.workflow.nodes)
})

const connections = computed(() => {
  if (!props.workflow?.connections) {
    return getSampleConnections()
  }
  return props.workflow.connections.map(conn => ({
    ...conn,
    status: getConnectionStatus(conn)
  }))
})

const viewBox = computed(() => {
  const width = Math.max(800, nodes.value.length * nodeSpacingX + 200)
  const height = Math.max(400, Math.ceil(nodes.value.length / 4) * nodeSpacingY + 200)
  return `0 0 ${width} ${height}`
})

const diamondPoints = computed(() => {
  const size = 35
  return `0,-${size} ${size},0 0,${size} -${size},0`
})

const workflowStatus = computed(() => props.workflow?.status || 'pending')

const statusIcon = computed(() => {
  switch (workflowStatus.value) {
    case 'running': return 'spinner'
    case 'completed': return 'check-circle'
    case 'failed': return 'times-circle'
    default: return 'clock'
  }
})

const statusText = computed(() => {
  switch (workflowStatus.value) {
    case 'running': return t('visualizations.workflowViz.running')
    case 'completed': return t('visualizations.workflowViz.completed')
    case 'failed': return t('visualizations.workflowViz.failed')
    default: return t('visualizations.workflowViz.pending')
  }
})

const completedSteps = computed(() => {
  return nodes.value.filter(n => n.status === 'completed').length
})

const totalSteps = computed(() => {
  return nodes.value.filter(n => n.type !== 'start' && n.type !== 'end').length
})

const progressPercent = computed(() => {
  if (totalSteps.value === 0) return 0
  return Math.round((completedSteps.value / totalSteps.value) * 100)
})

// Methods
function calculateNodePositions(inputNodes: WorkflowNode[]): WorkflowNode[] {
  return inputNodes.map((node, idx) => {
    if (node.x !== undefined && node.y !== undefined) {
      return node
    }

    // Auto-layout
    const col = idx % 4
    const row = Math.floor(idx / 4)

    return {
      ...node,
      x: layoutMode.value === 'horizontal' ? col * nodeSpacingX + 100 : row * nodeSpacingY + 100,
      y: layoutMode.value === 'horizontal' ? row * nodeSpacingY + 80 : col * nodeSpacingX + 80
    }
  })
}

function getSampleNodes(): WorkflowNode[] {
  return [
    { id: 'start', name: 'Start', type: 'start', status: 'completed', x: 100, y: 150 },
    { id: 'init', name: 'Initialize', type: 'action', status: 'completed', x: 280, y: 150, duration: 1200 },
    { id: 'check', name: 'Validate Input', type: 'decision', status: 'completed', x: 460, y: 150, duration: 450 },
    { id: 'process', name: 'Process Data', type: 'task', status: 'running', x: 640, y: 80 },
    { id: 'error_handle', name: 'Handle Error', type: 'action', status: 'pending', x: 640, y: 220 },
    { id: 'finalize', name: 'Finalize', type: 'action', status: 'pending', x: 820, y: 150 },
    { id: 'end', name: 'End', type: 'end', status: 'pending', x: 1000, y: 150 }
  ]
}

function getSampleConnections(): Connection[] {
  return [
    { from: 'start', to: 'init', status: 'success' },
    { from: 'init', to: 'check', status: 'success' },
    { from: 'check', to: 'process', status: 'active', label: 'valid' },
    { from: 'check', to: 'error_handle', label: 'invalid' },
    { from: 'process', to: 'finalize' },
    { from: 'error_handle', to: 'finalize' },
    { from: 'finalize', to: 'end' }
  ]
}

function getConnectionStatus(conn: Connection): string {
  const fromNode = nodes.value.find(n => n.id === conn.from)
  const toNode = nodes.value.find(n => n.id === conn.to)

  if (toNode?.status === 'running') return 'active'
  if (toNode?.status === 'completed') return 'success'
  if (toNode?.status === 'failed') return 'error'
  if (fromNode?.status === 'completed') return 'success'

  return 'default'
}

function getConnectionPath(conn: Connection): string {
  const fromNode = nodes.value.find(n => n.id === conn.from)
  const toNode = nodes.value.find(n => n.id === conn.to)

  if (!fromNode || !toNode) return ''

  const fromX = fromNode.x + (fromNode.type === 'decision' ? 35 : nodeWidth / 2)
  const fromY = fromNode.y
  const toX = toNode.x - (toNode.type === 'decision' ? 35 : nodeWidth / 2)
  const toY = toNode.y

  // Calculate control points for curved path
  const midX = (fromX + toX) / 2

  if (Math.abs(toY - fromY) < 10) {
    // Straight horizontal line
    return `M ${fromX} ${fromY} L ${toX} ${toY}`
  }

  // Curved path
  return `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`
}

function getNodeIcon(node: WorkflowNode): string {
  switch (node.type) {
    case 'start': return '\u25B6'
    case 'end': return '\u23F9'
    case 'decision': return '\u25C7'
    case 'parallel': return '\u2AEC'
    case 'task': return '\uD83D\uDCCB'
    default: return '\u2699'
  }
}

function formatNodeType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1)
}

function formatStatus(status?: string): string {
  if (!status) return t('visualizations.workflowViz.unknown')
  const statusMap: Record<string, string> = {
    pending: t('visualizations.workflowViz.pending'),
    running: t('visualizations.workflowViz.running'),
    completed: t('visualizations.workflowViz.completed'),
    failed: t('visualizations.workflowViz.failed')
  }
  return statusMap[status] || status.charAt(0).toUpperCase() + status.slice(1)
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 60000)}m`
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString()
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 1) + '\u2026'
}

function selectNode(node: WorkflowNode) {
  selectedNode.value = selectedNode.value?.id === node.id ? null : node
  emit('node-click', node)
}

function toggleLayout() {
  layoutMode.value = layoutMode.value === 'horizontal' ? 'vertical' : 'horizontal'
  emit('layout-change', layoutMode.value)
}

function fitToView() {
  zoomLevel.value = 1
  panOffset.value = { x: 50, y: 50 }
}

// Pan & Zoom
function startPan(event: MouseEvent) {
  if (event.button !== 0) return
  isPanning.value = true
  lastPanPoint.value = { x: event.clientX, y: event.clientY }
}

function handlePan(event: MouseEvent) {
  if (!isPanning.value) return

  const dx = event.clientX - lastPanPoint.value.x
  const dy = event.clientY - lastPanPoint.value.y

  panOffset.value = {
    x: panOffset.value.x + dx,
    y: panOffset.value.y + dy
  }

  lastPanPoint.value = { x: event.clientX, y: event.clientY }
}

function endPan() {
  isPanning.value = false
}

function handleZoom(event: WheelEvent) {
  const delta = event.deltaY > 0 ? -0.1 : 0.1
  zoomLevel.value = Math.max(0.3, Math.min(2, zoomLevel.value + delta))
}

function zoomIn() {
  zoomLevel.value = Math.min(2, zoomLevel.value + 0.2)
}

function zoomOut() {
  zoomLevel.value = Math.max(0.3, zoomLevel.value - 0.2)
}

// Watch for prop changes
watch(() => props.layoutMode, (newMode) => {
  layoutMode.value = newMode
})

// Expose
defineExpose({
  fitToView,
  selectNode
})
</script>

<style scoped>
/**
 * Issue #704: Migrated to CSS design tokens
 * All hardcoded colors replaced with var(--token-name) references
 */

.workflow-visualization {
  background: var(--bg-secondary-alpha);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  border: 1px solid var(--border-subtle);
  position: relative;
}

.workflow-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid var(--border-subtle);
}

.header-info h3 {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.workflow-id {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
}

.status-badge.pending {
  background: var(--color-secondary-bg, rgba(100, 116, 139, 0.2));
  color: var(--text-secondary);
}

.status-badge.running {
  background: var(--color-info-bg);
  color: var(--color-info-light);
}

.status-badge.completed {
  background: var(--color-success-bg);
  color: var(--color-success-light);
}

.status-badge.failed {
  background: var(--color-error-bg);
  color: var(--color-error-light);
}

.layout-btn,
.fit-btn {
  padding: var(--spacing-2) var(--spacing-2-5);
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.layout-btn:hover,
.fit-btn:hover {
  background: var(--color-info-bg);
  border-color: var(--chart-blue);
  color: var(--chart-blue);
}

.workflow-container {
  position: relative;
  background: rgba(15, 23, 42, 0.5);
  border-radius: var(--radius-lg);
  overflow: hidden;
  min-height: 400px;
}

.workflow-svg {
  width: 100%;
  height: 400px;
  cursor: grab;
}

.workflow-svg:active {
  cursor: grabbing;
}

/* Connections */
.connection-line {
  fill: none;
  stroke: var(--text-muted);
  stroke-width: 2;
  transition: stroke var(--duration-300);
}

.connection-line.active {
  stroke: var(--chart-blue);
  stroke-width: 3;
  animation: pulse 1.5s infinite;
}

.connection-line.success {
  stroke: var(--color-success);
}

.connection-line.error {
  stroke: var(--color-error);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Nodes */
.workflow-node {
  cursor: pointer;
}

.workflow-node .node-bg {
  fill: var(--bg-secondary);
  stroke: var(--text-muted);
  stroke-width: 2;
  transition: all var(--duration-200);
}

.workflow-node:hover .node-bg {
  stroke: var(--chart-blue);
}

.workflow-node.selected .node-bg {
  stroke: var(--chart-blue);
  stroke-width: 3;
}

.workflow-node.running .node-bg {
  stroke: var(--chart-blue);
  filter: url(#glow-active);
}

.workflow-node.completed .node-bg {
  stroke: var(--color-success);
}

.workflow-node.failed .node-bg {
  stroke: var(--color-error);
}

.workflow-node.start .node-bg,
.workflow-node.end .node-bg {
  fill: var(--bg-tertiary);
}

.node-icon {
  font-size: var(--text-lg);
  fill: var(--text-primary);
}

.node-label {
  font-size: var(--text-xs);
  fill: var(--text-secondary);
  font-weight: 500;
}

.status-indicator {
  stroke: var(--bg-primary);
  stroke-width: 2;
}

.status-indicator.pending {
  fill: var(--text-tertiary);
}

.status-indicator.running {
  fill: var(--chart-blue);
  animation: blink 1s infinite;
}

.status-indicator.completed {
  fill: var(--color-success);
}

.status-indicator.failed {
  fill: var(--color-error);
}

.status-indicator.skipped {
  fill: var(--text-secondary);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.duration-badge {
  font-size: var(--text-xs);
  fill: var(--text-tertiary);
}

/* Zoom controls */
.zoom-controls {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  background: rgba(30, 41, 59, 0.9);
  padding: var(--spacing-2);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.zoom-controls button {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  background: transparent;
  border-radius: var(--radius-default);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-200);
}

.zoom-controls button:hover {
  background: var(--color-info-bg);
  color: var(--chart-blue);
}

.zoom-level {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  min-width: 40px;
  text-align: center;
}

/* Progress bar */
.progress-bar {
  position: absolute;
  bottom: 16px;
  left: 16px;
  width: 200px;
  height: 24px;
  background: rgba(30, 41, 59, 0.9);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-subtle);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--chart-blue);
  transition: width var(--duration-300) var(--ease-out);
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: var(--text-xs);
  color: var(--text-primary);
  font-weight: 500;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

/* Node details panel */
.node-details {
  position: absolute;
  top: 80px;
  right: 20px;
  width: 280px;
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.details-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-tertiary-alpha);
  border-bottom: 1px solid var(--border-subtle);
}

.details-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-lg);
  background: var(--color-info-bg);
}

.details-icon.running {
  background: var(--color-info-bg);
}

.details-icon.completed {
  background: var(--color-success-bg);
}

.details-icon.failed {
  background: var(--color-error-bg);
}

.details-title {
  flex: 1;
}

.details-title h4 {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.node-type {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.close-btn {
  padding: var(--spacing-1-5);
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-default);
  transition: all var(--duration-200);
}

.close-btn:hover {
  background: var(--color-error-bg);
  color: var(--color-error-light);
}

.details-content {
  padding: var(--spacing-4);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: var(--spacing-2) var(--spacing-0);
  border-bottom: 1px solid rgba(71, 85, 105, 0.3);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-row .label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.detail-row .value {
  font-size: var(--text-xs);
  color: var(--text-primary);
  font-weight: 500;
}

.detail-row .value.error {
  color: var(--color-error-light);
}

.detail-row .output {
  font-size: var(--text-xs);
  background: rgba(15, 23, 42, 0.5);
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  margin-top: var(--spacing-1);
  overflow-x: auto;
  max-width: 200px;
}

/* Transitions */
.slide-enter-active,
.slide-leave-active {
  transition: all var(--duration-300) var(--ease-out);
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

/* Responsive */
@media (max-width: 768px) {
  .workflow-header {
    flex-direction: column;
    gap: var(--spacing-3);
    align-items: stretch;
  }

  .header-actions {
    justify-content: space-between;
  }

  .node-details {
    position: fixed;
    top: auto;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    border-radius: var(--radius-xl) 12px 0 0;
    max-height: 50vh;
    overflow-y: auto;
  }
}
</style>
