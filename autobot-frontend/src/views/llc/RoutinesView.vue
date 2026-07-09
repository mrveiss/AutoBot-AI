<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  GH#11355: Company OS Routines console.

  Operator UI for the LLC routines backend (GH#8229, autobot-backend/llc/api/routines.py):
  list / create / edit / pause-resume / delete cron-scheduled routines, trigger an
  immediate run, and browse per-routine run history. Company-scoped via the :companyId
  route param so the LlcSidebar stays mounted (#10750 B3).
-->
<template>
  <div class="routines-view">
    <div class="routines-header">
      <h2 class="view-title">{{ $t('llc.routines.title') }}</h2>
      <button class="btn-primary" @click="openCreate">{{ $t('llc.routines.newRoutine') }}</button>
    </div>

    <div v-if="isLoading && routines.length === 0" class="state-msg">
      {{ $t('llc.routines.loading') }}
    </div>
    <div v-else-if="loadError" class="state-msg state-error">{{ loadError }}</div>
    <div v-else-if="routines.length === 0" class="state-msg">{{ $t('llc.routines.empty') }}</div>

    <div v-else class="routines-grid-wrapper">
      <table class="routines-grid">
        <thead>
          <tr>
            <th>{{ $t('llc.routines.colName') }}</th>
            <th>{{ $t('llc.routines.colSchedule') }}</th>
            <th>{{ $t('llc.routines.colProduces') }}</th>
            <th>{{ $t('llc.routines.colStatus') }}</th>
            <th>{{ $t('llc.routines.colLastFired') }}</th>
            <th>{{ $t('llc.routines.colActions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="routine in routines"
            :key="routine.id"
            class="routine-row"
            @click="openHistory(routine)"
          >
            <td class="routine-name">
              <span class="name-text">{{ routine.name }}</span>
              <span v-if="routine.description" class="name-desc">{{ routine.description }}</span>
            </td>
            <td><code class="cron">{{ routine.cron_schedule }}</code></td>
            <td>{{ producesLabel(routine.produces) }}</td>
            <td>
              <span class="status-badge" :class="`status-${routine.status}`">{{ statusLabel(routine.status) }}</span>
            </td>
            <td class="routine-fired">{{ formatDate(routine.last_fired_at) }}</td>
            <td class="routine-actions" @click.stop>
              <button
                class="btn-sm"
                :disabled="routine.status !== 'active' || triggering.has(routine.id)"
                :title="$t('llc.routines.triggerHint')"
                @click="triggerRoutine(routine)"
              >
                {{ triggering.has(routine.id) ? $t('llc.routines.triggering') : $t('llc.routines.trigger') }}
              </button>
              <button class="btn-sm" @click="openEdit(routine)">{{ $t('llc.routines.edit') }}</button>
              <button
                class="btn-sm"
                :disabled="mutating.has(routine.id)"
                @click="toggleStatus(routine)"
              >
                {{ routine.status === 'active' ? $t('llc.routines.pause') : $t('llc.routines.resume') }}
              </button>
              <button class="btn-sm btn-danger" :disabled="mutating.has(routine.id)" @click="removeRoutine(routine)">
                {{ $t('llc.routines.archive') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create / edit modal -->
    <div v-if="editorOpen" class="modal-overlay" @click.self="closeEditor">
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h3>{{ editingId ? $t('llc.routines.editTitle') : $t('llc.routines.createTitle') }}</h3>
          <button class="btn-close" :aria-label="$t('common.close')" @click="closeEditor">✕</button>
        </div>
        <form class="modal-body" @submit.prevent="submitEditor">
          <label class="field">
            <span>{{ $t('llc.routines.fieldName') }}</span>
            <input v-model="form.name" type="text" required :placeholder="$t('llc.routines.fieldNamePlaceholder')" />
          </label>
          <label class="field">
            <span>{{ $t('llc.routines.fieldDescription') }}</span>
            <input v-model="form.description" type="text" />
          </label>
          <label class="field">
            <span>{{ $t('llc.routines.fieldCron') }}</span>
            <input v-model="form.cron_schedule" type="text" required placeholder="0 9 * * 1-5" />
            <small class="field-hint">{{ $t('llc.routines.fieldCronHint') }}</small>
          </label>
          <label class="field">
            <span>{{ $t('llc.routines.fieldAssignee') }}</span>
            <select v-model="form.assignee_agent_id">
              <option :value="null">{{ $t('llc.routines.assigneeUnset') }}</option>
              <option v-for="agent in agents" :key="agent.id" :value="agent.id">{{ agent.name }}</option>
            </select>
          </label>
          <label class="field">
            <span>{{ $t('llc.routines.fieldProduces') }}</span>
            <select v-model="form.produces">
              <option value="new_work_item">{{ $t('llc.routines.producesNewWorkItem') }}</option>
              <option value="updates_recurring">{{ $t('llc.routines.producesUpdatesRecurring') }}</option>
            </select>
          </label>
          <label v-if="form.produces === 'new_work_item'" class="field">
            <span>{{ $t('llc.routines.fieldWorkItemTitle') }}</span>
            <input v-model="form.workItemTitle" type="text" :placeholder="$t('llc.routines.fieldWorkItemTitlePlaceholder')" />
          </label>
          <p v-if="editorError" class="state-error">{{ editorError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-sm" @click="closeEditor">{{ $t('common.cancel') }}</button>
            <button type="submit" class="btn-primary" :disabled="saving">
              {{ saving ? $t('llc.routines.saving') : $t('llc.routines.save') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Run history drawer -->
    <div v-if="selectedRoutine" class="drawer-overlay" @click.self="selectedRoutine = null">
      <div class="history-drawer" role="dialog" aria-modal="true">
        <div class="drawer-header">
          <h3>{{ $t('llc.routines.runHistoryTitle', { name: selectedRoutine.name }) }}</h3>
          <button class="btn-close" :aria-label="$t('common.close')" @click="selectedRoutine = null">✕</button>
        </div>
        <div v-if="historyLoading" class="state-msg">{{ $t('llc.routines.loadingRuns') }}</div>
        <div v-else-if="runHistory.length === 0" class="state-msg">{{ $t('llc.routines.noRuns') }}</div>
        <div v-else class="run-list">
          <div v-for="run in runHistory" :key="run.id" class="run-item">
            <span class="status-badge" :class="`status-run-${run.status}`">{{ runStatusLabel(run.status) }}</span>
            <span class="run-date">{{ formatDate(run.started_at ?? run.created_at) }}</span>
            <span v-if="run.finished_at" class="run-duration">
              {{ computeDuration(run.started_at, run.finished_at) }}
            </span>
            <span v-if="run.work_item_id" class="run-wi">{{ $t('llc.routines.producedWorkItem') }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ companyId?: string }>()

const logger = createLogger('RoutinesView')
const api = useApiClient()
const { t } = useI18n()

interface Routine {
  id: string
  company_id: string
  name: string
  description?: string | null
  cron_schedule: string
  assignee_agent_id?: string | null
  status: 'active' | 'paused' | 'archived'
  produces: 'new_work_item' | 'updates_recurring'
  work_item_template?: Record<string, unknown> | null
  last_fired_at?: string | null
}

interface RoutineRun {
  id: string
  routine_id: string
  work_item_id?: string | null
  status: string
  started_at?: string | null
  finished_at?: string | null
  created_at: string
}

interface Agent {
  id: string
  name: string
}

const routines = ref<Routine[]>([])
const agents = ref<Agent[]>([])
const isLoading = ref(false)
const loadError = ref('')
const triggering = ref<Set<string>>(new Set())
const mutating = ref<Set<string>>(new Set())

const selectedRoutine = ref<Routine | null>(null)
const runHistory = ref<RoutineRun[]>([])
const historyLoading = ref(false)

const editorOpen = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const editorError = ref('')
const form = ref({
  name: '',
  description: '',
  cron_schedule: '',
  assignee_agent_id: null as string | null,
  produces: 'new_work_item' as Routine['produces'],
  workItemTitle: '',
})

function formatDate(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function computeDuration(start?: string | null, end?: string | null) {
  if (!start || !end) return ''
  const s = Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function statusLabel(status: Routine['status']) {
  return t(`llc.routines.status_${status}`)
}

function producesLabel(produces: Routine['produces']) {
  return produces === 'new_work_item'
    ? t('llc.routines.producesNewWorkItem')
    : t('llc.routines.producesUpdatesRecurring')
}

// Backend run statuses: queued | running | succeeded | failed | completed
// (llc/scheduler/routine_scheduler.py). Fall back to the raw value for any
// status not yet mapped rather than showing an empty label.
const RUN_STATUS_KEYS = ['queued', 'running', 'succeeded', 'failed', 'completed']
function runStatusLabel(status: string) {
  return RUN_STATUS_KEYS.includes(status) ? t(`llc.routines.runStatus_${status}`) : status
}

async function loadRoutines() {
  if (!props.companyId) return
  isLoading.value = true
  loadError.value = ''
  try {
    routines.value = await api.get<Routine[]>(`/api/llc/companies/${props.companyId}/routines`)
  } catch (err) {
    logger.error('Failed to load routines', err)
    loadError.value = t('llc.routines.loadFailed')
  } finally {
    isLoading.value = false
  }
}

async function loadAgents() {
  if (!props.companyId) return
  try {
    agents.value = await api.get<Agent[]>(`/api/llc/agents?company_id=${props.companyId}`)
  } catch (err) {
    logger.error('Failed to load agents', err)
  }
}

function openCreate() {
  editingId.value = null
  editorError.value = ''
  form.value = {
    name: '',
    description: '',
    cron_schedule: '',
    assignee_agent_id: null,
    produces: 'new_work_item',
    workItemTitle: '',
  }
  editorOpen.value = true
}

function openEdit(routine: Routine) {
  editingId.value = routine.id
  editorError.value = ''
  form.value = {
    name: routine.name,
    description: routine.description ?? '',
    cron_schedule: routine.cron_schedule,
    assignee_agent_id: routine.assignee_agent_id ?? null,
    produces: routine.produces,
    workItemTitle: (routine.work_item_template?.title as string) ?? '',
  }
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
}

function buildPayload() {
  const f = form.value
  const payload: Record<string, unknown> = {
    name: f.name,
    description: f.description || null,
    cron_schedule: f.cron_schedule,
    assignee_agent_id: f.assignee_agent_id || null,
    produces: f.produces,
  }
  if (f.produces === 'new_work_item' && f.workItemTitle) {
    payload.work_item_template = { title: f.workItemTitle }
  }
  return payload
}

async function submitEditor() {
  if (!props.companyId) return
  saving.value = true
  editorError.value = ''
  try {
    if (editingId.value) {
      await api.patch<Routine>(`/api/llc/routines/${editingId.value}`, buildPayload())
    } else {
      await api.post<Routine>(`/api/llc/companies/${props.companyId}/routines`, buildPayload())
    }
    editorOpen.value = false
    await loadRoutines()
  } catch (err) {
    logger.error('Failed to save routine', err)
    editorError.value = t('llc.routines.saveFailed')
  } finally {
    saving.value = false
  }
}

async function triggerRoutine(routine: Routine) {
  const next = new Set(triggering.value)
  next.add(routine.id)
  triggering.value = next
  try {
    await api.post(`/api/llc/routines/${routine.id}/trigger`, {})
  } catch (err) {
    logger.error('Failed to trigger routine', err)
  } finally {
    const done = new Set(triggering.value)
    done.delete(routine.id)
    triggering.value = done
  }
}

async function toggleStatus(routine: Routine) {
  const nextStatus = routine.status === 'active' ? 'paused' : 'active'
  const next = new Set(mutating.value)
  next.add(routine.id)
  mutating.value = next
  try {
    await api.patch<Routine>(`/api/llc/routines/${routine.id}`, { status: nextStatus })
    await loadRoutines()
  } catch (err) {
    logger.error('Failed to toggle routine status', err)
  } finally {
    const done = new Set(mutating.value)
    done.delete(routine.id)
    mutating.value = done
  }
}

async function removeRoutine(routine: Routine) {
  if (!window.confirm(t('llc.routines.confirmArchive', { name: routine.name }))) return
  const next = new Set(mutating.value)
  next.add(routine.id)
  mutating.value = next
  try {
    await api.delete(`/api/llc/routines/${routine.id}`)
    await loadRoutines()
  } catch (err) {
    logger.error('Failed to delete routine', err)
  } finally {
    const done = new Set(mutating.value)
    done.delete(routine.id)
    mutating.value = done
  }
}

async function openHistory(routine: Routine) {
  selectedRoutine.value = routine
  historyLoading.value = true
  runHistory.value = []
  try {
    runHistory.value = await api.get<RoutineRun[]>(`/api/llc/routines/${routine.id}/runs`)
  } catch (err) {
    logger.error('Failed to load routine runs', err)
  } finally {
    historyLoading.value = false
  }
}

onMounted(() => {
  void loadRoutines()
  void loadAgents()
})
</script>

<style scoped>
/* Ember semantic tokens with fallbacks so non-ember themes stay legible. */
.routines-view {
  padding: 1rem 1.25rem;
}

.routines-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.view-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.state-msg {
  padding: 1.5rem 0;
  color: var(--text-muted, #6b7280);
}

.state-error {
  color: var(--color-danger, #b91c1c);
}

.routines-grid-wrapper {
  overflow-x: auto;
}

.routines-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.routines-grid th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted, #6b7280);
  border-bottom: 1px solid var(--border-default, #e5e7eb);
}

.routine-row {
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle, #f3f4f6);
}

.routine-row:hover {
  background: var(--bg-hover, #f9fafb);
}

.routines-grid td {
  padding: 0.625rem 0.75rem;
  color: var(--text-secondary, #374151);
  vertical-align: middle;
}

.routine-name {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.name-text {
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.name-desc {
  font-size: 0.75rem;
  color: var(--text-muted, #6b7280);
}

.cron {
  font-family: var(--font-mono, monospace);
  font-size: 0.8125rem;
  background: var(--bg-code, #f3f4f6);
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-sm, 4px);
}

.status-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 999px;
  background: var(--bg-muted, #f3f4f6);
  color: var(--text-secondary, #4b5563);
}

.status-active {
  background: var(--color-success-subtle, #dcfce7);
  color: var(--color-success-text, #15803d);
}

.status-paused {
  background: var(--color-warning-subtle, #fef3c7);
  color: var(--color-warning-text, #b45309);
}

.status-archived {
  background: var(--bg-muted, #e5e7eb);
  color: var(--text-muted, #6b7280);
}

.routine-actions {
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
}

.btn-primary {
  padding: 0.4375rem 0.875rem;
  font-size: 0.875rem;
  font-weight: 600;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: var(--color-accent, #c4651a);
  color: #fff;
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 0.25rem 0.625rem;
  font-size: 0.8125rem;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-input, #fff);
  color: var(--text-primary, #111827);
  cursor: pointer;
}

.btn-sm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-danger {
  color: var(--color-danger, #b91c1c);
  border-color: var(--color-danger-subtle, #fecaca);
}

.btn-close {
  border: none;
  background: none;
  font-size: 1rem;
  cursor: pointer;
  color: var(--text-muted, #6b7280);
}

.modal-overlay,
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  z-index: 50;
}

.modal-overlay {
  align-items: center;
  justify-content: center;
}

.modal {
  width: min(32rem, 92vw);
  background: var(--bg-surface, #fff);
  border-radius: var(--radius-lg, 12px);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header,
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
}

.modal-body {
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary, #4b5563);
}

.field input,
.field select {
  padding: 0.4375rem 0.5rem;
  font-size: 0.875rem;
  font-weight: 400;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-input, #fff);
  color: var(--text-primary, #111827);
}

.field-hint {
  font-weight: 400;
  font-size: 0.75rem;
  color: var(--text-muted, #6b7280);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.history-drawer {
  margin-left: auto;
  width: min(28rem, 92vw);
  height: 100%;
  background: var(--bg-surface, #fff);
  display: flex;
  flex-direction: column;
}

.run-list {
  padding: 0.75rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
}

.run-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-subtle, #f3f4f6);
  font-size: 0.8125rem;
}

.run-date {
  color: var(--text-secondary, #4b5563);
}

.run-duration,
.run-wi {
  color: var(--text-muted, #6b7280);
  font-size: 0.75rem;
}

.status-run-succeeded,
.status-run-completed {
  background: var(--color-success-subtle, #dcfce7);
  color: var(--color-success-text, #15803d);
}

.status-run-failed {
  background: var(--color-danger-subtle, #fee2e2);
  color: var(--color-danger, #b91c1c);
}

.status-run-running {
  background: var(--color-info-subtle, #dbeafe);
  color: var(--color-info-text, #1d4ed8);
}

.status-run-queued {
  background: var(--bg-muted, #f3f4f6);
  color: var(--text-secondary, #4b5563);
}
</style>
