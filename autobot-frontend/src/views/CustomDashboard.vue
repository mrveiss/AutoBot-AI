<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #1359: i18n string extraction -->
<template>
  <div class="custom-dashboard view-container-flex">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h1><Icon name="th-large" class="header-icon-svg" /> {{ dashboardTitle }}</h1>
        <p class="header-description">{{ $t('views.customDashboard.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button @click="toggleEditMode" class="action-btn" :class="{ active: isEditMode }">
          <Icon :name="isEditMode ? 'check' : 'edit'" />
          {{ isEditMode ? $t('views.customDashboard.done') : $t('views.customDashboard.editLayout') }}
        </button>
        <button @click="addWidget" class="action-btn" v-if="isEditMode">
          <Icon name="plus" />
          {{ $t('views.customDashboard.addWidget') }}
        </button>
        <button
          @click="saveDashboard"
          class="action-btn"
          :class="{ primary: isDirty }"
          :disabled="!isDirty"
          :aria-label="isDirty ? $t('views.customDashboard.save') : $t('views.customDashboard.saved')"
        >
          <Icon name="save" />
          {{ isDirty ? $t('views.customDashboard.save') : $t('views.customDashboard.saved') }}
        </button>
        <div class="dashboard-selector">
          <select v-model="currentDashboardId" @change="loadDashboard">
            <option v-for="dash in availableDashboards" :key="dash.id" :value="dash.id">
              {{ dash.name }}
            </option>
          </select>
          <button @click="createNewDashboard" class="icon-btn" :title="$t('views.customDashboard.createNewDashboard')" :aria-label="$t('views.customDashboard.createNewDashboard')">
            <Icon name="plus" />
          </button>
        </div>
      </div>
    </div>

    <!-- Widget Palette (Edit Mode) -->
    <transition name="slide-down">
      <div v-if="isEditMode" class="widget-palette">
        <h4>{{ $t('views.customDashboard.availableWidgets') }}</h4>
        <div class="palette-widgets">
          <div
            v-for="widget in availableWidgetDefs"
            :key="widget.type"
            class="palette-widget"
            draggable="true"
            @dragstart="handleDragStart($event, widget)"
          >
            <Icon :name="widget.icon" />
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
            <Icon :name="getWidgetIcon(widget.type)" />
            {{ widget.title }}
          </h3>
          <div class="widget-actions" v-if="isEditMode">
            <button @click="configureWidget(widget)" :title="$t('views.customDashboard.configure')" :aria-label="$t('views.customDashboard.configure')">
              <Icon name="cog" />
            </button>
            <button @click="resizeWidget(widget, 'expand')" :title="$t('views.customDashboard.expand')" :aria-label="$t('views.customDashboard.expand')">
              <Icon name="expand-alt" />
            </button>
            <button @click="resizeWidget(widget, 'shrink')" :title="$t('views.customDashboard.shrink')" :aria-label="$t('views.customDashboard.shrink')">
              <Icon name="compress-alt" />
            </button>
            <button @click="removeWidget(widget.id)" class="remove-btn" :title="$t('views.customDashboard.remove')" :aria-label="$t('views.customDashboard.remove')">
              <Icon name="times" />
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
          <Icon name="th-large" />
        </div>
        <h3>{{ $t('views.customDashboard.noWidgets') }}</h3>
        <p>{{ $t('views.customDashboard.noWidgetsHint') }}</p>
        <button @click="toggleEditMode" class="action-btn primary">
          <Icon name="plus" />
          {{ $t('views.customDashboard.addFirstWidget') }}
        </button>
      </div>
    </div>

    <!-- Widget Configuration Modal -->
    <div v-if="showConfigModal" class="modal-overlay" @click.self="showConfigModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4><Icon name="cog" class="modal-icon" /> {{ $t('views.customDashboard.configureWidget') }}</h4>
          <button
            @click="showConfigModal = false"
            class="close-btn"
            :aria-label="$t('common.close')"
            :title="$t('common.close')"
            type="button"
          >
            <Icon name="times" />
          </button>
        </div>
        <div class="modal-body" v-if="configWidget">
          <div class="form-group">
            <label>{{ $t('views.customDashboard.widgetTitle') }}</label>
            <input v-model="configWidget.title" type="text" />
          </div>
          <div class="form-group">
            <label>{{ $t('views.customDashboard.refreshInterval') }}</label>
            <input v-model.number="configWidget.refreshInterval" type="number" min="5" />
          </div>
          <div class="form-group" v-if="hasHeightConfig(configWidget.type)">
            <label>{{ $t('views.customDashboard.heightPx') }}</label>
            <input v-model.number="configWidget.props.height" type="number" min="200" />
          </div>
          <!-- Type-specific config options -->
          <div v-if="configWidget.type === 'heatmap'" class="form-group">
            <label>{{ $t('views.customDashboard.metric') }}</label>
            <select v-model="configWidget.props.metric">
              <option value="cpu">CPU</option>
              <option value="memory">{{ $t('views.customDashboard.memory') }}</option>
              <option value="disk">{{ $t('views.customDashboard.disk') }}</option>
              <option value="network">{{ $t('views.customDashboard.network') }}</option>
            </select>
          </div>
          <div v-if="configWidget.type === 'chart'" class="form-group">
            <label>{{ $t('views.customDashboard.chartType') }}</label>
            <select v-model="configWidget.props.chartType">
              <option value="line">{{ $t('views.customDashboard.line') }}</option>
              <option value="area">{{ $t('views.customDashboard.area') }}</option>
              <option value="bar">{{ $t('views.customDashboard.bar') }}</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="showConfigModal = false" class="action-btn">{{ $t('views.customDashboard.cancel') }}</button>
          <button @click="saveWidgetConfig" class="action-btn primary">{{ $t('views.customDashboard.saveChanges') }}</button>
        </div>
      </div>
    </div>

    <!-- New Dashboard Modal -->
    <div v-if="showNewDashboardModal" class="modal-overlay" @click.self="showNewDashboardModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4><Icon name="plus-circle" class="modal-icon" /> {{ $t('views.customDashboard.createDashboard') }}</h4>
          <button
            @click="showNewDashboardModal = false"
            class="close-btn"
            :aria-label="$t('common.close')"
            :title="$t('common.close')"
            type="button"
          >
            <Icon name="times" />
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>{{ $t('views.customDashboard.dashboardName') }}</label>
            <input v-model="newDashboardName" type="text" :placeholder="$t('views.customDashboard.myDashboard')" />
          </div>
          <div class="form-group">
            <label>{{ $t('views.customDashboard.template') }}</label>
            <select v-model="newDashboardTemplate">
              <option value="blank">{{ $t('views.customDashboard.blank') }}</option>
              <option value="monitoring">{{ $t('views.customDashboard.systemMonitoring') }}</option>
              <option value="agents">{{ $t('views.customDashboard.agentActivity') }}</option>
              <option value="workflows">{{ $t('views.customDashboard.workflows') }}</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="showNewDashboardModal = false" class="action-btn">{{ $t('views.customDashboard.cancel') }}</button>
          <button @click="confirmCreateDashboard" class="action-btn primary">{{ $t('views.customDashboard.create') }}</button>
        </div>
      </div>
    </div>

    <!-- Add Widget Modal -->
    <div v-if="showAddWidgetModal" class="modal-overlay" @click.self="showAddWidgetModal = false">
      <div class="modal-content wide">
        <div class="modal-header">
          <h4><Icon name="plus-circle" class="modal-icon" /> {{ $t('views.customDashboard.addWidgetTitle') }}</h4>
          <button
            @click="showAddWidgetModal = false"
            class="close-btn"
            :aria-label="$t('common.close')"
            :title="$t('common.close')"
            type="button"
          >
            <Icon name="times" />
          </button>
        </div>
        <div class="modal-body">
          <div class="widget-gallery">
            <div
              v-for="widget in availableWidgetDefs"
              :key="widget.type"
              class="widget-option"
              @click="confirmAddWidget(widget)"
            >
              <div class="widget-preview">
                <Icon :name="widget.icon" />
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
// Issue #1359: i18n string extraction

import { ref, computed, onMounted, shallowRef, markRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'
import { useToast } from '@/composables/useToast'
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'

// Import visualization components
import ResourceHeatmap from '@/components/visualizations/ResourceHeatmap.vue'
import WorkflowVisualization from '@/components/visualizations/WorkflowVisualization.vue'
import AgentActivityVisualization from '@/components/visualizations/AgentActivityVisualization.vue'
import SystemArchitectureDiagram from '@/components/visualizations/SystemArchitectureDiagram.vue'

const { t } = useI18n()
const logger = createLogger('CustomDashboard')
const { showToast } = useToast()

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
  icon: IconName
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
const isDirty = ref(false)
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

// Available widget definitions (computed for i18n reactivity)
const availableWidgetDefs = computed<WidgetDefinition[]>(() => [
  {
    type: 'heatmap',
    name: t('views.customDashboard.widgetHeatmap'),
    icon: 'th-large',
    description: t('views.customDashboard.widgetHeatmapDesc'),
    defaultWidth: 2,
    defaultHeight: 300,
    defaultProps: { height: 300, metric: 'cpu' }
  },
  {
    type: 'workflow',
    name: t('views.customDashboard.widgetWorkflow'),
    icon: 'project-diagram',
    description: t('views.customDashboard.widgetWorkflowDesc'),
    defaultWidth: 2,
    defaultHeight: 400,
    defaultProps: { height: 400 }
  },
  {
    type: 'agents',
    name: t('views.customDashboard.widgetAgents'),
    icon: 'robot',
    description: t('views.customDashboard.widgetAgentsDesc'),
    defaultWidth: 2,
    defaultHeight: 400,
    defaultProps: { height: 400 }
  },
  {
    type: 'architecture',
    name: t('views.customDashboard.widgetArchitecture'),
    icon: 'sitemap',
    description: t('views.customDashboard.widgetArchitectureDesc'),
    defaultWidth: 3,
    defaultHeight: 500,
    defaultProps: { height: 500 }
  },
])

// ============================================================================
// Computed
// ============================================================================

const dashboardTitle = computed(() => {
  const dash = availableDashboards.value.find(d => d.id === currentDashboardId.value)
  return dash?.name || t('views.customDashboard.defaultTitle')
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
  isDirty.value = false
}

function saveDashboard() {
  const dashboardIndex = availableDashboards.value.findIndex(d => d.id === currentDashboardId.value)
  if (dashboardIndex !== -1) {
    availableDashboards.value[dashboardIndex].widgets = [...widgets.value]
    availableDashboards.value[dashboardIndex].updatedAt = Date.now()
    saveDashboardsToStorage()
    isDirty.value = false
    showToast(t('views.customDashboard.dashboardSaved'), 'success')
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
  isDirty.value = false
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
  isDirty.value = true
  showAddWidgetModal.value = false
}

function removeWidget(widgetId: string) {
  widgets.value = widgets.value.filter(w => w.id !== widgetId)
  isDirty.value = true
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
    isDirty.value = true
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
  isDirty.value = true
}

function getWidgetComponent(type: string) {
  return componentRegistry.value[type] || null
}

function getWidgetIcon(type: string): IconName {
  const def = availableWidgetDefs.value.find(w => w.type === type)
  return def?.icon || 'puzzle-piece'
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
    const widgetDef = availableWidgetDefs.value.find(w => w.type === widgetType)
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
// Polling — auto-refresh widgets on a 30-second cycle
// ============================================================================

const { start: startDashboardPolling, stop: stopDashboardPolling } = usePollingJob<void>(
  async () => {
    // Tick all widgets so child components re-fetch their data
    widgets.value = widgets.value.map(w => ({ ...w, refreshKey: (w.refreshKey ?? 0) + 1 }))
  },
  { intervalMs: 30_000, maxAttempts: Number.MAX_SAFE_INTEGER }
)

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  loadDashboards()
  loadDashboard()
  startDashboardPolling('')
})

// expose stop for tests / external teardown
defineExpose({ stopDashboardPolling })
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.custom-dashboard {
  contain: layout style paint;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-6) var(--spacing-8);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-content h1 {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
}

.header-icon-svg {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-1);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-200);
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

.action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  pointer-events: none;
}

.dashboard-selector {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.dashboard-selector select {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
  min-width: 150px;
}

.icon-btn {
  width: 44px;
  height: 44px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-200);
}

.icon-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Widget Palette */
.widget-palette {
  padding: var(--spacing-4) var(--spacing-8);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.widget-palette h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-3);
}

.palette-widgets {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.palette-widget {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: grab;
  transition: all var(--duration-200);
}

.palette-widget:hover {
  border-color: var(--color-primary);
  background: var(--bg-tertiary);
}

.palette-widget svg {
  color: var(--color-primary);
}

/* Dashboard Grid */
.dashboard-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-6);
  padding: var(--spacing-6) var(--spacing-8);
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
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-default);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: all var(--duration-200);
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
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.widget-header h3 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-primary);
}

