<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Agent Org Chart Tab (#1405)
 *
 * Tree visualization of agent hierarchy with delegation controls.
 * Uses /autobot-api proxy to main backend.
 */

import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'
import OrgTreeNode from './OrgTreeNode.vue'

interface OrgNode {
  agent_id: string
  name: string
  org_role: string
  title: string | null
  capabilities: string | null
  direct_reports_count: number
  children: OrgNode[]
}

interface Delegation {
  id: string
  delegator_id: string
  assignee_id: string
  task_description: string
  status: string
  escalated_to: string | null
  created_at: string | null
}

interface ActivitySummary {
  manager_id: string
  total_delegated: number
  by_status: Record<string, number>
}

const authStore = useAuthStore()
const tree = ref<OrgNode[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedNode = ref<OrgNode | null>(null)
const directReports = ref<{ agent_id: string; name: string; org_role: string }[]>([])
const activity = ref<ActivitySummary | null>(null)
const delegations = ref<Delegation[]>([])
const showDelegateForm = ref(false)
const delegateForm = ref({ assignee_id: '', task_description: '' })
const delegateError = ref<string | null>(null)

const headers = computed(() => ({
  Authorization: `Bearer ${authStore.token}`,
  'Content-Type': 'application/json',
}))

async function fetchTree() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`${getBackendUrl()}/agents/org`, { headers: headers.value })
    if (!res.ok) throw new Error(`Failed to load org tree: ${res.status}`)
    tree.value = await res.json()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load org tree'
  } finally {
    loading.value = false
  }
}

async function selectNode(node: OrgNode) {
  selectedNode.value = node
  showDelegateForm.value = false
  delegateError.value = null
  try {
    const [reportsRes, activityRes, delegationsRes] = await Promise.all([
      fetch(`${getBackendUrl()}/agents/${node.agent_id}/reports`, { headers: headers.value }),
      fetch(`${getBackendUrl()}/agents/${node.agent_id}/activity`, { headers: headers.value }),
      fetch(`${getBackendUrl()}/agents/${node.agent_id}/delegations?role=delegator&limit=10`, {
        headers: headers.value,
      }),
    ])
    directReports.value = reportsRes.ok ? await reportsRes.json() : []
    activity.value = activityRes.ok ? await activityRes.json() : null
    delegations.value = delegationsRes.ok ? await delegationsRes.json() : []
  } catch {
    directReports.value = []
    activity.value = null
    delegations.value = []
  }
}

async function submitDelegation() {
  if (!selectedNode.value) return
  delegateError.value = null
  try {
    const res = await fetch(
      `${getBackendUrl()}/agents/${selectedNode.value.agent_id}/delegate`,
      {
        method: 'POST',
        headers: headers.value,
        body: JSON.stringify(delegateForm.value),
      },
    )
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `Failed: ${res.status}`)
    }
    delegateForm.value = { assignee_id: '', task_description: '' }
    showDelegateForm.value = false
    await selectNode(selectedNode.value)
  } catch (err) {
    delegateError.value = err instanceof Error ? err.message : 'Delegation failed'
  }
}

function roleBadgeClass(role: string): string {
  const map: Record<string, string> = {
    manager: 'badge-purple',
    coordinator: 'badge-blue',
    specialist: 'badge-green',
    worker: 'badge-gray',
  }
  return map[role] || 'badge-gray'
}

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    pending: 'badge-gray',
    accepted: 'badge-blue',
    in_progress: 'badge-blue',
    completed: 'badge-green',
    failed: 'badge-red',
    escalated: 'badge-orange',
  }
  return map[status] || 'badge-gray'
}

onMounted(fetchTree)
</script>

