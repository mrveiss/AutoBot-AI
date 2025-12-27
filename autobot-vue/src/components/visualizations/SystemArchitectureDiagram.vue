<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="system-architecture-diagram">
    <!-- Header -->
    <div class="diagram-header">
      <div class="header-content">
        <h3><i class="fas fa-sitemap"></i> {{ title }}</h3>
        <p class="header-description">Interactive system architecture visualization</p>
      </div>
      <div class="header-actions">
        <button @click="refreshArchitecture" :disabled="isLoading" class="action-btn">
          <i class="fas fa-sync" :class="{ 'fa-spin': isLoading }"></i>
          Refresh
        </button>
        <button @click="autoLayout" class="action-btn">
          <i class="fas fa-magic"></i>
          Auto Layout
        </button>
        <button @click="exportDiagram" class="action-btn">
          <i class="fas fa-download"></i>
          Export
        </button>
      </div>
    </div>

    <!-- View Controls -->
    <div class="view-controls">
      <div class="control-group">
        <label>View:</label>
        <div class="view-toggle">
          <button
            v-for="view in viewModes"
            :key="view.id"
            :class="{ active: currentView === view.id }"
            @click="currentView = view.id"
          >
            <i :class="view.icon"></i>
            {{ view.label }}
          </button>
        </div>
      </div>
      <div class="control-group">
        <label>Detail Level:</label>
        <select v-model="detailLevel">
          <option value="high">High (All Components)</option>
          <option value="medium">Medium (Services Only)</option>
          <option value="low">Low (Overview)</option>
        </select>
      </div>
      <div class="control-group">
        <label>
          <input type="checkbox" v-model="showConnections" />
          Show Connections
        </label>
      </div>
      <div class="control-group">
        <label>
          <input type="checkbox" v-model="showMetrics" />
          Show Metrics
        </label>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <div class="spinner"><i class="fas fa-circle-notch fa-spin"></i></div>
      <p>Loading architecture data...</p>
    </div>

    <!-- Diagram Canvas -->
    <div v-else class="diagram-container" ref="diagramContainer">
      <svg
        ref="diagramSvg"
        class="diagram-svg"
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
            id="arrow-data"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#10b981" />
          </marker>
          <marker
            id="arrow-api"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#3b82f6" />
          </marker>
          <marker
            id="arrow-event"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#f59e0b" />
          </marker>

          <!-- Gradients -->
          <linearGradient id="grad-frontend" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#667eea" />
            <stop offset="100%" style="stop-color:#764ba2" />
          </linearGradient>
          <linearGradient id="grad-backend" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#10b981" />
            <stop offset="100%" style="stop-color:#059669" />
          </linearGradient>
          <linearGradient id="grad-database" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#f59e0b" />
            <stop offset="100%" style="stop-color:#d97706" />
          </linearGradient>
          <linearGradient id="grad-ai" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#8b5cf6" />
            <stop offset="100%" style="stop-color:#7c3aed" />
          </linearGradient>
          <linearGradient id="grad-infrastructure" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" style="stop-color:#6366f1" />
            <stop offset="100%" style="stop-color:#4f46e5" />
          </linearGradient>

          <!-- Filters -->
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="4" stdDeviation="4" flood-opacity="0.15" />
          </filter>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g :transform="`translate(${panOffset.x}, ${panOffset.y}) scale(${zoomLevel})`">
          <!-- Background grid -->
          <g class="grid" v-if="showGrid">
            <line
              v-for="i in 20"
              :key="`vline-${i}`"
              :x1="i * 80"
              y1="0"
              :x2="i * 80"
              y2="800"
              stroke="#374151"
              stroke-opacity="0.1"
              stroke-dasharray="4"
            />
            <line
              v-for="i in 10"
              :key="`hline-${i}`"
              x1="0"
              :y1="i * 80"
              x2="1600"
              :y2="i * 80"
              stroke="#374151"
              stroke-opacity="0.1"
              stroke-dasharray="4"
            />
          </g>

          <!-- Connections -->
          <g class="connections" v-if="showConnections">
            <g
              v-for="conn in visibleConnections"
              :key="`conn-${conn.from}-${conn.to}`"
              class="connection"
              :class="{ highlighted: isConnectionHighlighted(conn) }"
            >
              <path
                :d="getConnectionPath(conn)"
                :stroke="getConnectionColor(conn.type)"
                stroke-width="2"
                fill="none"
                :marker-end="`url(#arrow-${conn.type})`"
                :stroke-dasharray="conn.type === 'event' ? '5,5' : 'none'"
              />
              <text
                v-if="detailLevel === 'high'"
                :x="getConnectionMidpoint(conn).x"
                :y="getConnectionMidpoint(conn).y - 8"
                class="connection-label"
                text-anchor="middle"
              >
                {{ conn.label }}
              </text>
            </g>
          </g>

          <!-- Component Groups -->
          <g class="component-groups">
            <g
              v-for="group in componentGroups"
              :key="group.id"
              class="component-group"
              :transform="`translate(${group.x}, ${group.y})`"
            >
              <!-- Group background -->
              <rect
                :width="group.width"
                :height="group.height"
                :rx="12"
                :fill="group.bgColor"
                fill-opacity="0.05"
                :stroke="group.bgColor"
                stroke-opacity="0.2"
                stroke-width="2"
                stroke-dasharray="8,4"
              />
              <!-- Group label -->
              <text
                :x="group.width / 2"
                y="-10"
                class="group-label"
                text-anchor="middle"
                :fill="group.bgColor"
              >
                {{ group.label }}
              </text>
            </g>
          </g>

          <!-- Components (Nodes) -->
          <g class="components">
            <g
              v-for="comp in visibleComponents"
              :key="comp.id"
              class="component"
              :class="{
                selected: selectedComponent?.id === comp.id,
                highlighted: highlightedComponents.includes(comp.id),
                dimmed: highlightedComponents.length > 0 && !highlightedComponents.includes(comp.id),
                'status-healthy': comp.status === 'healthy',
                'status-warning': comp.status === 'warning',
                'status-error': comp.status === 'error'
              }"
              :transform="`translate(${comp.x}, ${comp.y})`"
              @click="selectComponent(comp)"
              @mouseenter="highlightConnectedComponents(comp)"
              @mouseleave="clearHighlight"
            >
              <!-- Component box -->
              <rect
                :width="comp.width"
                :height="comp.height"
                :rx="8"
                :fill="`url(#grad-${comp.category})`"
                filter="url(#shadow)"
              />

              <!-- Status indicator -->
              <circle
                :cx="comp.width - 12"
                cy="12"
                r="6"
                :fill="getStatusColor(comp.status)"
                :filter="comp.status === 'healthy' ? 'url(#glow)' : ''"
              />

              <!-- Icon -->
              <text
                :x="comp.width / 2"
                :y="comp.height / 2 - 8"
                class="component-icon"
                text-anchor="middle"
              >
                {{ comp.icon }}
              </text>

              <!-- Label -->
              <text
                :x="comp.width / 2"
                :y="comp.height / 2 + 12"
                class="component-label"
                text-anchor="middle"
              >
                {{ comp.name }}
              </text>

              <!-- Metrics badge (optional) -->
              <g v-if="showMetrics && comp.metrics" class="metrics-badge">
                <rect
                  :x="comp.width / 2 - 25"
                  :y="comp.height - 8"
                  width="50"
                  height="16"
                  rx="8"
                  fill="#1f2937"
                  fill-opacity="0.9"
                />
                <text
                  :x="comp.width / 2"
                  :y="comp.height + 4"
                  class="metrics-text"
                  text-anchor="middle"
                >
                  {{ formatMetric(comp.metrics) }}
                </text>
              </g>
            </g>
          </g>
        </g>
      </svg>

      <!-- Zoom Controls -->
      <div class="zoom-controls">
        <button @click="zoomIn" title="Zoom in">
          <i class="fas fa-plus"></i>
        </button>
        <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
        <button @click="zoomOut" title="Zoom out">
          <i class="fas fa-minus"></i>
        </button>
        <button @click="resetView" title="Reset view">
          <i class="fas fa-expand"></i>
        </button>
        <button @click="showGrid = !showGrid" title="Toggle grid" :class="{ active: showGrid }">
          <i class="fas fa-th"></i>
        </button>
      </div>

      <!-- Mini Map -->
      <div class="mini-map" v-if="showMiniMap">
        <svg viewBox="0 0 200 120">
          <rect
            v-for="comp in allComponents"
            :key="`mini-${comp.id}`"
            :x="comp.x / 8"
            :y="comp.y / 8"
            :width="comp.width / 8"
            :height="comp.height / 8"
            :fill="getComponentCategoryColor(comp.category)"
            rx="1"
          />
          <!-- Viewport indicator -->
          <rect
            :x="-panOffset.x / 8 / zoomLevel"
            :y="-panOffset.y / 8 / zoomLevel"
            :width="200 / zoomLevel"
            :height="120 / zoomLevel"
            fill="none"
            stroke="#667eea"
            stroke-width="2"
          />
        </svg>
      </div>
    </div>

    <!-- Component Details Panel -->
    <transition name="slide">
      <div v-if="selectedComponent" class="details-panel">
        <div class="panel-header">
          <h4>
            <span class="component-icon-badge" :style="{ background: getComponentCategoryColor(selectedComponent.category) }">
              {{ selectedComponent.icon }}
            </span>
            {{ selectedComponent.name }}
          </h4>
          <button @click="selectedComponent = null" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="panel-content">
          <!-- Basic Info -->
          <div class="info-section">
            <div class="info-row">
              <label>Type:</label>
              <span class="type-badge" :style="{ background: getComponentCategoryColor(selectedComponent.category) }">
                {{ selectedComponent.type }}
              </span>
            </div>
            <div class="info-row">
              <label>Status:</label>
              <span class="status-badge" :class="`status-${selectedComponent.status}`">
                {{ selectedComponent.status }}
              </span>
            </div>
            <div class="info-row" v-if="selectedComponent.host">
              <label>Host:</label>
              <code>{{ selectedComponent.host }}</code>
            </div>
            <div class="info-row" v-if="selectedComponent.port">
              <label>Port:</label>
              <code>{{ selectedComponent.port }}</code>
            </div>
          </div>

          <!-- Description -->
          <div class="description-section" v-if="selectedComponent.description">
            <h5><i class="fas fa-info-circle"></i> Description</h5>
            <p>{{ selectedComponent.description }}</p>
          </div>

          <!-- Metrics -->
          <div class="metrics-section" v-if="selectedComponent.detailedMetrics">
            <h5><i class="fas fa-chart-bar"></i> Metrics</h5>
            <div class="metrics-grid">
              <div
                v-for="(value, key) in selectedComponent.detailedMetrics"
                :key="key"
                class="metric-item"
              >
                <span class="metric-label">{{ formatMetricKey(key) }}</span>
                <span class="metric-value">{{ value }}</span>
              </div>
            </div>
          </div>

          <!-- Connections -->
          <div class="connections-section" v-if="getComponentConnections(selectedComponent.id).length">
            <h5><i class="fas fa-link"></i> Connections</h5>
            <ul class="connections-list">
              <li
                v-for="conn in getComponentConnections(selectedComponent.id)"
                :key="`${conn.from}-${conn.to}`"
                @click="navigateToComponent(conn)"
              >
                <span class="conn-type" :style="{ background: getConnectionColor(conn.type) }">
                  {{ conn.type }}
                </span>
                <span class="conn-direction">
                  <i :class="conn.from === selectedComponent.id ? 'fas fa-arrow-right' : 'fas fa-arrow-left'"></i>
                </span>
                <span class="conn-target">
                  {{ getComponentName(conn.from === selectedComponent.id ? conn.to : conn.from) }}
                </span>
              </li>
            </ul>
          </div>

          <!-- Actions -->
          <div class="panel-actions">
            <button @click="focusOnComponent(selectedComponent)" class="action-btn">
              <i class="fas fa-crosshairs"></i>
              Focus
            </button>
            <button @click="expandConnections(selectedComponent)" class="action-btn">
              <i class="fas fa-expand-arrows-alt"></i>
              Expand
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Legend -->
    <div class="diagram-legend">
      <h5>Legend</h5>
      <div class="legend-section">
        <span class="legend-title">Components:</span>
        <div class="legend-items">
          <div class="legend-item">
            <span class="legend-color" style="background: linear-gradient(135deg, #667eea, #764ba2)"></span>
            <span>Frontend</span>
          </div>
          <div class="legend-item">
            <span class="legend-color" style="background: linear-gradient(135deg, #10b981, #059669)"></span>
            <span>Backend</span>
          </div>
          <div class="legend-item">
            <span class="legend-color" style="background: linear-gradient(135deg, #f59e0b, #d97706)"></span>
            <span>Database</span>
          </div>
          <div class="legend-item">
            <span class="legend-color" style="background: linear-gradient(135deg, #8b5cf6, #7c3aed)"></span>
            <span>AI/ML</span>
          </div>
          <div class="legend-item">
            <span class="legend-color" style="background: linear-gradient(135deg, #6366f1, #4f46e5)"></span>
            <span>Infrastructure</span>
          </div>
        </div>
      </div>
      <div class="legend-section">
        <span class="legend-title">Connections:</span>
        <div class="legend-items">
          <div class="legend-item">
            <span class="legend-line" style="background: #3b82f6"></span>
            <span>API</span>
          </div>
          <div class="legend-item">
            <span class="legend-line" style="background: #10b981"></span>
            <span>Data</span>
          </div>
          <div class="legend-item">
            <span class="legend-line dashed" style="background: #f59e0b"></span>
            <span>Event</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted, watch } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { getConfig } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SystemArchitectureDiagram')

