<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  WorkflowVisualization.vue - Interactive workflow execution flowchart
  Displays workflow steps, status, and execution flow
  Issue #62: Enhanced Visualizations
-->
<template>
  <div class="workflow-visualization">
    <div class="workflow-header">
      <div class="header-info">
        <h3>{{ workflow?.name || 'Workflow Execution' }}</h3>
        <span class="workflow-id" v-if="workflow?.id">ID: {{ workflow.id }}</span>
      </div>
      <div class="header-actions">
        <div class="status-badge" :class="workflowStatus">
          <i :class="statusIcon"></i>
          {{ statusText }}
        </div>
        <button @click="toggleLayout" class="layout-btn" title="Toggle layout">
          <i :class="layoutMode === 'horizontal' ? 'fas fa-arrows-alt-v' : 'fas fa-arrows-alt-h'"></i>
        </button>
        <button @click="fitToView" class="fit-btn" title="Fit to view">
          <i class="fas fa-expand"></i>
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
            <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
          </marker>
          <marker
            id="arrow-active"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#3b82f6" />
          </marker>
          <marker
            id="arrow-success"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#10b981" />
          </marker>
          <marker
            id="arrow-error"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#ef4444" />
          </marker>

          <!-- Glow filters -->
          <filter id="glow-active" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feFlood flood-color="#3b82f6" flood-opacity="0.5" />
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
        <button @click="zoomIn" title="Zoom in">
          <i class="fas fa-plus"></i>
        </button>
        <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
        <button @click="zoomOut" title="Zoom out">
          <i class="fas fa-minus"></i>
        </button>
      </div>

      <!-- Mini progress -->
      <div class="progress-bar" v-if="workflow">
        <div
          class="progress-fill"
          :style="{ width: `${progressPercent}%` }"
        ></div>
        <span class="progress-text">{{ completedSteps }}/{{ totalSteps }} steps</span>
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
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="details-content">
          <div class="detail-row">
            <span class="label">Status:</span>
            <span class="value status-badge" :class="selectedNode.status">
              {{ formatStatus(selectedNode.status) }}
            </span>
          </div>
          <div class="detail-row" v-if="selectedNode.duration">
            <span class="label">Duration:</span>
            <span class="value">{{ formatDuration(selectedNode.duration) }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.startTime">
            <span class="label">Started:</span>
            <span class="value">{{ formatTime(selectedNode.startTime) }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.endTime">
            <span class="label">Ended:</span>
            <span class="value">{{ formatTime(selectedNode.endTime) }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.error">
            <span class="label">Error:</span>
            <span class="value error">{{ selectedNode.error }}</span>
          </div>
          <div class="detail-row" v-if="selectedNode.output">
            <span class="label">Output:</span>
            <pre class="output">{{ selectedNode.output }}</pre>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { createLogger } from '@/utils/debugUtils'

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
    case 'running': return 'fas fa-spinner fa-spin'
    case 'completed': return 'fas fa-check-circle'
    case 'failed': return 'fas fa-times-circle'
    default: return 'fas fa-clock'
  }
})

const statusText = computed(() => {
  switch (workflowStatus.value) {
    case 'running': return 'Running'
    case 'completed': return 'Completed'
    case 'failed': return 'Failed'
    default: return 'Pending'
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
  const dx = Math.abs(toX - fromX)

  if (Math.abs(toY - fromY) < 10) {
    // Straight horizontal line
    return `M ${fromX} ${fromY} L ${toX} ${toY}`
  }

  // Curved path
  return `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`
}

function getNodeIcon(node: WorkflowNode): string {
  switch (node.type) {
    case 'start': return '▶'
    case 'end': return '⏹'
    case 'decision': return '◇'
    case 'parallel': return '⫴'
    case 'task': return '📋'
    default: return '⚙'
  }
}

function formatNodeType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1)
}

