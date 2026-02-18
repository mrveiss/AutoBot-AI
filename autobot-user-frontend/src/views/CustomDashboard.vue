<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="custom-dashboard view-container-flex">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h1><i class="fas fa-th-large"></i> {{ dashboardTitle }}</h1>
        <p class="header-description">Customizable dashboard with drag-and-drop widgets</p>
      </div>
      <div class="header-actions">
        <button @click="toggleEditMode" class="action-btn" :class="{ active: isEditMode }">
          <i :class="isEditMode ? 'fas fa-check' : 'fas fa-edit'"></i>
          {{ isEditMode ? 'Done' : 'Edit Layout' }}
        </button>
        <button @click="addWidget" class="action-btn" v-if="isEditMode">
          <i class="fas fa-plus"></i>
          Add Widget
        </button>
        <button @click="saveDashboard" class="action-btn primary">
          <i class="fas fa-save"></i>
          Save
        </button>
        <div class="dashboard-selector">
          <select v-model="currentDashboardId" @change="loadDashboard">
            <option v-for="dash in availableDashboards" :key="dash.id" :value="dash.id">
              {{ dash.name }}
            </option>
          </select>
          <button @click="createNewDashboard" class="icon-btn" title="Create new dashboard">
            <i class="fas fa-plus"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Widget Palette (Edit Mode) -->
    <transition name="slide-down">
      <div v-if="isEditMode" class="widget-palette">
        <h4>Available Widgets</h4>
        <div class="palette-widgets">
          <div
            v-for="widget in availableWidgets"
            :key="widget.type"
            class="palette-widget"
            draggable="true"
            @dragstart="handleDragStart($event, widget)"
          >
            <i :class="widget.icon"></i>
            <span>{{ widget.name }}</span>
          </div>
        </div>
      </div>
    </transition>

    <!-- Dashboard Grid -->
    <div
      class="dashboard-grid"
      :class="{ 'edit-mode': isEditMode }"
      @dragover.prevent="handleDragOver"
      @drop="handleDrop"
    >
      <div
        v-for="widget in widgets"
        :key="widget.id"
        class="widget-container"
        :class="{ 'is-dragging': draggingWidgetId === widget.id }"
        :style="getWidgetStyle(widget)"
        :draggable="isEditMode"
        @dragstart="handleWidgetDragStart($event, widget)"
        @dragend="handleDragEnd"
      >
        <!-- Widget Header -->
        <div class="widget-header">
          <h3>
            <i :class="getWidgetIcon(widget.type)"></i>
            {{ widget.title }}
          </h3>
          <div class="widget-actions" v-if="isEditMode">
            <button @click="configureWidget(widget)" title="Configure">
              <i class="fas fa-cog"></i>
            </button>
            <button @click="resizeWidget(widget, 'expand')" title="Expand">
              <i class="fas fa-expand-alt"></i>
            </button>
            <button @click="resizeWidget(widget, 'shrink')" title="Shrink">
              <i class="fas fa-compress-alt"></i>
            </button>
            <button @click="removeWidget(widget.id)" class="remove-btn" title="Remove">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>

        <!-- Widget Content -->
        <div class="widget-content">
          <component
            :is="getWidgetComponent(widget.type)"
            v-bind="widget.props"
            :key="`${widget.id}-${widget.refreshKey}`"
          />
        </div>

      </div>

      <!-- Empty State -->
      <div v-if="widgets.length === 0" class="empty-dashboard">
        <div class="empty-icon">
          <i class="fas fa-th-large"></i>
        </div>
        <h3>No Widgets Added</h3>
        <p>Click "Edit Layout" to add widgets to your dashboard</p>
        <button @click="toggleEditMode" class="action-btn primary">
          <i class="fas fa-plus"></i>
          Add Your First Widget
        </button>
      </div>
    </div>

    <!-- Widget Configuration Modal -->
    <div v-if="showConfigModal" class="modal-overlay" @click.self="showConfigModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4><i class="fas fa-cog"></i> Configure Widget</h4>
          <button @click="showConfigModal = false" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body" v-if="configWidget">
          <div class="form-group">
            <label>Title</label>
            <input v-model="configWidget.title" type="text" />
          </div>
          <div class="form-group">
            <label>Refresh Interval (seconds)</label>
            <input v-model.number="configWidget.refreshInterval" type="number" min="5" />
          </div>
          <div class="form-group" v-if="hasHeightConfig(configWidget.type)">
            <label>Height (px)</label>
            <input v-model.number="configWidget.props.height" type="number" min="200" />
          </div>
          <!-- Type-specific config options -->
          <div v-if="configWidget.type === 'heatmap'" class="form-group">
            <label>Metric</label>
            <select v-model="configWidget.props.metric">
              <option value="cpu">CPU</option>
              <option value="memory">Memory</option>
              <option value="disk">Disk</option>
              <option value="network">Network</option>
            </select>
          </div>
          <div v-if="configWidget.type === 'chart'" class="form-group">
            <label>Chart Type</label>
            <select v-model="configWidget.props.chartType">
              <option value="line">Line</option>
              <option value="area">Area</option>
              <option value="bar">Bar</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="showConfigModal = false" class="action-btn">Cancel</button>
          <button @click="saveWidgetConfig" class="action-btn primary">Save Changes</button>
        </div>
      </div>
    </div>

    <!-- New Dashboard Modal -->
    <div v-if="showNewDashboardModal" class="modal-overlay" @click.self="showNewDashboardModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4><i class="fas fa-plus-circle"></i> Create Dashboard</h4>
          <button @click="showNewDashboardModal = false" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>Dashboard Name</label>
            <input v-model="newDashboardName" type="text" placeholder="My Dashboard" />
          </div>
          <div class="form-group">
            <label>Template</label>
            <select v-model="newDashboardTemplate">
              <option value="blank">Blank</option>
              <option value="monitoring">System Monitoring</option>
              <option value="agents">Agent Activity</option>
              <option value="workflows">Workflows</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="showNewDashboardModal = false" class="action-btn">Cancel</button>
          <button @click="confirmCreateDashboard" class="action-btn primary">Create</button>
        </div>
      </div>
    </div>

    <!-- Add Widget Modal -->
    <div v-if="showAddWidgetModal" class="modal-overlay" @click.self="showAddWidgetModal = false">
      <div class="modal-content wide">
        <div class="modal-header">
          <h4><i class="fas fa-plus-circle"></i> Add Widget</h4>
          <button @click="showAddWidgetModal = false" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="widget-gallery">
            <div
              v-for="widget in availableWidgets"
              :key="widget.type"
              class="widget-option"
              @click="confirmAddWidget(widget)"
            >
              <div class="widget-preview">
                <i :class="widget.icon"></i>
              </div>
              <h5>{{ widget.name }}</h5>
              <p>{{ widget.description }}</p>
            </div>
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