// Get SSOT config for VM IPs and ports
const config = getConfig()

// ============================================================================
// Types
// ============================================================================

interface Component {
  id: string
  name: string
  type: string
  category: 'frontend' | 'backend' | 'database' | 'ai' | 'infrastructure'
  icon: string
  x: number
  y: number
  width: number
  height: number
  status: 'healthy' | 'warning' | 'error' | 'unknown'
  host?: string
  port?: number
  description?: string
  metrics?: string
  detailedMetrics?: Record<string, string | number>
  group?: string
}

interface Connection {
  from: string
  to: string
  type: 'api' | 'data' | 'event'
  label?: string
  bidirectional?: boolean
}

interface ComponentGroup {
  id: string
  label: string
  x: number
  y: number
  width: number
  height: number
  bgColor: string
}

interface ViewMode {
  id: string
  label: string
  icon: string
}

// ============================================================================
// Props
// ============================================================================

interface Props {
  title?: string
  height?: number
  autoRefresh?: boolean
  refreshInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  title: 'System Architecture',
  height: 600,
  autoRefresh: true,
  refreshInterval: 30000
})

// ============================================================================
// State
// ============================================================================

const isLoading = ref(false)
const allComponents = ref<Component[]>([])
const connections = ref<Connection[]>([])
const componentGroups = ref<ComponentGroup[]>([])
const selectedComponent = ref<Component | null>(null)
const highlightedComponents = ref<string[]>([])