<template>
  <div class="org-chart-tab">
    <div v-if="error" class="error-banner">
      {{ error }}
      <button @click="error = null">{{ $t('agents.orgChartTab.dismiss') }}</button>
    </div>

    <div v-if="loading" class="loading">{{ $t('agents.orgChartTab.loadingOrgTree') }}</div>

    <div v-else class="org-layout">
      <!-- Tree panel -->
      <div class="tree-panel">
        <h3>{{ $t('agents.orgChartTab.agentHierarchy') }}</h3>
        <div v-if="tree.length === 0" class="empty-state">
          {{ $t('agents.orgChartTab.noAgentsRegisteredIn') }}
        </div>
        <ul v-else class="tree-list">
          <OrgTreeNode
            v-for="node in tree"
            :key="node.agent_id"
            :node="node"
            :depth="0"
            :selected-id="selectedNode?.agent_id ?? null"
            @select="selectNode($event)"
          />
        </ul>
      </div>

      <!-- Detail panel -->
      <div v-if="selectedNode" class="detail-panel">
        <div class="detail-header">
          <h3>{{ selectedNode.name }}</h3>
          <span :class="['role-badge', roleBadgeClass(selectedNode.org_role)]">{{
            selectedNode.org_role
          }}</span>
        </div>
        <p v-if="selectedNode.title" class="agent-title">{{ selectedNode.title }}</p>
        <p v-if="selectedNode.capabilities" class="capabilities">
          {{ selectedNode.capabilities }}
        </p>

        <div v-if="activity" class="activity-summary">
          <h4>{{ $t('agents.orgChartTab.delegationActivity') }}</h4>
          <div class="activity-grid">
            <div class="activity-stat">
              <span class="stat-value">{{ activity.total_delegated }}</span>
              <span class="stat-label">{{ $t('agents.orgChartTab.total') }}</span>
            </div>
            <div
              v-for="(count, status) in activity.by_status"
              :key="status"
              class="activity-stat"
            >
              <span class="stat-value">{{ count }}</span>
              <span class="stat-label">{{ status }}</span>
            </div>
          </div>
        </div>

        <div v-if="directReports.length" class="direct-reports">
          <h4>Direct Reports ({{ directReports.length }})</h4>
          <ul>
            <li v-for="r in directReports" :key="r.agent_id">
              <span :class="['role-badge', 'small', roleBadgeClass(r.org_role)]">{{
                r.org_role
              }}</span>
              {{ r.name }}
            </li>
          </ul>
        </div>

        <div v-if="directReports.length" class="delegate-section">
          <button
            v-if="!showDelegateForm"
            class="btn-primary"
            @click="showDelegateForm = true"
          >
            {{ $t('agents.orgChartTab.delegateTask') }}
          </button>
          <div v-else class="delegate-form">
            <h4>{{ $t('agents.orgChartTab.newDelegation') }}</h4>
            <div v-if="delegateError" class="error-inline">{{ delegateError }}</div>
            <div class="form-group">
              <label>{{ $t('agents.orgChartTab.assignTo') }}</label>
              <select v-model="delegateForm.assignee_id">
                <option value="" disabled>{{ $t('agents.orgChartTab.selectReport') }}</option>
                <option
                  v-for="r in directReports"
                  :key="r.agent_id"
                  :value="r.agent_id"
                >
                  {{ r.name }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label>{{ $t('agents.orgChartTab.task') }}</label>
              <textarea
                v-model="delegateForm.task_description"
                rows="3"
                placeholder="Describe the task..."
              />
            </div>
            <div class="form-actions">
              <button class="btn-primary" @click="submitDelegation">{{ $t('agents.orgChartTab.submit') }}</button>
              <button class="btn-cancel" @click="showDelegateForm = false">{{ $t('agents.orgChartTab.cancel') }}</button>
            </div>
          </div>
        </div>

        <div v-if="delegations.length" class="delegations-list">
          <h4>{{ $t('agents.orgChartTab.recentDelegations') }}</h4>
          <div v-for="d in delegations" :key="d.id" class="delegation-item">
            <div class="delegation-header">
              <span :class="['status-badge', statusBadgeClass(d.status)]">{{ d.status }}</span>
              <span class="delegation-assignee">&rarr; {{ d.assignee_id }}</span>
            </div>
            <p class="delegation-desc">{{ d.task_description }}</p>
            <span v-if="d.created_at" class="delegation-time">{{
              new Date(d.created_at).toLocaleString()
            }}</span>
          </div>
        </div>
      </div>

      <div v-else class="detail-panel empty-state">
        {{ $t('agents.orgChartTab.selectAnAgentTo') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.org-layout { display: grid; grid-template-columns: 380px 1fr; gap: 24px; }
.tree-panel, .detail-panel { background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 20px; }
.tree-panel h3, .detail-panel h3 { font-size: 18px; font-weight: 600; margin: 0 0 16px 0; color: var(--text-primary, #1a1a2e); }
.tree-list { list-style: none; padding: 0; margin: 0; max-height: 600px; overflow-y: auto; }
.tree-list li { padding: 10px 12px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.tree-list li:hover { background: #f3f4f6; }
.tree-list li.selected { background: #e0e7ff; }
.indent-1 { padding-left: 36px !important; }
.node-name { font-weight: 500; color: var(--text-primary, #1a1a2e); }
.reports-count { font-size: 11px; color: var(--text-secondary, #6b7280); margin-left: auto; }
.role-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
.role-badge.small { font-size: 9px; padding: 1px 6px; }
.badge-purple { background: #ede9fe; color: #7c3aed; }
.badge-blue { background: #dbeafe; color: #2563eb; }
.badge-green { background: #d1fae5; color: #059669; }
.badge-gray { background: #f3f4f6; color: #6b7280; }
.badge-red { background: #fee2e2; color: #dc2626; }
.badge-orange { background: #ffedd5; color: #ea580c; }
.agent-title { color: var(--text-secondary, #6b7280); font-size: 14px; margin: 4px 0 16px; }
.capabilities { font-size: 13px; color: var(--text-secondary, #6b7280); margin-bottom: 16px; line-height: 1.5; }
.activity-summary, .direct-reports, .delegate-section, .delegations-list { margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5e7eb; }
h4 { font-size: 14px; font-weight: 600; margin: 0 0 12px 0; color: var(--text-primary, #1a1a2e); }
.activity-grid { display: flex; gap: 16px; flex-wrap: wrap; }
.activity-stat { text-align: center; }
.activity-stat .stat-value { display: block; font-size: 20px; font-weight: 700; color: var(--primary, #6366f1); }
.activity-stat .stat-label { font-size: 11px; color: var(--text-secondary, #6b7280); text-transform: capitalize; }
.direct-reports ul { list-style: none; padding: 0; margin: 0; }
.direct-reports li { padding: 6px 0; display: flex; align-items: center; gap: 8px; font-size: 14px; }
.delegate-form { background: #f9fafb; border-radius: 8px; padding: 16px; }
.form-group { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.form-group label { font-size: 13px; font-weight: 500; color: var(--text-secondary, #6b7280); }
.form-group select, .form-group textarea { padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; font-family: inherit; }
.form-actions { display: flex; gap: 8px; }
.btn-primary { background: #6366f1; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; }
.btn-primary:hover { background: #4f46e5; }
.btn-cancel { background: #e5e7eb; color: #374151; border: none; padding: 8px 16px; border-radius: 6px; font-size: 14px; cursor: pointer; }
.delegation-item { padding: 10px 0; border-bottom: 1px solid #f3f4f6; }
.delegation-header { display: flex; align-items: center; gap: 8px; }
.status-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
.delegation-assignee { font-size: 13px; color: var(--text-secondary, #6b7280); }
.delegation-desc { font-size: 13px; margin: 4px 0 2px; color: var(--text-primary, #1a1a2e); }
.delegation-time { font-size: 11px; color: var(--text-secondary, #6b7280); }
.detail-panel.empty-state { display: flex; align-items: center; justify-content: center; min-height: 400px; color: var(--text-secondary, #6b7280); }
.empty-state { color: var(--text-secondary, #6b7280); text-align: center; padding: 40px; }
.error-banner { background: #fee2e2; border: 1px solid #ef4444; color: #b91c1c; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
.error-inline { background: #fee2e2; color: #b91c1c; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; }
.loading { text-align: center; color: var(--text-secondary, #6b7280); padding: 60px; }
.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
</style>