import { ref, computed, onMounted, shallowRef, markRaw } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Import visualization components
import ResourceHeatmap from '@/components/visualizations/ResourceHeatmap.vue'
import WorkflowVisualization from '@/components/visualizations/WorkflowVisualization.vue'
import AgentActivityVisualization from '@/components/visualizations/AgentActivityVisualization.vue'
import SystemArchitectureDiagram from '@/components/visualizations/SystemArchitectureDiagram.vue'


const logger = createLogger('CustomDashboard')

// ============================================================================
// Types
// ============================================================================

interface Widget {
  id: string
  type: string
  title: string
  x: number
  y: number
  width: number
  height: number
  props: Record<string, unknown>
  refreshInterval?: number
  refreshKey?: number
}

interface WidgetDefinition {
  type: string
  name: string
  icon: string
  description: string
  defaultWidth: number
  defaultHeight: number
  defaultProps: Record<string, unknown>
}

interface Dashboard {
  id: string
  name: string
  widgets: Widget[]
  createdAt: number
  updatedAt: number
}

// ============================================================================
// State
// ============================================================================

const isEditMode = ref(false)
const widgets = ref<Widget[]>([])
const currentDashboardId = ref('default')
const availableDashboards = ref<Dashboard[]>([])
const draggingWidgetId = ref<string | null>(null)
const showConfigModal = ref(false)
const showNewDashboardModal = ref(false)
const showAddWidgetModal = ref(false)
const configWidget = ref<Widget | null>(null)
const newDashboardName = ref('')
const newDashboardTemplate = ref('blank')

