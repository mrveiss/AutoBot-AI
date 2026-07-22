<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="approvals-inbox">
    <div class="inbox-header">
      <div class="header-left">
        <h2 class="view-title">{{ $t('llc.approvals.title') }}</h2>
        <span v-if="pendingCount > 0" class="pending-badge">{{ pendingCount }}</span>
      </div>
      <div class="header-tabs">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'pending' }"
          @click="activeTab = 'pending'"
        >
          {{ $t('llc.approvals.tabPending') }}
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'history' }"
          @click="activeTab = 'history'"
        >
          {{ $t('llc.approvals.tabHistory') }}
        </button>
      </div>
    </div>

    <div v-if="!companyId" class="state-msg">{{ $t('llc.approvals.selectCompany') }}</div>

    <template v-else>
      <!-- Filters -->
      <div class="inbox-filters">
        <select v-model="filters.type" class="filter-select">
          <option value="">{{ $t('llc.approvals.allTypes') }}</option>
          <option v-for="t in APPROVAL_TYPES" :key="t" :value="t">{{ formatType(t) }}</option>
        </select>
        <select v-if="activeTab === 'history'" v-model="filters.status" class="filter-select">
          <option value="">{{ $t('llc.approvals.allStatuses') }}</option>
          <option value="approved">{{ $t('llc.approvals.statusApproved') }}</option>
          <option value="rejected">{{ $t('llc.approvals.statusRejected') }}</option>
          <option value="changes_requested">{{ $t('llc.approvals.statusChangesRequested') }}</option>
        </select>
        <input v-model="filters.search" class="filter-search" :placeholder="$t('llc.approvals.searchPlaceholder')" type="text" />
      </div>

      <!-- Pending Tab -->
      <div v-if="activeTab === 'pending'" class="approval-list">
        <div v-if="isLoading" class="state-msg">{{ $t('llc.approvals.loading') }}</div>
        <div v-else-if="filteredPending.length === 0" class="state-msg">{{ $t('llc.approvals.noPending') }}</div>
        <div
          v-for="item in filteredPending"
          :key="item.id"
          class="approval-card"
        >
          <div class="card-header">
            <span class="type-badge" :class="`type-${item.type}`">{{ formatType(item.type) }}</span>
            <span class="card-meta">{{ $t('llc.approvals.requestedBy', { id: item.requested_by_agent_id }) }}</span>
            <span class="card-meta">{{ formatDate(item.created_at) }}</span>
          </div>

          <div class="payload-section">
            <button class="toggle-payload" @click="togglePayload(item.id)">
              {{ expandedPayloads.has(item.id) ? $t('llc.approvals.hidePayload') : $t('llc.approvals.showPayload') }}
            </button>
            <pre v-if="expandedPayloads.has(item.id)" class="payload-json">{{ formatJson(item.payload) }}</pre>
          </div>

          <div class="card-actions">
            <button
              class="btn-approve"
              :disabled="processing.has(item.id)"
              @click="decide(item.id, 'approved')"
            >
              {{ $t('llc.approvals.approve') }}
            </button>
            <button
              class="btn-reject"
              :disabled="processing.has(item.id)"
              @click="openDecisionNote(item.id, 'rejected')"
            >
              {{ $t('llc.approvals.reject') }}
            </button>
            <button
              class="btn-changes"
              :disabled="processing.has(item.id)"
              @click="openDecisionNote(item.id, 'changes_requested')"
            >
              {{ $t('llc.approvals.requestChanges') }}
            </button>
          </div>

          <div v-if="noteTarget?.id === item.id" class="note-form">
            <textarea
              v-model="decisionNote"
              class="note-textarea"
              :placeholder="$t('llc.approvals.notePlaceholder')"
              rows="3"
            />
            <div class="note-actions">
              <button class="btn-secondary" @click="noteTarget = null">{{ $t('llc.approvals.cancel') }}</button>
              <button
                class="btn-primary"
                :disabled="!decisionNote.trim() || processing.has(item.id)"
                @click="submitWithNote(item.id)"
              >
                {{ $t('llc.approvals.confirm') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- History Tab -->
      <div v-if="activeTab === 'history'" class="approval-list">
        <div v-if="isLoading" class="state-msg">{{ $t('llc.approvals.loading') }}</div>
        <div v-else-if="filteredHistory.length === 0" class="state-msg">{{ $t('llc.approvals.noHistory') }}</div>
        <div
          v-for="item in filteredHistory"
          :key="item.id"
          class="approval-card history-card"
        >
          <div class="card-header">
            <span class="type-badge" :class="`type-${item.type}`">{{ formatType(item.type) }}</span>
            <span class="status-badge" :class="`status-${item.status}`">{{ formatType(item.status) }}</span>
            <span class="card-meta">{{ $t('llc.approvals.decidedBy', { id: item.decided_by_agent_id ?? '—' }) }}</span>
            <span class="card-meta">{{ formatDate(item.decided_at ?? item.updated_at) }}</span>
          </div>
          <div class="payload-section">
            <button class="toggle-payload" @click="togglePayload(item.id)">
              {{ expandedPayloads.has(item.id) ? $t('llc.approvals.hidePayload') : $t('llc.approvals.showPayload') }}
            </button>
            <pre v-if="expandedPayloads.has(item.id)" class="payload-json">{{ formatJson(item.payload) }}</pre>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { formatDateTime } from '@/utils/formatHelpers'
import { useUserStore } from '@/stores/useUserStore'
import { useI18n } from 'vue-i18n'
import { useNotificationBus } from '@/composables/useNotificationBus'
import type { components } from '@/types/generated/api'

const logger = createLogger('ApprovalsInbox')
const api = useApiClient()
const route = useRoute()
const userStore = useUserStore()
const { t } = useI18n()
const { showToast } = useNotificationBus()

const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

const APPROVAL_TYPES = [
  'budget_increase', 'agent_spawn', 'external_api', 'code_deploy',
  'data_access', 'policy_change', 'contract_sign', 'hiring',
]

// #11367: derive from the generated OpenAPI schema.
type Approval = components['schemas']['ApprovalResponse']

const approvals = ref<Approval[]>([])
const isLoading = ref(false)
const activeTab = ref<'pending' | 'history'>('pending')
const expandedPayloads = ref<Set<string>>(new Set())
const processing = ref<Set<string>>(new Set())
const filters = ref({ type: '', status: '', search: '' })
const noteTarget = ref<{ id: string; decision: string } | null>(null)
const decisionNote = ref('')

const pendingItems = computed(() => approvals.value.filter(a => a.status === 'pending'))
const historyItems = computed(() => approvals.value.filter(a => a.status !== 'pending'))
const pendingCount = computed(() => pendingItems.value.length)

const filteredPending = computed(() => {
  return pendingItems.value.filter(a => {
    if (filters.value.type && a.type !== filters.value.type) return false
    if (filters.value.search) {
      const q = filters.value.search.toLowerCase()
      if (!a.type.includes(q) && !a.requested_by_agent_id.includes(q)) return false
    }
    return true
  })
})

const filteredHistory = computed(() => {
  return historyItems.value.filter(a => {
    if (filters.value.type && a.type !== filters.value.type) return false
    if (filters.value.status && a.status !== filters.value.status) return false
    if (filters.value.search) {
      const q = filters.value.search.toLowerCase()
      if (!a.type.includes(q)) return false
    }
    return true
  })
})

function formatType(val: string) {
  return val.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatDate(iso: string | null) {
  return formatDateTime(iso) || '—'
}

function formatJson(payload: Record<string, unknown>) {
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload)
  }
}

function togglePayload(id: string) {
  const next = new Set(expandedPayloads.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedPayloads.value = next
}

function openDecisionNote(id: string, decision: string) {
  noteTarget.value = { id, decision }
  decisionNote.value = ''
}

async function decide(id: string, decision: string, note?: string) {
  const next = new Set(processing.value)
  next.add(id)
  processing.value = next
  try {
    await api.post<unknown>(`/api/llc/approvals/${id}/decide`, {
      decision,
      decided_by_agent_id: userStore.currentUser?.id ?? undefined,
      ...(note ? { note } : {}),
    })
    await fetchApprovals()
  } catch (err) {
    logger.error('Decision failed', err)
    showToast(t('llcBrowser.approvals.decideError'), 'error')
  } finally {
    const s = new Set(processing.value)
    s.delete(id)
    processing.value = s
  }
}

async function submitWithNote(id: string) {
  if (!noteTarget.value || !decisionNote.value.trim()) return
  const { decision } = noteTarget.value
  noteTarget.value = null
  await decide(id, decision, decisionNote.value.trim())
  decisionNote.value = ''
}

async function fetchApprovals() {
  if (!companyId.value) return
  isLoading.value = true
  try {
    const data = await api.get<Approval[] | { items: Approval[] }>(
      `/api/llc/approvals?company_id=${companyId.value}`
    )
    approvals.value = Array.isArray(data) ? data : (data as { items: Approval[] }).items ?? []
  } catch (err) {
    logger.error('Failed to fetch approvals', err)
  } finally {
    isLoading.value = false
  }
}

let pollInterval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  if (!companyId.value) return
  fetchApprovals()
  pollInterval = setInterval(fetchApprovals, 30_000)
})