function formatStatus(status?: string): string {
  if (!status) return 'Unknown'
  return status.charAt(0).toUpperCase() + status.slice(1)
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
  return text.slice(0, maxLength - 1) + '…'
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
.workflow-visualization {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  position: relative;
}

.workflow-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.header-info h3 {
  font-size: 18px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
}

.workflow-id {
  font-size: 12px;
  color: #64748b;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}

.status-badge.pending {
  background: rgba(100, 116, 139, 0.2);
  color: #94a3b8;
}

.status-badge.running {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}

.status-badge.completed {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.status-badge.failed {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.layout-btn,
.fit-btn {
  padding: 8px 10px;
  background: transparent;
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s;
}

.layout-btn:hover,
.fit-btn:hover {
  background: rgba(59, 130, 246, 0.1);
  border-color: #3b82f6;
  color: #3b82f6;
}

.workflow-container {
  position: relative;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
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
  stroke: #475569;
  stroke-width: 2;
  transition: stroke 0.3s;
}

.connection-line.active {
  stroke: #3b82f6;
  stroke-width: 3;
  animation: pulse 1.5s infinite;
}

.connection-line.success {
  stroke: #10b981;
}

.connection-line.error {
  stroke: #ef4444;
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
  fill: #1e293b;
  stroke: #475569;
  stroke-width: 2;
  transition: all 0.2s;
}

.workflow-node:hover .node-bg {
  stroke: #3b82f6;
}

.workflow-node.selected .node-bg {
  stroke: #3b82f6;
  stroke-width: 3;
}

.workflow-node.running .node-bg {
  stroke: #3b82f6;
  filter: url(#glow-active);
}

.workflow-node.completed .node-bg {
  stroke: #10b981;
}

.workflow-node.failed .node-bg {
  stroke: #ef4444;
}

.workflow-node.start .node-bg,
.workflow-node.end .node-bg {
  fill: #334155;
}

.node-icon {
  font-size: 18px;
  fill: #e2e8f0;
}

.node-label {
  font-size: 12px;
  fill: #94a3b8;
  font-weight: 500;
}

.status-indicator {
  stroke: #0f172a;
  stroke-width: 2;
}

.status-indicator.pending {
  fill: #64748b;
}

.status-indicator.running {
  fill: #3b82f6;
  animation: blink 1s infinite;
}

.status-indicator.completed {
  fill: #10b981;
}

.status-indicator.failed {
  fill: #ef4444;
}

.status-indicator.skipped {
  fill: #94a3b8;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.duration-badge {
  font-size: 10px;
  fill: #64748b;
}

/* Zoom controls */
.zoom-controls {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(30, 41, 59, 0.9);
  padding: 8px;
  border-radius: 8px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.zoom-controls button {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  background: transparent;
  border-radius: 4px;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.zoom-controls button:hover {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.zoom-level {
  font-size: 12px;
  color: #64748b;
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
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #10b981);
  transition: width 0.3s ease;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 11px;
  color: #e2e8f0;
  font-weight: 500;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

/* Node details panel */
.node-details {
  position: absolute;
  top: 80px;
  right: 20px;
  width: 280px;
  background: #1e293b;
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.details-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: rgba(51, 65, 85, 0.5);
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.details-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background: rgba(59, 130, 246, 0.2);
}

.details-icon.running {
  background: rgba(59, 130, 246, 0.2);
}

.details-icon.completed {
  background: rgba(16, 185, 129, 0.2);
}

.details-icon.failed {
  background: rgba(239, 68, 68, 0.2);
}

.details-title {
  flex: 1;
}

.details-title h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
}

.node-type {
  font-size: 11px;
  color: #64748b;
}

.close-btn {
  padding: 6px;
  background: transparent;
  border: none;
  color: #64748b;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.details-content {
  padding: 16px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 8px 0;
  border-bottom: 1px solid rgba(71, 85, 105, 0.3);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-row .label {
  font-size: 12px;
  color: #64748b;
}

.detail-row .value {
  font-size: 12px;
  color: #e2e8f0;
  font-weight: 500;
}

.detail-row .value.error {
  color: #f87171;
}

.detail-row .output {
  font-size: 11px;
  background: rgba(15, 23, 42, 0.5);
  padding: 8px;
  border-radius: 4px;
  margin-top: 4px;
  overflow-x: auto;
  max-width: 200px;
}

/* Transitions */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
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
    gap: 12px;
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
    border-radius: 12px 12px 0 0;
    max-height: 50vh;
    overflow-y: auto;
  }
}
</style>