// Component registry (using shallowRef for performance)
const componentRegistry = shallowRef<Record<string, unknown>>({
  heatmap: markRaw(ResourceHeatmap),
  workflow: markRaw(WorkflowVisualization),
  agents: markRaw(AgentActivityVisualization),
  architecture: markRaw(SystemArchitectureDiagram)
})

// Available widget definitions
const availableWidgets: WidgetDefinition[] = [
  {
    type: 'heatmap',
    name: 'Resource Heatmap',
    icon: 'fas fa-th',
    description: 'Visualize resource usage patterns over time',
    defaultWidth: 2,
    defaultHeight: 300,
    defaultProps: { height: 300, metric: 'cpu' }
  },
  {
    type: 'workflow',
    name: 'Workflow Visualization',
    icon: 'fas fa-project-diagram',
    description: 'Interactive workflow execution flowcharts',
    defaultWidth: 2,
    defaultHeight: 400,
    defaultProps: { height: 400 }
  },
  {
    type: 'agents',
    name: 'Agent Activity',
    icon: 'fas fa-robot',
    description: 'Real-time agent activity monitoring',
    defaultWidth: 2,
    defaultHeight: 400,
    defaultProps: { height: 400 }
  },
  {
    type: 'architecture',
    name: 'System Architecture',
    icon: 'fas fa-sitemap',
    description: 'Interactive system architecture diagram',
    defaultWidth: 3,
    defaultHeight: 500,
    defaultProps: { height: 500 }
  },
]

// ============================================================================
// Computed
// ============================================================================

const dashboardTitle = computed(() => {
  const dash = availableDashboards.value.find(d => d.id === currentDashboardId.value)
  return dash?.name || 'Custom Dashboard'
})

// ============================================================================
// Methods - Dashboard Management
// ============================================================================

function loadDashboards() {
  // Load from localStorage
  const stored = localStorage.getItem('autobot_dashboards')
  if (stored) {
    try {
      availableDashboards.value = JSON.parse(stored)
    } catch (e) {
      logger.error('Failed to parse stored dashboards:', e)
      createDefaultDashboard()
    }
  } else {
    createDefaultDashboard()
  }
}

function createDefaultDashboard() {
  const defaultDashboard: Dashboard = {
    id: 'default',
    name: 'Main Dashboard',
    widgets: [
      {
        id: 'widget-1',
        type: 'system',
        title: 'System Monitor',
        x: 0,
        y: 0,
        width: 1,
        height: 350,
        props: {}
      },
      {
        id: 'widget-2',
        type: 'heatmap',
        title: 'Resource Heatmap',
        x: 1,
        y: 0,
        width: 2,
        height: 300,
        props: { height: 300 }
      },
      {
        id: 'widget-3',
        type: 'agents',
        title: 'Agent Activity',
        x: 0,
        y: 1,
        width: 2,
        height: 400,
        props: { height: 400 }
      }
    ],
    createdAt: Date.now(),
    updatedAt: Date.now()
  }

  availableDashboards.value = [defaultDashboard]
  saveDashboardsToStorage()
}

function loadDashboard() {
  const dashboard = availableDashboards.value.find(d => d.id === currentDashboardId.value)
  if (dashboard) {
    widgets.value = [...dashboard.widgets]
  }
}

function saveDashboard() {
  const dashboardIndex = availableDashboards.value.findIndex(d => d.id === currentDashboardId.value)
  if (dashboardIndex !== -1) {
    availableDashboards.value[dashboardIndex].widgets = [...widgets.value]
    availableDashboards.value[dashboardIndex].updatedAt = Date.now()
    saveDashboardsToStorage()
  }
  isEditMode.value = false
}

function saveDashboardsToStorage() {
  localStorage.setItem('autobot_dashboards', JSON.stringify(availableDashboards.value))
}

function createNewDashboard() {
  newDashboardName.value = ''
  newDashboardTemplate.value = 'blank'
  showNewDashboardModal.value = true
}