// View controls
const currentView = ref('physical')
const detailLevel = ref<'high' | 'medium' | 'low'>('medium')
const showConnections = ref(true)
const showMetrics = ref(true)
const showGrid = ref(false)
const showMiniMap = ref(true)

// Viewport state
const diagramContainer = ref<HTMLElement | null>(null)
const diagramSvg = ref<SVGElement | null>(null)
const zoomLevel = ref(1)
const panOffset = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const lastPanPoint = ref({ x: 0, y: 0 })
const viewBox = ref('0 0 1600 800')

// View modes
const viewModes: ViewMode[] = [
  { id: 'physical', label: 'Physical', icon: 'fas fa-server' },
  { id: 'logical', label: 'Logical', icon: 'fas fa-project-diagram' },
  { id: 'dataflow', label: 'Data Flow', icon: 'fas fa-exchange-alt' }
]

// ============================================================================
// Computed
// ============================================================================

const visibleComponents = computed(() => {
  if (detailLevel.value === 'low') {
    // Only show main services
    return allComponents.value.filter(c =>
      ['frontend', 'backend', 'database', 'ai'].includes(c.category) &&
      c.type !== 'worker'
    )
  } else if (detailLevel.value === 'medium') {
    // Show services, hide internal workers
    return allComponents.value.filter(c => c.type !== 'worker')
  }
  return allComponents.value
})

