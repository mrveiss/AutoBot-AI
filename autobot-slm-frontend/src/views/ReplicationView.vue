<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Replication Management View
 *
 * Manages Redis replication between nodes with Ansible orchestration (Issue #726 Phase 4).
 */

import { ref, computed, onMounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { useFleetStore } from '@/stores/fleet'
import { formatFleetDateTime } from '@/composables/useTimezone'
import { useToast } from '@/composables/useToast'
import type { Replication, ReplicationRequest } from '@/types/slm'
import { BaseAlert, BaseModal, createLogger } from '@autobot/ui'
import { useI18n } from 'vue-i18n'

const logger = createLogger('ReplicationView')
const { t } = useI18n()
const api = useSlmApi()
const ws = useSlmWebSocket()
const fleetStore = useFleetStore()
const { showToast } = useToast()

// State
const replications = ref<Replication[]>([])
const isLoading = ref(false)
const showCreateDialog = ref(false)
const isCreating = ref(false)
const selectedReplication = ref<Replication | null>(null)
const showDetailsModal = ref(false)
const syncVerifyResult = ref<{
  is_healthy: boolean
  checks: Array<{ name: string; status: string; message: string }>
  details: Record<string, unknown>
} | null>(null)
const isVerifying = ref(false)

// New replication form
const newReplication = ref<ReplicationRequest>({
  source_node_id: '',
  target_node_id: '',
  service_type: 'redis',
})

// Summary stats
const stats = computed(() => ({
  total: replications.value.length,
  active: replications.value.filter(r => r.status === 'active').length,
  syncing: replications.value.filter(r => r.status === 'syncing').length,
  pending: replications.value.filter(r => r.status === 'pending').length,
  failed: replications.value.filter(r => r.status === 'failed').length,
}))

// Filter nodes that have Redis role
const redisNodes = computed(() =>
  fleetStore.nodeList
    .filter(node => node.roles.includes('redis'))
    .map(node => ({
      value: node.node_id,
      label: `${node.hostname} (${node.ip_address})`,
      status: node.status,
    }))
)

// Available target nodes (exclude source)
const availableTargets = computed(() =>
  redisNodes.value.filter(n => n.value !== newReplication.value.source_node_id)
)

onMounted(async () => {
  await Promise.all([
    fetchReplications(),
    fleetStore.fetchNodes(),
  ])

  // Connect to WebSocket for real-time updates
  ws.connect()
  ws.subscribeAll()

  ws.onBackupStatus(() => {
    // Replication status updates come through this channel
    fetchReplications()
  })
})

// #15225: no explicit ws.disconnect() here. useSlmWebSocket() is a
// reference-counted singleton (consumerCount) shared with whatever else is
// on screen. #15225 embeds this view as a tab inside OrchestrationView.vue,
// which holds its own live connection via useOrchestrationManagement — an
// unconditional disconnect() on tab-switch would tear that down out from
// under the per-node tab too. The composable's own onUnmounted hook already
// decrements consumerCount and only calls the real doDisconnect() when this
// was the last consumer, so nothing further is needed here.

async function fetchReplications(): Promise<void> {
  isLoading.value = true
  try {
    replications.value = await api.getReplications()
  } catch (err) {
    logger.error('Failed to fetch replications:', err)
  } finally {
    isLoading.value = false
  }
}

async function handleCreateReplication(): Promise<void> {
  if (!newReplication.value.source_node_id || !newReplication.value.target_node_id) {
    return
  }

  isCreating.value = true
  try {
    await api.startReplication(newReplication.value)
    showCreateDialog.value = false
    resetForm()
    await fetchReplications()
  } catch (err) {
    logger.error('Failed to start replication:', err)
    showToast('Failed to start replication', 'error')
  } finally {
    isCreating.value = false
  }
}

async function handlePromote(replicationId: string): Promise<void> {
  if (!confirm(t('replicationView.areYouSureYouWantToPromote'))) {
    return
  }

  try {
    await api.promoteReplica(replicationId)
    await fetchReplications()
  } catch (err) {
    logger.error('Failed to promote replica:', err)
    showToast('Failed to promote replica', 'error')
  }
}

async function handleStop(replicationId: string): Promise<void> {
  if (!confirm(t('replicationView.areYouSureYouWantToStop'))) {
    return
  }

  try {
    await api.stopReplication(replicationId)
    await fetchReplications()
  } catch (err) {
    logger.error('Failed to stop replication:', err)
    showToast('Failed to stop replication', 'error')
  }
}

async function handleVerifySync(replication: Replication): Promise<void> {
  selectedReplication.value = replication
  showDetailsModal.value = true
  isVerifying.value = true
  syncVerifyResult.value = null

  try {
    syncVerifyResult.value = await api.verifyReplicationSync(replication.replication_id)
  } catch (err) {
    logger.error('Failed to verify sync:', err)
    syncVerifyResult.value = {
      is_healthy: false,
      checks: [{ name: 'verification', status: 'failed', message: String(err) }],
      details: {},
    }
  } finally {
    isVerifying.value = false
  }
}

function resetForm(): void {
  newReplication.value = {
    source_node_id: '',
    target_node_id: '',
    service_type: 'redis',
  }
}

function showDetails(replication: Replication): void {
  selectedReplication.value = replication
  syncVerifyResult.value = null
  showDetailsModal.value = true
}

function closeDetails(): void {
  showDetailsModal.value = false
  selectedReplication.value = null
  syncVerifyResult.value = null
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'active': return 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg'
    case 'syncing': return 'bg-autobot-pill-info-bg text-autobot-pill-info-fg'
    case 'pending': return 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg'
    case 'failed': return 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
    case 'stopped': return 'bg-autobot-bg-tertiary text-autobot-text-primary'
    default: return 'bg-autobot-bg-tertiary text-autobot-text-primary'
  }
}

function formatLag(lagBytes: number): string {
  if (lagBytes === 0) return '0 B (in sync)'
  if (lagBytes < 1024) return `${lagBytes} B`
  if (lagBytes < 1024 * 1024) return `${(lagBytes / 1024).toFixed(1)} KB`
  return `${(lagBytes / (1024 * 1024)).toFixed(2)} MB`
}

function getNodeHostname(nodeId: string): string {
  const node = fleetStore.getNode(nodeId)
  return node?.hostname || nodeId
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-autobot-text-primary">{{ $t('replicationView.redisReplication') }}</h1>
        <p class="text-sm text-autobot-text-tertiary mt-1">
          {{ $t('replicationView.manageRedisMasterReplica') }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="fetchReplications"
          :disabled="isLoading"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg :class="['w-4 h-4', isLoading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ $t('replicationView.refresh') }}
        </button>
        <button
          @click="showCreateDialog = true"
          :disabled="redisNodes.length < 2"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          {{ $t('replicationView.newReplication') }}
        </button>
      </div>
    </div>

    <!-- Warning if less than 2 Redis nodes -->
    <BaseAlert
      v-if="redisNodes.length < 2"
      variant="warning"
      class="mb-6"
      :message="$t('replicationView.atLeast2NodesWithThe', { count: redisNodes.length })"
    />

    <!-- Summary Stats -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.total') }}</p>
            <p class="text-2xl font-bold text-autobot-text-primary">{{ stats.total }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-autobot-bg-tertiary flex items-center justify-center">
            <svg class="w-5 h-5 text-autobot-text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.active') }}</p>
            <p class="text-2xl font-bold text-autobot-success">{{ stats.active }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-autobot-pill-ok-bg flex items-center justify-center">
            <svg class="w-5 h-5 text-autobot-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.syncing') }}</p>
            <p class="text-2xl font-bold text-autobot-text-link">{{ stats.syncing }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-autobot-pill-info-bg flex items-center justify-center">
            <svg class="w-5 h-5 text-autobot-text-link" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.pending') }}</p>
            <p class="text-2xl font-bold text-autobot-warning">{{ stats.pending }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-autobot-pill-warn-bg flex items-center justify-center">
            <svg class="w-5 h-5 text-autobot-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.failed') }}</p>
            <p class="text-2xl font-bold text-autobot-error">{{ stats.failed }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-autobot-pill-bad-bg flex items-center justify-center">
            <svg class="w-5 h-5 text-autobot-error" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Replications Table -->
    <div class="card overflow-hidden">
      <div class="px-6 py-4 border-b border-autobot-border">
        <h2 class="text-lg font-semibold">{{ $t('replicationView.replicationLinks') }}</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-autobot-border">
          <thead class="bg-autobot-bg-secondary">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('replicationView.status') }}</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('replicationView.sourcePrimary') }}</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('replicationView.targetReplica') }}</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('replicationView.service') }}</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('replicationView.lag') }}</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('replicationView.started') }}</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('replicationView.actions') }}</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-autobot-border">
            <tr v-for="replication in replications" :key="replication.replication_id" class="hover:bg-autobot-bg-hover">
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(replication.status)]">
                  {{ replication.status }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full bg-autobot-primary" :title="$t('replicationView.primary')"></div>
                  <span class="text-sm font-medium text-autobot-text-primary">{{ getNodeHostname(replication.source_node_id) }}</span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full bg-autobot-info-solid" :title="$t('replicationView.replica')"></div>
                  <span class="text-sm font-medium text-autobot-text-primary">{{ getNodeHostname(replication.target_node_id) }}</span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-0.5 text-xs font-medium bg-autobot-pill-bad-bg text-autobot-pill-bad-fg rounded-sm">
                  {{ replication.service_type }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="[
                  'text-sm',
                  replication.lag_bytes === 0 ? 'text-autobot-success' :
                  replication.lag_bytes < 1024 * 1024 ? 'text-autobot-warning' : 'text-autobot-error'
                ]">
                  {{ formatLag(replication.lag_bytes) }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-autobot-text-tertiary">
                {{ formatFleetDateTime(replication.started_at, '-') }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right">
                <div class="flex items-center justify-end gap-2">
                  <!-- Verify Sync -->
                  <button
                    @click="handleVerifySync(replication)"
                    class="text-autobot-text-link hover:text-autobot-text-link"
                    :title="$t('replicationView.verifySyncStatus')"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </button>

                  <!-- View Details -->
                  <button
                    @click="showDetails(replication)"
                    class="text-autobot-text-secondary hover:text-autobot-text-primary"
                    :title="$t('replicationView.viewDetails')"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </button>

                  <!-- Promote Replica (when active) -->
                  <button
                    v-if="replication.status === 'active'"
                    @click="handlePromote(replication.replication_id)"
                    class="text-autobot-success hover:text-autobot-pill-ok-fg"
                    :title="$t('replicationView.promoteToPrimary2')"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
                    </svg>
                  </button>

                  <!-- Stop Replication (when active/syncing) -->
                  <button
                    v-if="['active', 'syncing'].includes(replication.status)"
                    @click="handleStop(replication.replication_id)"
                    class="text-autobot-error hover:text-autobot-pill-bad-fg"
                    :title="$t('replicationView.stopReplication')"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="replications.length === 0 && !isLoading">
              <td colspan="7" class="px-6 py-12 text-center text-autobot-text-tertiary">
                <svg class="w-12 h-12 mx-auto text-autobot-text-tertiary mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
                <p>{{ $t('replicationView.noReplicationsConfiguredYet') }}</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
    </div>

    <!-- Create Dialog -->
    <BaseModal
      v-model="showCreateDialog"
      :title="$t('replicationView.newReplication')"
      width="32rem"
      :close-label="$t('replicationView.close')"
    >
      <template #subtitle>
        {{ $t('replicationView.setUpRedisMaster') }}
      </template>
      <div class="space-y-4">
        <!-- Source Node Selection -->
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">
            <span class="flex items-center gap-2">
              <div class="w-3 h-3 rounded-full bg-autobot-primary"></div>
              {{ $t('replicationView.sourceNodePrimaryMaster') }}
            </span>
          </label>
          <select
            v-model="newReplication.source_node_id"
            class="w-full px-3 py-2 border border-autobot-border-strong rounded-md focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="">{{ $t('replicationView.selectPrimaryNode') }}</option>
            <option v-for="opt in redisNodes" :key="opt.value" :value="opt.value">
              {{ opt.label }} - {{ opt.status }}
            </option>
          </select>
        </div>

        <!-- Target Node Selection -->
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">
            <span class="flex items-center gap-2">
              <div class="w-3 h-3 rounded-full bg-autobot-info-solid"></div>
              {{ $t('replicationView.targetNodeReplica') }}
            </span>
          </label>
          <select
            v-model="newReplication.target_node_id"
            :disabled="!newReplication.source_node_id"
            class="w-full px-3 py-2 border border-autobot-border-strong rounded-md focus:ring-primary-500 focus:border-primary-500 disabled:bg-autobot-bg-tertiary"
          >
            <option value="">{{ $t('replicationView.selectReplicaNode') }}</option>
            <option v-for="opt in availableTargets" :key="opt.value" :value="opt.value">
              {{ opt.label }} - {{ opt.status }}
            </option>
          </select>
        </div>

        <!-- Service Type -->
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('replicationView.serviceType') }}</label>
          <select
            v-model="newReplication.service_type"
            class="w-full px-3 py-2 border border-autobot-border-strong rounded-md focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="redis">{{ $t('replicationView.redis') }}</option>
          </select>
          <p class="text-xs text-autobot-text-tertiary mt-1">{{ $t('replicationView.currentlyOnlyRedisReplication') }}</p>
        </div>

        <!-- Info Box -->
        <BaseAlert variant="info" size="compact">
          {{ $t('replicationView.thisWillConfigureThe') }}
          <code>REPLICAOF</code> {{ $t('replicationView.commandViaAnsibleThe') }}
        </BaseAlert>
      </div>
      <template #actions>
        <button
          @click="showCreateDialog = false; resetForm()"
          class="px-4 py-2 text-sm font-medium text-autobot-text-secondary bg-autobot-bg-tertiary rounded-md hover:bg-autobot-bg-active"
        >
          {{ $t('replicationView.cancel') }}
        </button>
        <button
          @click="handleCreateReplication"
          :disabled="!newReplication.source_node_id || !newReplication.target_node_id || isCreating"
          class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <div v-if="isCreating" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
          {{ $t('replicationView.startReplication') }}
        </button>
      </template>
    </BaseModal>

    <!-- Details Modal -->
    <BaseModal
      v-if="selectedReplication"
      :model-value="showDetailsModal"
      :title="$t('replicationView.replicationDetails')"
      width="42rem"
      :close-label="$t('replicationView.close')"
      @close="closeDetails"
    >
      <template #subtitle>
        <span v-if="selectedReplication" :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(selectedReplication.status)]">
          {{ selectedReplication.status }}
        </span>
      </template>
      <!-- Node Info -->
      <div class="grid grid-cols-2 gap-4 mb-6">
        <div class="p-4 bg-autobot-illus-2-tint rounded-lg">
          <p class="text-sm font-medium text-autobot-text-primary mb-1">{{ $t('replicationView.sourcePrimary') }}</p>
          <p class="text-lg font-semibold text-autobot-text-primary">{{ getNodeHostname(selectedReplication.source_node_id) }}</p>
          <p class="text-xs text-autobot-text-primary mt-1">{{ selectedReplication.source_node_id }}</p>
        </div>
        <div class="p-4 bg-autobot-info-bg rounded-lg">
          <p class="text-sm font-medium text-autobot-pill-info-fg mb-1">{{ $t('replicationView.targetReplica') }}</p>
          <p class="text-lg font-semibold text-autobot-pill-info-fg">{{ getNodeHostname(selectedReplication.target_node_id) }}</p>
          <p class="text-xs text-autobot-info mt-1">{{ selectedReplication.target_node_id }}</p>
        </div>
      </div>

      <!-- Lag & Sync Info -->
      <div class="mb-6 p-4 border border-autobot-border rounded-lg">
        <div class="flex items-center justify-between mb-2">
          <p class="text-sm font-medium text-autobot-text-secondary">{{ $t('replicationView.replicationLag') }}</p>
          <span :class="[
            'text-lg font-bold',
            selectedReplication.lag_bytes === 0 ? 'text-autobot-success' :
            selectedReplication.lag_bytes < 1024 * 1024 ? 'text-autobot-warning' : 'text-autobot-error'
          ]">
            {{ formatLag(selectedReplication.lag_bytes) }}
          </span>
        </div>
        <div v-if="selectedReplication.sync_position" class="text-xs text-autobot-text-tertiary">{{ $t('replicationView.syncPositionValue0', { value0: selectedReplication.sync_position }) }}</div>
      </div>

      <!-- Sync Verification Results -->
      <div v-if="isVerifying" class="mb-6 flex items-center justify-center py-8">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
        <span class="ml-3 text-autobot-text-secondary">{{ $t('replicationView.verifyingSyncStatus') }}</span>
      </div>

      <div v-else-if="syncVerifyResult" class="mb-6">
        <div class="flex items-center gap-2 mb-3">
          <svg
            :class="['w-5 h-5', syncVerifyResult.is_healthy ? 'text-autobot-success' : 'text-autobot-error']"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path
              v-if="syncVerifyResult.is_healthy"
              stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
            <path
              v-else
              stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p :class="['font-medium', syncVerifyResult.is_healthy ? 'text-autobot-pill-ok-fg' : 'text-autobot-pill-bad-fg']">
            {{ syncVerifyResult.is_healthy ? $t('replicationView.replicationIsHealthyAndInSync') : $t('replicationView.replicationIssuesDetected') }}
          </p>
        </div>

        <!-- Checks -->
        <div class="space-y-2">
          <div
            v-for="check in syncVerifyResult.checks"
            :key="check.name"
            class="flex items-center gap-2 p-2 rounded-md"
            :class="check.status === 'passed' ? 'bg-autobot-success-bg' : check.status === 'failed' ? 'bg-autobot-pill-bad-bg' : 'bg-autobot-bg-secondary'"
          >
            <svg
              :class="[
                'w-4 h-4',
                check.status === 'passed' ? 'text-autobot-success' :
                check.status === 'failed' ? 'text-autobot-error' : 'text-autobot-text-tertiary'
              ]"
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path
                v-if="check.status === 'passed'"
                stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"
              />
              <path
                v-else-if="check.status === 'failed'"
                stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"
              />
              <path
                v-else
                stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01"
              />
            </svg>
            <span class="text-sm font-medium">{{ check.name }}:</span>
            <span class="text-sm text-autobot-text-secondary">{{ check.message }}</span>
          </div>
        </div>
      </div>

      <!-- Timestamps -->
      <div class="grid grid-cols-2 gap-4 mb-6">
        <div>
          <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.created') }}</p>
          <p class="text-sm font-medium">{{ formatFleetDateTime(selectedReplication.created_at, '-') }}</p>
        </div>
        <div>
          <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.started') }}</p>
          <p class="text-sm font-medium">{{ formatFleetDateTime(selectedReplication.started_at, '-') }}</p>
        </div>
        <div v-if="selectedReplication.completed_at">
          <p class="text-sm text-autobot-text-tertiary">{{ $t('replicationView.completed') }}</p>
          <p class="text-sm font-medium">{{ formatFleetDateTime(selectedReplication.completed_at, '-') }}</p>
        </div>
      </div>

      <!-- Error -->
      <div v-if="selectedReplication.error" class="mb-6">
        <p class="text-sm text-autobot-text-tertiary mb-2">{{ $t('replicationView.error') }}</p>
        <BaseAlert variant="error">
          <p class="text-sm font-mono whitespace-pre-wrap">{{ selectedReplication.error }}</p>
        </BaseAlert>
      </div>
      <template #actions>
        <button
          @click="handleVerifySync(selectedReplication)"
          :disabled="isVerifying"
          class="btn btn-secondary flex items-center gap-2"
        >
          <div v-if="isVerifying" class="animate-spin w-4 h-4 border-2 border-autobot-border-strong border-t-transparent rounded-full"></div>
          {{ $t('replicationView.verifySync') }}
        </button>
        <button
          v-if="selectedReplication.status === 'active'"
          @click="handlePromote(selectedReplication.replication_id); closeDetails()"
          class="btn bg-autobot-primary text-autobot-text-on-primary hover:bg-autobot-primary-hover"
        >
          {{ $t('replicationView.promoteToPrimary') }}
        </button>
        <button @click="closeDetails" class="btn btn-secondary">
          {{ $t('replicationView.close') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>
