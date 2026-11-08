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
        <button v-if="loadError" @click="retryLoad" class="action-btn">
          <Icon name="redo" />
          {{ $t('views.customDashboard.retryLoad') }}
        </button>
        <button v-else @click="toggleEditMode" class="action-btn" :class="{ active: isEditMode }" :disabled="!loaded">
          <Icon :name="isEditMode ? 'check' : 'edit'" />
          {{ isEditMode ? $t('views.customDashboard.done') : $t('views.customDashboard.editLayout') }}
        </button>
        <button @click="addWidget" class="action-btn" v-if="isEditMode">
          <Icon name="plus" /> {{ $t('views.customDashboard.addWidget') }}
        </button>
        <button v-if="isEditMode" @click="resetLayout" class="action-btn">
          <Icon name="undo" /> {{ $t('views.customDashboard.resetLayout') }}
        </button>
        <button
          @click="saveDashboard"
          class="action-btn"
          :class="{ primary: isDirty }"
          :disabled="!isDirty || !loaded"
          :aria-label="isDirty ? $t('views.customDashboard.save') : $t('views.customDashboard.saved')"
        >
          <Icon name="save" />
          {{ isDirty ? $t('views.customDashboard.save') : $t('views.customDashboard.saved') }}
        </button>
        <div class="dashboard-selector">
          <select v-model="currentDashboardId" @change="loadDashboard(false)">
            <option v-for="dash in availableDashboards" :key="dash.id" :value="dash.id">
              {{ tr(dash.name) }}
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
    <div class="dashboard-body" @dragover.prevent="handleDragOver" @drop="handleDrop">
      <DashboardGrid v-model:widgets="widgets" :label-of="(w) => tr(w.title) || w.type" :editing="isEditMode" @update:widgets="isDirty = true">
        <template #widget="{ widget }">
          <div class="widget-header">
            <h3>
              <Icon :name="getWidgetIcon(widget.type)" />
              {{ tr(widget.title) }}
            </h3>
            <div class="widget-actions" v-if="isEditMode">
              <button @click="configureWidget(widget)" :title="$t('views.customDashboard.configure')" :aria-label="$t('views.customDashboard.configure')">
                <Icon name="cog" />
              </button>
              <button @click="removeWidget(widget.id)" class="remove-btn" :title="$t('views.customDashboard.remove')" :aria-label="$t('views.customDashboard.remove')">
                <Icon name="times" />
              </button>
            </div>
          </div>
          <div class="widget-content">
            <component
              :is="getWidgetComponent(widget.type)"
              v-bind="renderProps(widget)"
              :key="`${widget.id}-${widget.refreshKey}`"
            />
          </div>
        </template>
      </DashboardGrid>

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
    <BaseModal
      :model-value="showConfigModal"
      :title="$t('views.customDashboard.configureWidget')"
      :close-label="$t('common.close')"
      :width="480"
      @close="showConfigModal = false"
    >
      <template #title>
        <Icon name="cog" class="modal-icon" /> {{ $t('views.customDashboard.configureWidget') }}
      </template>
      <div class="modal-body" v-if="configWidget">
          <div class="form-group">
            <label>{{ $t('views.customDashboard.widgetTitle') }}</label>
            <input v-model="configWidget.title" type="text" :maxlength="MAX_TEXT" />
          </div>
          <div class="form-group">
            <label>{{ $t('views.customDashboard.refreshInterval') }}</label>
            <input v-model.number="configWidget.refreshInterval" type="number" min="5" :max="REFRESH_INTERVAL_MAX" />
          </div>
          <div class="form-group" v-if="hasHeightProp(configWidget.type)">
            <label>{{ $t('views.customDashboard.heightPx') }}</label>
            <input v-model.number="configWidget.height" type="number" :min="HEIGHT_MIN" :max="HEIGHT_MAX" />
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
      <template #actions>
        <button @click="showConfigModal = false" class="action-btn">{{ $t('views.customDashboard.cancel') }}</button>
        <button @click="saveWidgetConfig" class="action-btn primary">{{ $t('views.customDashboard.saveChanges') }}</button>
      </template>
    </BaseModal>

    <!-- New Dashboard Modal -->
    <BaseModal
      :model-value="showNewDashboardModal"
      :title="$t('views.customDashboard.createDashboard')"
      :close-label="$t('common.close')"
      :width="480"
      @close="showNewDashboardModal = false"
    >
      <template #title>
        <Icon name="plus-circle" class="modal-icon" /> {{ $t('views.customDashboard.createDashboard') }}
      </template>
      <div class="modal-body">
          <div class="form-group">
            <label>{{ $t('views.customDashboard.dashboardName') }}</label>
            <input v-model="newDashboardName" type="text" :maxlength="MAX_TEXT" :placeholder="$t('views.customDashboard.myDashboard')" />
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
      <template #actions>
        <button @click="showNewDashboardModal = false" class="action-btn">{{ $t('views.customDashboard.cancel') }}</button>
        <button @click="confirmCreateDashboard" class="action-btn primary">{{ $t('views.customDashboard.create') }}</button>
      </template>
    </BaseModal>

    <!-- Add Widget Modal -->
    <BaseModal
      :model-value="showAddWidgetModal"
      :title="$t('views.customDashboard.addWidgetTitle')"
      :close-label="$t('common.close')"
      :width="800"
      @close="showAddWidgetModal = false"
    >
      <template #title>
        <Icon name="plus-circle" class="modal-icon" /> {{ $t('views.customDashboard.addWidgetTitle') }}
      </template>
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
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
// Issue #1359: i18n string extraction