const visibleConnections = computed(() => {
  const visibleIds = new Set(visibleComponents.value.map(c => c.id))
  return connections.value.filter(conn =>
    visibleIds.has(conn.from) && visibleIds.has(conn.to)
  )
})

// ============================================================================
// Methods - Data
// ============================================================================

async function refreshArchitecture() {
  isLoading.value = true

  try {
    // Issue #552: Fixed path - backend uses /api/monitoring/services/health
    const healthResponse = await apiClient.get('/api/monitoring/services/health')
    const healthData = await parseApiResponse(healthResponse)

    // Generate architecture based on known infrastructure
    generateArchitecture(healthData?.data?.services || healthData?.services || {})

  } catch (error) {
    logger.error('Failed to fetch architecture data:', error)
    // Generate default architecture on error
    generateArchitecture({})
  } finally {
    isLoading.value = false
  }
}

function generateArchitecture(serviceHealth: Record<string, unknown>) {
  // Define the AutoBot distributed architecture
  const components: Component[] = [
    // Frontend Layer
    {
      id: 'vue-frontend',
      name: 'Vue.js Frontend',
      type: 'Web Application',
      category: 'frontend',
      icon: '\u{1F310}',
      x: 200,
      y: 50,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'frontend'),
      host: config.vm.frontend,
      port: config.port.frontend,
      description: 'Vue 3 + TypeScript web interface',
      metrics: 'Active',
      group: 'presentation'
    },
    {
      id: 'vnc-desktop',
      name: 'VNC Desktop',
      type: 'Remote Desktop',
      category: 'frontend',
      icon: '\u{1F5A5}',
      x: 380,
      y: 50,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'vnc'),
      host: config.vm.main,
      port: config.port.vnc,
      description: 'NoVNC web-based remote desktop',
      group: 'presentation'
    },

    // Backend Layer
    {
      id: 'fastapi-backend',
      name: 'FastAPI Backend',
      type: 'API Server',
      category: 'backend',
      icon: '\u{2699}',
      x: 200,
      y: 200,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'backend'),
      host: config.vm.main,
      port: config.port.backend,
      description: 'Main API server and orchestration',
      metrics: '8001',
      group: 'services'
    },
    {
      id: 'websocket-server',
      name: 'WebSocket Server',
      type: 'Real-time',
      category: 'backend',
      icon: '\u{1F50C}',
      x: 380,
      y: 200,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'websocket'),
      description: 'Real-time event streaming',
      group: 'services'
    },
    {
      id: 'browser-automation',
      name: 'Browser Automation',
      type: 'Playwright',
      category: 'backend',
      icon: '\u{1F916}',
      x: 560,
      y: 200,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'playwright'),
      host: config.vm.browser,
      port: config.port.browser,
      description: 'Headless browser automation via Playwright',
      group: 'services'
    },

    // Data Layer
    {
      id: 'redis-stack',
      name: 'Redis Stack',
      type: 'Cache/Queue',
      category: 'database',
      icon: '\u{1F9F1}',
      x: 200,
      y: 350,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'redis'),
      host: config.vm.redis,
      port: config.port.redis,
      description: 'Multi-purpose cache, queues, and search',
      metrics: '6379',
      group: 'data'
    },
    {
      id: 'sqlite-db',
      name: 'SQLite Database',
      type: 'Primary DB',
      category: 'database',
      icon: '\u{1F4BE}',
      x: 380,
      y: 350,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'sqlite'),
      description: 'Main application database',
      group: 'data'
    },
    {
      id: 'chromadb',
      name: 'ChromaDB',
      type: 'Vector DB',
      category: 'database',
      icon: '\u{1F9E0}',
      x: 560,
      y: 350,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'chromadb'),
      description: 'Vector embeddings for RAG/search',
      group: 'data'
    },

    // AI Layer
    {
      id: 'llm-providers',
      name: 'LLM Providers',
      type: 'AI Models',
      category: 'ai',
      icon: '\u{1F4AC}',
      x: 200,
      y: 500,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'llm'),
      description: 'OpenAI, Anthropic, Ollama integration',
      group: 'ai'
    },
    {
      id: 'npu-worker',
      name: 'NPU Worker',
      type: 'Hardware AI',
      category: 'ai',
      icon: '\u{1F4A0}',
      x: 380,
      y: 500,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'npu'),
      host: config.vm.npu,
      port: config.port.npu,
      description: 'Intel NPU acceleration via OpenVINO',
      group: 'ai'
    },
    {
      id: 'ai-stack',
      name: 'AI Stack',
      type: 'Processing',
      category: 'ai',
      icon: '\u{1F52C}',
      x: 560,
      y: 500,
      width: 140,
      height: 80,
      status: getServiceStatus(serviceHealth, 'ai_stack'),
      host: config.vm.aistack,
      port: config.port.aistack,
      description: 'Advanced AI processing pipeline',
      group: 'ai'
    },

    // Infrastructure Layer
    {
      id: 'prometheus',
      name: 'Prometheus',
      type: 'Monitoring',
      category: 'infrastructure',
      icon: '\u{1F4CA}',
      x: 760,
      y: 200,
      width: 120,
      height: 70,
      status: getServiceStatus(serviceHealth, 'prometheus'),
      port: 9090,
      description: 'Metrics collection and alerting',
      group: 'monitoring'
    },
    {
      id: 'grafana',
      name: 'Grafana',
      type: 'Dashboards',
      category: 'infrastructure',
      icon: '\u{1F4C8}',
      x: 760,
      y: 290,
      width: 120,
      height: 70,
      status: getServiceStatus(serviceHealth, 'grafana'),
      port: 3001,
      description: 'Metrics visualization dashboards',
      group: 'monitoring'
    },
    {
      id: 'loki',
      name: 'Loki',
      type: 'Logging',
      category: 'infrastructure',
      icon: '\u{1F4DD}',
      x: 760,
      y: 380,
      width: 120,
      height: 70,
      status: getServiceStatus(serviceHealth, 'loki'),
      description: 'Log aggregation and search',
      group: 'monitoring'
    }
  ]

  // Define connections
  const conns: Connection[] = [
    // Frontend to Backend
    { from: 'vue-frontend', to: 'fastapi-backend', type: 'api', label: 'REST API' },
    { from: 'vue-frontend', to: 'websocket-server', type: 'event', label: 'WebSocket' },
    { from: 'vnc-desktop', to: 'fastapi-backend', type: 'api' },

    // Backend to Data
    { from: 'fastapi-backend', to: 'redis-stack', type: 'data', label: 'Cache/Queue' },
    { from: 'fastapi-backend', to: 'sqlite-db', type: 'data', label: 'Persistence' },
    { from: 'fastapi-backend', to: 'chromadb', type: 'data', label: 'Vectors' },
    { from: 'websocket-server', to: 'redis-stack', type: 'event', label: 'Pub/Sub' },
    { from: 'browser-automation', to: 'fastapi-backend', type: 'api' },

    // Backend to AI
    { from: 'fastapi-backend', to: 'llm-providers', type: 'api', label: 'LLM Calls' },
    { from: 'fastapi-backend', to: 'npu-worker', type: 'api', label: 'NPU Tasks' },
    { from: 'fastapi-backend', to: 'ai-stack', type: 'api', label: 'AI Pipeline' },
    { from: 'llm-providers', to: 'chromadb', type: 'data', label: 'Embeddings' },
    { from: 'npu-worker', to: 'redis-stack', type: 'event', label: 'Results' },

    // Monitoring
    { from: 'prometheus', to: 'fastapi-backend', type: 'data', label: 'Scrape' },
    { from: 'prometheus', to: 'redis-stack', type: 'data' },
    { from: 'grafana', to: 'prometheus', type: 'data', label: 'Query' },
    { from: 'grafana', to: 'loki', type: 'data' },
    { from: 'loki', to: 'fastapi-backend', type: 'data', label: 'Logs' }
  ]

  // Define component groups
  const groups: ComponentGroup[] = [
    { id: 'presentation', label: 'Presentation Layer', x: 180, y: 30, width: 360, height: 120, bgColor: '#667eea' },
    { id: 'services', label: 'Service Layer', x: 180, y: 180, width: 540, height: 120, bgColor: '#10b981' },
    { id: 'data', label: 'Data Layer', x: 180, y: 330, width: 540, height: 120, bgColor: '#f59e0b' },
    { id: 'ai', label: 'AI/ML Layer', x: 180, y: 480, width: 540, height: 120, bgColor: '#8b5cf6' },
    { id: 'monitoring', label: 'Monitoring', x: 740, y: 180, width: 160, height: 290, bgColor: '#6366f1' }
  ]

  allComponents.value = components
  connections.value = conns
  componentGroups.value = groups
}