.widget-header h3 svg {
  color: var(--color-primary);
}

.widget-actions {
  display: flex;
  gap: var(--spacing-1);
}

.widget-actions button {
  width: 44px;
  height: 44px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-200);
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
  padding: var(--spacing-16);
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
  margin-bottom: var(--spacing-6);
}

.empty-dashboard h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.empty-dashboard p {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-6);
}

/* Modals */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
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
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.modal-header h4 {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.modal-icon {
  color: var(--color-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-1);
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-6);
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-group label {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1-5);
}

.form-group input,
.form-group select {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--color-primary);
}
.form-group input:focus-visible,
.form-group select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-primary);
  border-top: 1px solid var(--border-default);
}

/* Widget Gallery */
.widget-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--spacing-4);
}

.widget-option {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  text-align: center;
  cursor: pointer;
  transition: all var(--duration-200);
}

.widget-option:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
}

.widget-preview {
  width: 60px;
  height: 60px;
  background: var(--color-primary-bg);
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1rem;
  font-size: var(--text-2xl);
  color: var(--color-primary);
}

.widget-option h5 {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.widget-option p {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Transitions */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all var(--duration-300) var(--ease-out);
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
    gap: var(--spacing-4);
    padding: var(--spacing-4);
  }

  .header-actions {
    flex-wrap: wrap;
    justify-content: center;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
    padding: var(--spacing-4);
  }

  .widget-container {
    grid-column: span 1 !important;
  }
}
</style>