onUnmounted(() => {
  if (pollInterval !== null) clearInterval(pollInterval)
})
</script>

<style scoped>
.approvals-inbox {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
  gap: 1rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.inbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.view-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.pending-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  height: 1.5rem;
  padding: 0 0.4rem;
  background: var(--color-error);
  color: white;
  font-size: 0.75rem;
  font-weight: 700;
  border-radius: var(--radius-full);
}

.header-tabs {
  display: flex;
  gap: 0.25rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  overflow: hidden;
}

.tab-btn {
  padding: 0.375rem 1rem;
  font-size: 0.875rem;
  border: none;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
}

.tab-btn.active {
  background: var(--color-primary);
  color: white;
}

.inbox-filters {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.filter-select,
.filter-search {
  padding: 0.4rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.875rem;
}

.filter-search {
  flex: 1;
  min-width: 180px;
}

.approval-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  flex: 1;
}

.state-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-secondary);
}

.approval-card {
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1rem;
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.history-card {
  opacity: 0.85;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.card-meta {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.type-badge,
.status-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 500;
}

/* approval type + decision palette — theme-adaptive (GH#10868) */
.type-budget_increase { background: var(--badge-approval-budget_increase-bg); color: var(--badge-approval-budget_increase-fg); }
.type-agent_spawn { background: var(--badge-approval-agent_spawn-bg); color: var(--badge-approval-agent_spawn-fg); }
.type-external_api { background: var(--badge-approval-external_api-bg); color: var(--badge-approval-external_api-fg); }
.type-code_deploy { background: var(--badge-approval-code_deploy-bg); color: var(--badge-approval-code_deploy-fg); }
.type-data_access { background: var(--badge-approval-data_access-bg); color: var(--badge-approval-data_access-fg); }
.type-policy_change { background: var(--badge-approval-policy_change-bg); color: var(--badge-approval-policy_change-fg); }
.type-contract_sign { background: var(--badge-approval-contract_sign-bg); color: var(--badge-approval-contract_sign-fg); }
.type-hiring { background: var(--badge-approval-hiring-bg); color: var(--badge-approval-hiring-fg); }

.status-approved { background: var(--badge-approval-approved-bg); color: var(--badge-approval-approved-fg); }
.status-rejected { background: var(--badge-approval-rejected-bg); color: var(--badge-approval-rejected-fg); }
.status-changes_requested { background: var(--badge-approval-changes_requested-bg); color: var(--badge-approval-changes_requested-fg); }

.toggle-payload {
  font-size: 0.8rem;
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.25rem;
  background: var(--bg-elevated);
  cursor: pointer;
}

.payload-json {
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  padding: 0.75rem;
  font-size: 0.8rem;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.card-actions {
  display: flex;
  gap: 0.5rem;
}

.btn-approve,
.btn-reject,
.btn-changes {
  padding: 0.4rem 0.875rem;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-approve { background: var(--color-success); color: white; }
.btn-reject { background: var(--color-error); color: white; }
.btn-changes { background: var(--color-warning); color: white; }

.btn-approve:disabled,
.btn-reject:disabled,
.btn-changes:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.note-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-top: 1px solid var(--border-default);
  padding-top: 0.75rem;
}

.note-textarea {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.875rem;
  resize: vertical;
}

.note-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.btn-primary {
  padding: 0.4rem 1rem;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 0.4rem 1rem;
  background: var(--bg-surface);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}
</style>