function getServiceStatus(services: Record<string, unknown>, key: string): 'healthy' | 'warning' | 'error' | 'unknown' {
  const service = services[key] as { status?: string } | undefined
  if (!service) return 'unknown'
  if (service.status === 'healthy' || service.status === 'up') return 'healthy'
  if (service.status === 'degraded') return 'warning'
  if (service.status === 'down' || service.status === 'error') return 'error'
  return 'unknown'
}

// ============================================================================
// Methods - Visualization
// ============================================================================

function getConnectionPath(conn: Connection): string {
  const from = allComponents.value.find(c => c.id === conn.from)
  const to = allComponents.value.find(c => c.id === conn.to)
  if (!from || !to) return ''

  const fromX = from.x + from.width / 2
  const fromY = from.y + from.height
  const toX = to.x + to.width / 2
  const toY = to.y

  // Create curved path
  const midY = (fromY + toY) / 2
  return `M ${fromX} ${fromY} C ${fromX} ${midY}, ${toX} ${midY}, ${toX} ${toY}`
}

function getConnectionMidpoint(conn: Connection): { x: number; y: number } {
  const from = allComponents.value.find(c => c.id === conn.from)
  const to = allComponents.value.find(c => c.id === conn.to)
  if (!from || !to) return { x: 0, y: 0 }

  return {
    x: (from.x + from.width / 2 + to.x + to.width / 2) / 2,
    y: (from.y + from.height + to.y) / 2
  }
}

