<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="budget-policies-view view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">{{ t('budgetPolicies.title') }}</h2>
        <p class="page-subtitle">{{ t('budgetPolicies.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-primary" @click="openCreate">
          <Icon name="plus" />
          {{ t('budgetPolicies.newPolicy') }}
        </button>
        <button class="btn-action-secondary" :disabled="loading" @click="loadPolicies">
          <Icon name="sync-alt" :spin="loading" />
          {{ t('common.refresh') }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="btn-dismiss" :aria-label="t('common.dismiss')" @click="error = null">
        <Icon name="times" />
      </button>
    </div>

    <!-- Scope filter bar -->
    <div class="filter-bar">
      <div class="filter-group">
        <label class="filter-label">{{ t('budgetPolicies.scope') }}</label>
        <select v-model="filterScope" class="filter-select" @change="loadPolicies">
          <option value="">{{ t('budgetPolicies.scopeAll') }}</option>
          <option value="agent">{{ t('budgetPolicies.scopeAgent') }}</option>
          <option value="project">{{ t('budgetPolicies.scopeProject') }}</option>
          <option value="task">{{ t('budgetPolicies.scopeTask') }}</option>
          <option value="tenant">{{ t('budgetPolicies.scopeTenant') }}</option>
        </select>
      </div>
    </div>

    <!-- Policies table -->
    <div class="table-section">
      <div v-if="loading && policies.length === 0" class="loading-state">
        <Icon name="sync-alt" :spin="true" /> {{ t('budgetPolicies.loading') }}
      </div>

      <div v-else-if="!loading && policies.length === 0" class="empty-state">
        <Icon name="shield-alt" class="empty-icon" />
        <p>{{ t('budgetPolicies.empty') }}</p>
      </div>

      <table v-else class="data-table">
        <thead>
          <tr>
            <th>{{ t('budgetPolicies.colName') }}</th>
            <th>{{ t('budgetPolicies.colScope') }}</th>
            <th>{{ t('budgetPolicies.colScopeId') }}</th>
            <th>{{ t('budgetPolicies.colPeriod') }}</th>
            <th>{{ t('budgetPolicies.colThreshold') }}</th>
            <th>{{ t('budgetPolicies.colWarning') }}</th>
            <th>{{ t('budgetPolicies.colAction') }}</th>
            <th>{{ t('budgetPolicies.colStatus') }}</th>
            <th>{{ t('budgetPolicies.colActions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="policy in policies" :key="policy.id">
            <td class="name-cell">
              <span class="policy-name">{{ policy.name || '—' }}</span>
              <span v-if="policy.description" class="policy-desc">{{ policy.description }}</span>
            </td>
            <td>
              <span class="badge badge-scope">{{ policy.scope }}</span>
            </td>
            <td class="monospace">{{ policy.scope_id }}</td>
            <td>{{ policy.period }}</td>
            <td class="amount">${{ policy.threshold_usd.toFixed(2) }}</td>
            <td>{{ (policy.warning_pct * 100).toFixed(0) }}%</td>
            <td>
              <span class="badge" :class="actionBadgeClass(policy.action)">
                {{ policy.action }}
              </span>
            </td>
            <td>
              <span class="badge" :class="policy.enabled ? 'badge-active' : 'badge-inactive'">
                {{ policy.enabled ? t('budgetPolicies.statusEnabled') : t('budgetPolicies.statusDisabled') }}
              </span>
            </td>
            <td class="actions-cell">
              <button
                class="btn-icon btn-primary"
                :title="t('common.edit')"
                @click="openEdit(policy)"
              >
                <Icon name="edit" />
              </button>
              <button
                class="btn-icon btn-danger"
                :title="t('common.delete')"
                @click="confirmDelete(policy)"
              >
                <Icon name="trash" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Agent Pause Status section (admin only) -->
    <div v-if="isAdmin" class="section-card mt-6">
      <h3 class="section-title">{{ t('budgetPolicies.checkPauseTitle') }}</h3>
      <div class="agent-status-form">
        <input
          v-model="agentIdQuery"
          type="text"
          class="text-input"
:placeholder="t('budgetPolicies.agentIdPlaceholder')"
          @keydown.enter="checkAgentStatus"
        />
        <button class="btn-action-secondary" :disabled="!agentIdQuery.trim()" @click="checkAgentStatus">
          {{ t('budgetPolicies.checkStatus') }}
        </button>
      </div>

      <div v-if="agentStatus" class="agent-status-result">
        <div class="status-row">
          <span class="status-label">{{ t('budgetPolicies.labelAgent') }}</span>
          <span class="monospace">{{ agentStatus.agent_id }}</span>
        </div>
        <div class="status-row">
          <span class="status-label">{{ t('budgetPolicies.labelPaused') }}</span>
          <span :class="agentStatus.is_paused ? 'text-danger' : 'text-success'">
            {{ agentStatus.is_paused ? t('common.yes') : t('common.no') }}
          </span>
        </div>
        <div v-if="agentStatus.is_paused" class="status-row">
          <span class="status-label">{{ t('budgetPolicies.labelReason') }}</span>
          <span>{{ agentStatus.paused_reason || '—' }}</span>
        </div>
        <div v-if="agentStatus.is_paused && agentStatus.paused_at" class="status-row">
          <span class="status-label">{{ t('budgetPolicies.labelSince') }}</span>
          <span>{{ new Date(agentStatus.paused_at).toLocaleString() }}</span>
        </div>
        <button
          v-if="agentStatus.is_paused && isAdmin"
          class="btn-action-primary mt-2"
          :disabled="resuming"
          @click="resumeAgent(agentStatus.agent_id)"
        >
          <Icon name="play" :spin="resuming" />
          {{ t('budgetPolicies.resumeAgent') }}
        </button>
      </div>
    </div>

    <!-- Create / Edit Modal -->
    <BaseModal
      :model-value="showModal"
      :title="editTarget ? t('budgetPolicies.modalEditTitle') : t('budgetPolicies.modalNewTitle')"
      :close-label="t('common.close')"
      :width="560"
      @close="closeModal"
    >
      <div v-if="modalError" class="error-banner">
        <Icon name="exclamation-circle" />
        <span>{{ modalError }}</span>
      </div>

      <form id="budget-policy-form" class="modal-form" @submit.prevent="submitForm">
          <div class="form-row">
            <label class="form-label">{{ t('budgetPolicies.fieldName') }}</label>
            <input v-model="form.name" type="text" class="text-input" :placeholder="t('budgetPolicies.fieldNamePlaceholder')" />
          </div>
          <div class="form-row">
            <label class="form-label">{{ t('budgetPolicies.fieldDescription') }}</label>
            <input v-model="form.description" type="text" class="text-input" :placeholder="t('budgetPolicies.fieldDescriptionPlaceholder')" />
          </div>
          <div class="form-row two-col">
            <div>
              <label class="form-label">{{ t('budgetPolicies.fieldScope') }} <span class="required">*</span></label>
              <select v-model="form.scope" class="filter-select" required>
                <option value="agent">{{ t('budgetPolicies.scopeAgent') }}</option>
                <option value="project">{{ t('budgetPolicies.scopeProject') }}</option>
                <option value="task">{{ t('budgetPolicies.scopeTask') }}</option>
                <option value="tenant">{{ t('budgetPolicies.scopeTenant') }}</option>
              </select>
            </div>
            <div>
              <label class="form-label">{{ t('budgetPolicies.fieldScopeId') }} <span class="required">*</span></label>
              <input v-model="form.scope_id" type="text" class="text-input" :placeholder="t('budgetPolicies.fieldScopeIdPlaceholder')" required />
            </div>
          </div>
          <div class="form-row two-col">
            <div>
              <label class="form-label">{{ t('budgetPolicies.fieldPeriod') }} <span class="required">*</span></label>
              <select v-model="form.period" class="filter-select" required>
                <option value="hour">{{ t('budgetPolicies.periodHour') }}</option>
                <option value="day">{{ t('budgetPolicies.periodDay') }}</option>
                <option value="month">{{ t('budgetPolicies.periodMonth') }}</option>
              </select>
            </div>
            <div>
              <label class="form-label">{{ t('budgetPolicies.fieldThreshold') }} <span class="required">*</span></label>
              <input
                v-model.number="form.threshold_usd"
                type="number"
                min="0.01"
                step="0.01"
                class="text-input"
                required
              />
            </div>
          </div>
          <div class="form-row two-col">
            <div>
              <label class="form-label">{{ t('budgetPolicies.fieldWarning') }}</label>
              <input
                v-model.number="warningPct"
                type="number"
                min="0"
                max="100"
                step="1"
                class="text-input"
                placeholder="80"
              />
            </div>
            <div>
              <label class="form-label">{{ t('budgetPolicies.fieldAction') }} <span class="required">*</span></label>
              <select v-model="form.action" class="filter-select" required>
                <option value="alert">{{ t('budgetPolicies.actionAlert') }}</option>
                <option value="pause">{{ t('budgetPolicies.actionPause') }}</option>
                <option value="alert_then_pause">{{ t('budgetPolicies.actionAlertThenPause') }}</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <label class="checkbox-label">
              <input v-model="form.enabled" type="checkbox" class="checkbox-input" />
              {{ t('budgetPolicies.fieldEnabled') }}
            </label>
          </div>
      </form>

      <template #actions>
        <button type="button" class="btn-action-secondary" @click="closeModal">{{ t('common.cancel') }}</button>
        <button
          type="submit"
          form="budget-policy-form"
          class="btn-action-primary"
          :disabled="saving"
        >
          <Icon v-if="saving" name="sync-alt" :spin="true" />
          {{ editTarget ? t('budgetPolicies.saveChanges') : t('budgetPolicies.createPolicy') }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete confirm dialog -->
    <BaseModal
      :model-value="!!deleteTarget"
:title="t('budgetPolicies.deleteTitle')"
      :close-label="t('common.close')"
      :width="420"
      @close="deleteTarget = null"
    >
      <p v-if="deleteTarget" class="modal-body-text">
        {{ t('budgetPolicies.deleteConfirm') }}
        <strong>{{ deleteTarget.name || deleteTarget.id }}</strong>?
        {{ t('budgetPolicies.deleteUndone') }}
      </p>

      <template #actions>
        <button class="btn-action-secondary" @click="deleteTarget = null">{{ t('common.cancel') }}</button>
        <button class="btn-action-danger" :disabled="deleting" @click="doDelete">
          <Icon v-if="deleting" name="sync-alt" :spin="true" />
          {{ t('common.delete') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useUserStore } from '@/stores/useUserStore'
import Icon from '@/components/ui/Icon.vue'
import { BaseModal } from '@autobot/ui'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const logger = createLogger('BudgetPolicies')

// --- Types ---

interface BudgetPolicyResponse {
  id: string
  scope: string
  scope_id: string
  period: string
  threshold_usd: number
  warning_pct: number
  action: string
  enabled: boolean
  name: string
  description: string
  created_at: string
  updated_at: string
}

interface BudgetPolicyForm {
  scope: string
  scope_id: string
  period: string
  threshold_usd: number
  warning_pct: number
  action: string
  enabled: boolean
  name: string
  description: string
}

interface PauseStatusResponse {
  agent_id: string
  is_paused: boolean
  paused_reason: string | null
  paused_at: string | null
}

// --- State ---

const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

const policies = ref<BudgetPolicyResponse[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const filterScope = ref('')

const showModal = ref(false)
const editTarget = ref<BudgetPolicyResponse | null>(null)
const saving = ref(false)
const modalError = ref<string | null>(null)

const defaultForm = (): BudgetPolicyForm => ({
  scope: 'agent',
  scope_id: '',
  period: 'day',
  threshold_usd: 10,
  warning_pct: 0.8,
  action: 'alert_then_pause',
  enabled: true,
  name: '',
  description: '',
})

const form = ref<BudgetPolicyForm>(defaultForm())

// warning_pct is stored as 0–1 but the form shows 0–100
const warningPct = computed({
  get: () => Math.round(form.value.warning_pct * 100),
  set: (v: number) => { form.value.warning_pct = v / 100 },
})

const deleteTarget = ref<BudgetPolicyResponse | null>(null)
const deleting = ref(false)

const agentIdQuery = ref('')
const agentStatus = ref<PauseStatusResponse | null>(null)
const resuming = ref(false)

// --- Helpers ---

function actionBadgeClass(action: string): string {
  if (action === 'pause') return 'badge-danger'
  if (action === 'alert') return 'badge-warning'
  return 'badge-info'
}

// --- API ---

async function loadPolicies(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams()
    if (filterScope.value) params.set('scope', filterScope.value)
    const res = await fetchWithAuth(`${getBackendUrl()}/api/budget-policies?${params}`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    const data = await res.json() as { policies: BudgetPolicyResponse[]; count: number }
    policies.value = data.policies
  } catch (err) {
    logger.error('Failed to load budget policies:', err)
    error.value = err instanceof Error ? err.message : 'Failed to load policies'
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editTarget.value = null
  form.value = defaultForm()
  modalError.value = null
  showModal.value = true
}

function openEdit(policy: BudgetPolicyResponse): void {
  editTarget.value = policy
  form.value = {
    scope: policy.scope,
    scope_id: policy.scope_id,
    period: policy.period,
    threshold_usd: policy.threshold_usd,
    warning_pct: policy.warning_pct,
    action: policy.action,
    enabled: policy.enabled,
    name: policy.name,
    description: policy.description,
  }
  modalError.value = null
  showModal.value = true
}

function closeModal(): void {
  showModal.value = false
  editTarget.value = null
  modalError.value = null
}

async function submitForm(): Promise<void> {
  saving.value = true
  modalError.value = null
  const payload = { ...form.value }
  const url = editTarget.value
    ? `${getBackendUrl()}/api/budget-policies/${editTarget.value.id}`
    : `${getBackendUrl()}/api/budget-policies`
  const method = editTarget.value ? 'PATCH' : 'POST'
  try {
    const res = await fetchWithAuth(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    closeModal()
    await loadPolicies()
  } catch (err) {
    logger.error('Failed to save policy:', err)
    modalError.value = err instanceof Error ? err.message : 'Failed to save policy'
  } finally {
    saving.value = false
  }
}

function confirmDelete(policy: BudgetPolicyResponse): void {
  deleteTarget.value = policy
}

async function doDelete(): Promise<void> {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    const res = await fetchWithAuth(`${getBackendUrl()}/api/budget-policies/${deleteTarget.value.id}`, {
      method: 'DELETE',
    })
    if (!res.ok && res.status !== 204) {
      const body = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    deleteTarget.value = null
    await loadPolicies()
  } catch (err) {
    logger.error('Failed to delete policy:', err)
    error.value = err instanceof Error ? err.message : 'Failed to delete policy'
    deleteTarget.value = null
  } finally {
    deleting.value = false
  }
}

async function checkAgentStatus(): Promise<void> {
  const id = agentIdQuery.value.trim()
  if (!id) return
  agentStatus.value = null
  error.value = null
  try {
    const res = await fetchWithAuth(`${getBackendUrl()}/api/budget-policies/${id}/status`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    agentStatus.value = await res.json() as PauseStatusResponse
  } catch (err) {
    logger.error('Failed to fetch agent status:', err)
    error.value = err instanceof Error ? err.message : 'Failed to check agent status'
  }
}

async function resumeAgent(agentId: string): Promise<void> {
  resuming.value = true
  error.value = null
  try {
    const res = await fetchWithAuth(`${getBackendUrl()}/api/budget-policies/${agentId}/resume`, {
      method: 'POST',
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as { detail?: string }
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    agentStatus.value = null
    agentIdQuery.value = ''
    await loadPolicies()
  } catch (err) {
    logger.error('Failed to resume agent:', err)
    error.value = err instanceof Error ? err.message : 'Failed to resume agent'
  } finally {
    resuming.value = false
  }
}

onMounted(loadPolicies)
</script>

<style scoped>
.budget-policies-view {
  padding: var(--spacing-6);
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--spacing-6);
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: 600;
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-shrink: 0;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  background: var(--color-danger-bg, #fee2e2);
  color: var(--color-error, #dc2626);
  border: 1px solid var(--color-danger-border, #fca5a5);
  border-radius: var(--radius-md);
  padding: var(--spacing-3) var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  padding: var(--spacing-1);
}

.filter-bar {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
  align-items: flex-end;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.filter-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.table-section {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.loading-state,
.empty-state {
  padding: var(--spacing-12);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
}

.empty-icon {
  font-size: 2rem;
  opacity: 0.4;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.data-table thead {
  background: var(--color-bg-subtle);
}

.data-table th {
  padding: var(--spacing-3) var(--spacing-4);
  text-align: left;
  font-weight: 500;
  color: var(--text-secondary);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.data-table td {
  padding: var(--spacing-3) var(--spacing-4);
  vertical-align: middle;
  border-top: 1px solid var(--border-default);
}

.data-table tbody tr:hover {
  background: var(--color-bg-hover);
}

.name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.policy-name {
  font-weight: 500;
}

.policy-desc {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.monospace {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.amount {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: var(--text-xs);
  font-weight: 500;
  white-space: nowrap;
}

.badge-scope {
  background: var(--color-info-bg, #dbeafe);
  color: var(--color-info, #1d4ed8);
}

.badge-active {
  background: var(--color-success-bg, #dcfce7);
  color: var(--color-success, #16a34a);
}

.badge-inactive {
  background: var(--color-bg-subtle);
  color: var(--text-secondary);
}

.badge-danger {
  background: var(--color-danger-bg, #fee2e2);
  color: var(--color-error, #dc2626);
}

.badge-warning {
  background: var(--color-warning-bg, #fef9c3);
  color: var(--color-warning, #a16207);
}

.badge-info {
  background: var(--color-info-bg, #dbeafe);
  color: var(--color-info, #1d4ed8);
}

.actions-cell {
  display: flex;
  gap: var(--spacing-2);
}

.btn-action-primary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-action-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-action-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-bg-input);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-action-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-action-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-error, #dc2626);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
}

.btn-action-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  background: transparent;
  color: var(--text-secondary);
  transition: background 0.15s, color 0.15s;
}

.btn-icon:hover {
  background: var(--color-bg-hover);
  color: var(--text-primary);
}

.btn-icon.btn-primary:hover {
  background: var(--color-info-bg, #dbeafe);
  color: var(--color-info, #1d4ed8);
}

.btn-icon.btn-danger:hover {
  background: var(--color-danger-bg, #fee2e2);
  color: var(--color-error, #dc2626);
}

/* Agent pause status section */
.section-card {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  margin: 0 0 var(--spacing-4);
}

.agent-status-form {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
}

.text-input {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.agent-status-result {
  margin-top: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--color-bg-subtle);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.status-row {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
}

.status-label {
  font-weight: 500;
  min-width: 70px;
}

.text-danger { color: var(--color-error, #dc2626); font-weight: 500; }
.text-success { color: var(--color-success, #16a34a); font-weight: 500; }

.mt-2 { margin-top: var(--spacing-2); }
.mt-6 { margin-top: var(--spacing-6); }

/* Modal */
/* #10882: overlay/header/actions chrome now provided by @autobot/ui BaseModal. */
.modal-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.form-row.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-3);
}

.form-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.required {
  color: var(--color-error, #dc2626);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  cursor: pointer;
}

.checkbox-input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.modal-body-text {
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin: 0;
}
</style>