import { ref, computed, onMounted, shallowRef, markRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePollingJob } from '@/composables/usePollingJob'
import { useToast } from '@/composables/useToast'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { BaseModal } from '@autobot/ui'
import DashboardGrid from '@/components/dashboard/DashboardGrid.vue'
import { useDashboardLayout } from '@/composables/dashboard/useDashboardLayout'
import { i18nRef, displayText, fitText, HEIGHT_MAX, HEIGHT_MIN, MAX_DASHBOARDS, MAX_TEXT, MAX_WIDGETS, REFRESH_INTERVAL_MAX, type Dashboard, type DashboardLayout, type DashboardWidget } from '@/composables/dashboard/dashboardLayoutModel'
import { applyConfig, configDraft, hasHeightProp, renderProps } from '@/composables/dashboard/widgetConfig'
import { defaultHomeLayout, templateWidgets, WIDGET_DEFINITIONS, type WidgetDefinitionSpec } from '@/composables/dashboard/defaultDashboards'

// Import visualization components
import ResourceHeatmap from '@/components/visualizations/ResourceHeatmap.vue'
import WorkflowVisualization from '@/components/visualizations/WorkflowVisualization.vue'
import AgentActivityVisualization from '@/components/visualizations/AgentActivityVisualization.vue'
import SystemArchitectureDiagram from '@/components/visualizations/SystemArchitectureDiagram.vue'

const { t } = useI18n()
const tr = (s: string) => displayText(s, t)
const { showToast } = useToast()
const { confirm } = useConfirmDialog()
const { layout, loaded, loadError, load, save, reset } = useDashboardLayout('home', defaultHomeLayout)

// ============================================================================
// Types
// ============================================================================

// refreshKey is local and never persisted (stripped on save).
type Widget = DashboardWidget & { refreshKey?: number }

type WidgetDefinition = WidgetDefinitionSpec & { name: string; description: string }

// ============================================================================
// State
// ============================================================================

const isEditMode = ref(false)
const isDirty = ref(false)
const widgets = ref<Widget[]>([])
const availableDashboards = computed(() => layout.value.dashboards)
const currentDashboardId = computed({
  get: () => layout.value.activeId ?? '',
  // Fold the old dashboard's unsaved widgets in before activeId moves, so a switch never drops them.
  set: (id: string) => { layout.value = { ...(isDirty.value ? nextLayout() : layout.value), activeId: id } },
})
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

// Available widget definitions; names and descriptions translate at render.
const availableWidgetDefs = computed<WidgetDefinition[]>(() =>
  WIDGET_DEFINITIONS.map((d) => ({ ...d, name: t(d.nameKey), description: t(d.descriptionKey) })),
)

// ============================================================================
// Computed
// ============================================================================

const dashboardTitle = computed(() => {
  const dash = availableDashboards.value.find(d => d.id === currentDashboardId.value)
  return dash?.name ? tr(dash.name) : t('views.customDashboard.defaultTitle')
})

// ============================================================================
// Methods - Dashboard Management
// ============================================================================

/** `clean = false` on a switch: unsaved work is still unsaved, so Save stays enabled. */
function loadDashboard(clean = true) {
  const dashboard = availableDashboards.value.find(d => d.id === currentDashboardId.value)
  if (dashboard) widgets.value = dashboard.widgets.map(w => ({ ...w, props: { ...w.props } }))
  if (clean) isDirty.value = false
}

function nextLayout(): DashboardLayout {
  const widgetsToSave = widgets.value.map(({ refreshKey: _rk, ...w }) => w)
  return {
    ...layout.value,
    dashboards: layout.value.dashboards.map(d =>
      d.id === currentDashboardId.value ? { ...d, widgets: widgetsToSave, updatedAt: Date.now() } : d
    ),
  }
}