function getConnectionColor(type: string): string {
  const colors: Record<string, string> = {
    api: '#3b82f6',
    data: '#10b981',
    event: '#f59e0b'
  }
  return colors[type] || '#6b7280'
}

function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    healthy: '#10b981',
    warning: '#f59e0b',
    error: '#ef4444',
    unknown: '#6b7280'
  }
  return colors[status] || '#6b7280'
}

function getComponentCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    frontend: '#667eea',
    backend: '#10b981',
    database: '#f59e0b',
    ai: '#8b5cf6',
    infrastructure: '#6366f1'
  }
  return colors[category] || '#6b7280'
}

function formatMetric(metric: string | undefined): string {
  return metric || ''
}

function formatMetricKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// ============================================================================
// Methods - Interactions
// ============================================================================

function selectComponent(comp: Component) {
  selectedComponent.value = selectedComponent.value?.id === comp.id ? null : comp
}

function highlightConnectedComponents(comp: Component) {
  const connected = new Set<string>([comp.id])
  connections.value.forEach(conn => {
    if (conn.from === comp.id) connected.add(conn.to)
    if (conn.to === comp.id) connected.add(conn.from)
  })
  highlightedComponents.value = Array.from(connected)
}

function clearHighlight() {
  highlightedComponents.value = []
}