function confirmCreateDashboard() {
  const id = `dashboard-${Date.now()}`
  let templateWidgets: Widget[] = []

  // Apply template
  if (newDashboardTemplate.value === 'monitoring') {
    templateWidgets = [
      { id: 'w1', type: 'system', title: 'System Monitor', x: 0, y: 0, width: 1, height: 350, props: {} },
      { id: 'w2', type: 'heatmap', title: 'CPU Heatmap', x: 1, y: 0, width: 2, height: 300, props: { height: 300, metric: 'cpu' } }
    ]
  } else if (newDashboardTemplate.value === 'agents') {
    templateWidgets = [
      { id: 'w1', type: 'agents', title: 'Agent Activity', x: 0, y: 0, width: 3, height: 450, props: { height: 450 } }
    ]
  } else if (newDashboardTemplate.value === 'workflows') {
    templateWidgets = [
      { id: 'w1', type: 'workflow', title: 'Workflow View', x: 0, y: 0, width: 3, height: 500, props: { height: 500 } }
    ]
  }

  const newDashboard: Dashboard = {
    id,
    name: newDashboardName.value || 'New Dashboard',
    widgets: templateWidgets,
    createdAt: Date.now(),
    updatedAt: Date.now()
  }

  availableDashboards.value.push(newDashboard)
  saveDashboardsToStorage()
  currentDashboardId.value = id
  loadDashboard()
  showNewDashboardModal.value = false
}

// ============================================================================
// Methods - Widget Management
// ============================================================================

function toggleEditMode() {
  isEditMode.value = !isEditMode.value
}

function addWidget() {
  showAddWidgetModal.value = true
}

function confirmAddWidget(widgetDef: WidgetDefinition) {
  const newWidget: Widget = {
    id: `widget-${Date.now()}`,
    type: widgetDef.type,
    title: widgetDef.name,
    x: 0,
    y: widgets.value.length,
    width: widgetDef.defaultWidth,
    height: widgetDef.defaultHeight,
    props: { ...widgetDef.defaultProps },
    refreshKey: 0
  }

  widgets.value.push(newWidget)
  showAddWidgetModal.value = false
}

function removeWidget(widgetId: string) {
  widgets.value = widgets.value.filter(w => w.id !== widgetId)
}

function configureWidget(widget: Widget) {
  configWidget.value = { ...widget }
  showConfigModal.value = true
}

function saveWidgetConfig() {
  if (!configWidget.value) return

  const index = widgets.value.findIndex(w => w.id === configWidget.value!.id)
  if (index !== -1) {
    widgets.value[index] = { ...configWidget.value, refreshKey: (widgets.value[index].refreshKey || 0) + 1 }
  }
  showConfigModal.value = false
  configWidget.value = null
}

function resizeWidget(widget: Widget, action: 'expand' | 'shrink') {
  const index = widgets.value.findIndex(w => w.id === widget.id)
  if (index === -1) return

  if (action === 'expand') {
    widgets.value[index].width = Math.min(3, widgets.value[index].width + 1)
  } else {
    widgets.value[index].width = Math.max(1, widgets.value[index].width - 1)
  }
}

function getWidgetComponent(type: string) {
  return componentRegistry.value[type] || null
}

function getWidgetIcon(type: string): string {
  const def = availableWidgets.find(w => w.type === type)
  return def?.icon || 'fas fa-puzzle-piece'
}

function getWidgetStyle(widget: Widget) {
  return {
    gridColumn: `span ${widget.width}`,
    minHeight: `${widget.height}px`
  }
}

function hasHeightConfig(type: string): boolean {
  return ['heatmap', 'workflow', 'agents', 'architecture'].includes(type)
}

// ============================================================================
// Methods - Drag & Drop
// ============================================================================

function handleDragStart(event: DragEvent, widgetDef: WidgetDefinition) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('widget-type', widgetDef.type)
    event.dataTransfer.effectAllowed = 'copy'
  }
}

function handleWidgetDragStart(event: DragEvent, widget: Widget) {
  draggingWidgetId.value = widget.id
  if (event.dataTransfer) {
    event.dataTransfer.setData('widget-id', widget.id)
    event.dataTransfer.effectAllowed = 'move'
  }
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
}