async function saveDashboard() {
  if (await save(nextLayout())) {
    isDirty.value = false
    isEditMode.value = false
    showToast(t('views.customDashboard.dashboardSaved'), 'success')
  } else {
    showToast(t('views.customDashboard.saveFailed'), 'error')
  }
}

async function resetLayout() {
  const ok = await confirm({
    title: t('views.customDashboard.resetLayout'),
    message: t('views.customDashboard.resetLayoutConfirm'),
  })
  if (!ok) return
  try {
    await reset()
  } catch {
    showToast(t('views.customDashboard.resetFailed'), 'error')
    return
  }
  loadDashboard() // widgets and layout both come from the same defaults() value
}

function createNewDashboard() {
  newDashboardName.value = ''
  newDashboardTemplate.value = 'blank'
  showNewDashboardModal.value = true
}

function confirmCreateDashboard() {
  if (layout.value.dashboards.length >= MAX_DASHBOARDS) { showToast(t('views.customDashboard.dashboardLimit', { max: MAX_DASHBOARDS }), 'error'); return }
  const id = `dashboard-${Date.now()}`
  const newDashboard: Dashboard = {
    id,
    name: fitText(newDashboardName.value) || i18nRef('views.customDashboard.newDashboard'),
    widgets: templateWidgets(newDashboardTemplate.value),
    createdAt: Date.now(),
    updatedAt: Date.now()
  }

  layout.value = { ...layout.value, dashboards: [...layout.value.dashboards, newDashboard] }
  currentDashboardId.value = id // through the setter, so the old dashboard's unsaved edits are kept
  loadDashboard()
  isDirty.value = true // not on the server yet: Save stays enabled until it is
  showNewDashboardModal.value = false
}

// ============================================================================
// Methods - Widget Management
// ============================================================================

function toggleEditMode() {
  // Editing the defaults shown after a failed load would overwrite the real saved layout.
  if (!loaded.value) return
  isEditMode.value = !isEditMode.value
}

async function loadLayout() {
  await load()
  if (loadError.value) showToast(t('views.customDashboard.loadFailed'), 'error')
  loadDashboard()
}

function retryLoad() {
  void loadLayout()
}

function addWidget() {
  showAddWidgetModal.value = true
}

function confirmAddWidget(widgetDef: WidgetDefinition) {
  if (widgets.value.length >= MAX_WIDGETS) { showToast(t('views.customDashboard.widgetLimit', { max: MAX_WIDGETS }), 'error'); return }
  const newWidget: Widget = {
    // #17020: a random id, so two widgets added in one tick never share layout, removal and :key.
    id: `widget-${crypto.randomUUID()}`,
    type: widgetDef.type,
    title: i18nRef(widgetDef.nameKey),
    span: widgetDef.defaultSpan,
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
  configWidget.value = configDraft(widget, tr)
  showConfigModal.value = true
}

function saveWidgetConfig() {
  if (!configWidget.value) return

  const index = widgets.value.findIndex(w => w.id === configWidget.value!.id)
  if (index !== -1) {
    const original = widgets.value[index]
    widgets.value[index] = { ...applyConfig(original, configWidget.value, tr), refreshKey: (original.refreshKey || 0) + 1 }
    isDirty.value = true
  }
  showConfigModal.value = false
  configWidget.value = null
}

function getWidgetComponent(type: string) {
  return componentRegistry.value[type] || null
}

function getWidgetIcon(type: string): IconName {
  const def = availableWidgetDefs.value.find(w => w.type === type)
  return def?.icon || 'puzzle-piece'
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

function handleDragOver(event: DragEvent) {
  event.preventDefault()
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  const widgetType = event.dataTransfer?.getData('widget-type')
  if (!widgetType) return // not a palette drag (grid reordering is handled by DashboardGrid)
  const widgetDef = availableWidgetDefs.value.find(w => w.type === widgetType)
  if (widgetDef) confirmAddWidget(widgetDef)
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

onMounted(async () => {
  await loadLayout()
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

/* Dashboard Grid (grid and widget chrome owned by DashboardGrid) */
.dashboard-body {
  flex: 1;
  padding: var(--spacing-6) var(--spacing-8);
  overflow-y: auto;
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
  background: var(--color-error-solid);
  color: var(--text-on-error);
}

.widget-content {
  flex: 1;
  overflow: auto;
}

/* Empty Dashboard */
.empty-dashboard {
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
/* #10882: overlay/header/footer chrome now provided by @autobot/ui BaseModal. */
.modal-icon {
  color: var(--color-primary);
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

  .dashboard-body {
    padding: var(--spacing-4);
  }
}
</style>