function isConnectionHighlighted(conn: Connection): boolean {
  return highlightedComponents.value.includes(conn.from) && highlightedComponents.value.includes(conn.to)
}

function getComponentConnections(compId: string): Connection[] {
  return connections.value.filter(c => c.from === compId || c.to === compId)
}

function getComponentName(compId: string): string {
  return allComponents.value.find(c => c.id === compId)?.name || compId
}

function navigateToComponent(conn: Connection) {
  const targetId = conn.from === selectedComponent.value?.id ? conn.to : conn.from
  const target = allComponents.value.find(c => c.id === targetId)
  if (target) {
    selectComponent(target)
    focusOnComponent(target)
  }
}

function focusOnComponent(comp: Component) {
  panOffset.value = {
    x: 400 - comp.x - comp.width / 2,
    y: 300 - comp.y - comp.height / 2
  }
}

function expandConnections(comp: Component) {
  highlightConnectedComponents(comp)
}

function autoLayout() {
  // Auto-arrange components
  logger.debug('Auto layout triggered')
}

function exportDiagram() {
  // Export as SVG or PNG
  const svg = diagramSvg.value
  if (!svg) return

  const serializer = new XMLSerializer()
  const svgString = serializer.serializeToString(svg)
  const blob = new Blob([svgString], { type: 'image/svg+xml' })
  const url = URL.createObjectURL(blob)

  const link = document.createElement('a')
  link.href = url
  link.download = 'system-architecture.svg'
  link.click()

  URL.revokeObjectURL(url)
}

// ============================================================================
// Methods - Pan & Zoom
// ============================================================================

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

function resetView() {
  zoomLevel.value = 1
  panOffset.value = { x: 0, y: 0 }
}

// ============================================================================
// Lifecycle
// ============================================================================

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  refreshArchitecture()

  if (props.autoRefresh && props.refreshInterval > 0) {
    refreshTimer = setInterval(refreshArchitecture, props.refreshInterval)
  }
})

watch(() => currentView.value, () => {
  // Could adjust layout based on view mode
  logger.debug('View changed to:', currentView.value)
})
</script>

<style scoped>
.system-architecture-diagram {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0f172a;
  color: #f8fafc;
  border-radius: 12px;
  overflow: hidden;
}

/* Header */
.diagram-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: linear-gradient(135deg, #1e293b, #0f172a);
  border-bottom: 1px solid #334155;
}

.header-content h3 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.25rem;
  font-weight: 600;
  color: #f8fafc;
}

.header-content h3 i {
  color: #667eea;
}

.header-description {
  color: #94a3b8;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

/* Action Buttons */
.action-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #1e293b;
  border: 1px solid #334155;
  color: #e2e8f0;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: #334155;
  border-color: #475569;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* View Controls */
.view-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  padding: 1rem 1.5rem;
  background: #1e293b;
  border-bottom: 1px solid #334155;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.control-group label {
  color: #94a3b8;
  font-size: 0.875rem;
}

.view-toggle {
  display: flex;
  border-radius: 0.5rem;
  overflow: hidden;
  border: 1px solid #334155;
}

.view-toggle button {
  padding: 0.5rem 1rem;
  background: transparent;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  transition: all 0.2s;
}

.view-toggle button:hover {
  background: #334155;
}

.view-toggle button.active {
  background: #667eea;
  color: white;
}

.control-group select {
  padding: 0.5rem 0.75rem;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 0.375rem;
  color: #e2e8f0;
  font-size: 0.875rem;
}

.control-group input[type="checkbox"] {
  accent-color: #667eea;
}

/* Loading State */
.loading-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  color: #94a3b8;
}

.spinner {
  font-size: 2rem;
  color: #667eea;
}