function handleDrop(event: DragEvent) {
  event.preventDefault()

  const widgetType = event.dataTransfer?.getData('widget-type')
  const widgetId = event.dataTransfer?.getData('widget-id')

  if (widgetType) {
    // Adding new widget from palette
    const widgetDef = availableWidgets.find(w => w.type === widgetType)
    if (widgetDef) {
      confirmAddWidget(widgetDef)
    }
  } else if (widgetId) {
    // Reordering existing widget
    // Could implement position swapping here
    logger.debug('Widget dropped:', widgetId)
  }

  draggingWidgetId.value = null
}

function handleDragEnd() {
  draggingWidgetId.value = null
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  loadDashboards()
  loadDashboard()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.custom-dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-content h1 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.header-content h1 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  border-radius: 0.5rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-strong);
}

.action-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-on-primary);
}

.action-btn.primary {
  background: var(--color-primary);
  border-color: transparent;
  color: var(--text-on-primary);
}

.action-btn.primary:hover {
  box-shadow: var(--shadow-primary);
}

.dashboard-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.dashboard-selector select {
  padding: 0.625rem 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  color: var(--text-primary);
  font-size: 0.875rem;
  min-width: 150px;
}

.icon-btn {
  width: 36px;
  height: 36px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.icon-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Widget Palette */
.widget-palette {
  padding: 1rem 2rem;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.widget-palette h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
}

.palette-widgets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.palette-widget {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: grab;
  transition: all 0.2s;
}

.palette-widget:hover {
  border-color: var(--color-primary);
  background: var(--bg-tertiary);
}

.palette-widget i {
  color: var(--color-primary);
}

/* Dashboard Grid */
.dashboard-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
  padding: 1.5rem 2rem;
  overflow-y: auto;
}

.dashboard-grid.edit-mode {
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 49px,
    var(--border-default) 49px,
    var(--border-default) 50px
  ),
  repeating-linear-gradient(
    90deg,
    transparent,
    transparent 49px,
    var(--border-default) 49px,
    var(--border-default) 50px
  );
  background-size: 50px 50px;
}

/* Widget Container */
.widget-container {
  background: var(--bg-secondary);
  border-radius: 0.75rem;
  border: 1px solid var(--border-default);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: all 0.2s;
}

.widget-container:hover {
  border-color: var(--border-strong);
}

.widget-container.is-dragging {
  opacity: 0.5;
  border-color: var(--color-primary);
}

.edit-mode .widget-container {
  cursor: grab;
}

.edit-mode .widget-container:active {
  cursor: grabbing;
}

.widget-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.widget-header h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-primary);
}

.widget-header h3 i {
  color: var(--color-primary);
}

.widget-actions {
  display: flex;
  gap: 0.25rem;
}

.widget-actions button {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 0.375rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.widget-actions button:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.widget-actions button.remove-btn:hover {
  background: var(--color-error);
  color: var(--text-on-error);
}

.widget-content {
  flex: 1;
  overflow: auto;
}

/* Empty Dashboard */
.empty-dashboard {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem;
  text-align: center;
}

.empty-icon {
  width: 80px;
  height: 80px;
  background: var(--color-primary-bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  color: var(--color-primary);
  margin-bottom: 1.5rem;
}

.empty-dashboard h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.empty-dashboard p {
  color: var(--text-secondary);
  margin-bottom: 1.5rem;
}

/* Modals */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-secondary);
  border-radius: 0.75rem;
  border: 1px solid var(--border-default);
  width: 90%;
  max-width: 480px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-content.wide {
  max-width: 800px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.modal-header h4 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-header h4 i {
  color: var(--color-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0.25rem;
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.375rem;
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 0.625rem 0.75rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  background: var(--bg-primary);
  border-top: 1px solid var(--border-default);
}

/* Widget Gallery */
.widget-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}

.widget-option {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 0.75rem;
  padding: 1.5rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.widget-option:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
}

.widget-preview {
  width: 60px;
  height: 60px;
  background: var(--color-primary-bg);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1rem;
  font-size: 1.5rem;
  color: var(--color-primary);
}

.widget-option h5 {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}

.widget-option p {
  font-size: 0.75rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Transitions */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}

/* Responsive */
@media (max-width: 1024px) {
  .dashboard-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .dashboard-header {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
  }

  .header-actions {
    flex-wrap: wrap;
    justify-content: center;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
    padding: 1rem;
  }

  .widget-container {
    grid-column: span 1 !important;
  }
}
</style>