/* Diagram Container */
.diagram-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.diagram-svg {
  width: 100%;
  height: 100%;
  cursor: grab;
  background: radial-gradient(circle at 50% 50%, #1e293b 0%, #0f172a 100%);
}

.diagram-svg:active {
  cursor: grabbing;
}

/* Connections */
.connection path {
  transition: stroke-width 0.2s, opacity 0.2s;
}

.connection.highlighted path {
  stroke-width: 3;
}

.connection-label {
  font-size: 10px;
  fill: #94a3b8;
}

/* Component Groups */
.group-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Components */
.component {
  cursor: pointer;
  transition: transform 0.2s, opacity 0.2s;
}

.component:hover {
  transform: scale(1.02);
}

.component.selected rect {
  stroke: #f8fafc;
  stroke-width: 3;
}

.component.dimmed {
  opacity: 0.3;
}

.component.highlighted {
  opacity: 1;
}

.component-icon {
  font-size: 24px;
  fill: white;
}

.component-label {
  font-size: 12px;
  font-weight: 500;
  fill: white;
}

.metrics-text {
  font-size: 10px;
  fill: #94a3b8;
}

/* Zoom Controls */
.zoom-controls {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #1e293b;
  padding: 0.5rem;
  border-radius: 0.5rem;
  border: 1px solid #334155;
}

.zoom-controls button {
  width: 32px;
  height: 32px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 0.375rem;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.zoom-controls button:hover {
  background: #334155;
  color: #f8fafc;
}

.zoom-controls button.active {
  background: #667eea;
  border-color: #667eea;
  color: white;
}

.zoom-level {
  font-size: 0.75rem;
  color: #94a3b8;
  min-width: 40px;
  text-align: center;
}

/* Mini Map */
.mini-map {
  position: absolute;
  bottom: 1rem;
  left: 1rem;
  width: 200px;
  height: 120px;
  background: #1e293b;
  border-radius: 0.5rem;
  border: 1px solid #334155;
  overflow: hidden;
}

.mini-map svg {
  width: 100%;
  height: 100%;
}

/* Details Panel */
.details-panel {
  position: absolute;
  top: 1rem;
  right: 1rem;
  width: 320px;
  max-height: calc(100% - 2rem);
  background: #1e293b;
  border-radius: 0.75rem;
  border: 1px solid #334155;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: linear-gradient(135deg, #334155, #1e293b);
  border-bottom: 1px solid #334155;
}

.panel-header h4 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1rem;
  font-weight: 600;
  color: #f8fafc;
}

.component-icon-badge {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.close-btn {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 0.25rem;
}

.close-btn:hover {
  color: #f8fafc;
}

.panel-content {
  padding: 1rem;
  overflow-y: auto;
  flex: 1;
}

.info-section {
  margin-bottom: 1rem;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #334155;
}

.info-row label {
  font-size: 0.75rem;
  color: #94a3b8;
}

.info-row code {
  font-size: 0.75rem;
  background: #0f172a;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  color: #e2e8f0;
}

.type-badge {
  font-size: 0.75rem;
  color: white;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.status-badge {
  font-size: 0.75rem;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  text-transform: capitalize;
}

.status-badge.status-healthy {
  background: #10b98120;
  color: #10b981;
}

.status-badge.status-warning {
  background: #f59e0b20;
  color: #f59e0b;
}

.status-badge.status-error {
  background: #ef444420;
  color: #ef4444;
}

.status-badge.status-unknown {
  background: #6b728020;
  color: #6b7280;
}

.description-section,
.metrics-section,
.connections-section {
  margin-bottom: 1rem;
}

.description-section h5,
.metrics-section h5,
.connections-section h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.description-section p {
  font-size: 0.8125rem;
  color: #94a3b8;
  line-height: 1.5;
}

.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}

.metric-item {
  background: #0f172a;
  padding: 0.5rem;
  border-radius: 0.375rem;
}

.metric-label {
  font-size: 0.625rem;
  color: #64748b;
  text-transform: uppercase;
  display: block;
  margin-bottom: 0.25rem;
}

.metric-value {
  font-size: 0.875rem;
  font-weight: 600;
  color: #e2e8f0;
}

.connections-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.connections-list li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: #0f172a;
  border-radius: 0.375rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: background 0.2s;
}

.connections-list li:hover {
  background: #334155;
}

.conn-type {
  font-size: 0.625rem;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  color: white;
  text-transform: uppercase;
}

.conn-direction {
  color: #64748b;
  font-size: 0.75rem;
}

.conn-target {
  font-size: 0.8125rem;
  color: #e2e8f0;
}

.panel-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid #334155;
}

.panel-actions .action-btn {
  flex: 1;
  justify-content: center;
}

/* Legend */
.diagram-legend {
  padding: 1rem 1.5rem;
  background: #1e293b;
  border-top: 1px solid #334155;
}

.diagram-legend h5 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 0.75rem;
}

.legend-section {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.legend-title {
  font-size: 0.75rem;
  color: #64748b;
  min-width: 80px;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: #94a3b8;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.legend-line {
  width: 20px;
  height: 3px;
  border-radius: 1px;
}

.legend-line.dashed {
  background: repeating-linear-gradient(90deg, currentColor, currentColor 4px, transparent 4px, transparent 8px);
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
  .diagram-header {
    flex-direction: column;
    gap: 1rem;
  }

  .view-controls {
    flex-direction: column;
  }

  .details-panel {
    width: 100%;
    max-width: none;
    top: auto;
    bottom: 0;
    right: 0;
    left: 0;
    border-radius: 0.75rem 0.75rem 0 0;
    max-height: 50%;
  }

  .mini-map {
    display: none;
  }
}
</style>
