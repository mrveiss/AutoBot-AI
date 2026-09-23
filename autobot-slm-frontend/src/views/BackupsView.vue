<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Backups View
 *
 * Manages backups for stateful services (Phase 4 - Issue #726).
 *
 * Issue #15225: the replications tab was removed from here — replication
 * management is consolidated into the Orchestration "replication" tab,
 * which mounts the full ReplicationView.vue surface (list, create, start,
 * stop, verify-sync, promote). /backups/replications now redirects there.
 */

import { ref, computed, onMounted } from 'vue'
import { formatBytes } from '@/utils/formatHelpers'
import { useSlmApi } from '@/composables/useSlmApi'
import { useFleetStore } from '@/stores/fleet'
import { formatDateTime } from '@/composables/useTimezone'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'
import type { Backup, BackupRequest } from '@/types/slm'

const { showToast } = useToast()
// #13307: confirm/error strings go through i18n like the rest of the view;
// they were the only hardcoded English left in this file.
const { t } = useI18n()

const api = useSlmApi()
const fleetStore = useFleetStore()

// Backups state
const backups = ref<Backup[]>([])
const isLoadingBackups = ref(false)
const showCreateBackupDialog = ref(false)
const newBackup = ref<BackupRequest>({
  node_id: '',
  service_type: 'redis',
})
const isCreatingBackup = ref(false)

// Node list for dropdowns
const nodeOptions = computed(() =>
  fleetStore.nodeList.map((node) => ({
    value: node.node_id,
    label: `${node.hostname} (${node.ip_address})`,
  }))
)

// Service types
const serviceTypes = ['redis', 'chromadb', 'sqlite']

onMounted(async () => {
  await Promise.all([fetchBackups(), fleetStore.fetchNodes()])
})

// =============================================================================
// Backups
// =============================================================================

async function fetchBackups(): Promise<void> {
  isLoadingBackups.value = true
  try {
    backups.value = await api.getBackups()
  } finally {
    isLoadingBackups.value = false
  }
}

async function handleCreateBackup(): Promise<void> {
  if (!newBackup.value.node_id) return

  isCreatingBackup.value = true
  try {
    await api.createBackup(newBackup.value)
    showCreateBackupDialog.value = false
    newBackup.value = { node_id: '', service_type: 'redis' }
    await fetchBackups()
  } finally {
    isCreatingBackup.value = false
  }
}

async function handleRestore(backupId: string): Promise<void> {
  if (!confirm(t('backupsView.confirmRestore'))) {
    return
  }

  try {
    await api.restoreBackup(backupId)
    await fetchBackups()
  } catch (e) {
    showToast(`${t('backupsView.restoreFailed')}: ${errorText(e)}`, 'error')
  }
}

// #13307: deletion is irreversible and removes the stored file, so it is
// confirmed. Retention prunes automatically after a successful backup; this is
// the manual path for reclaiming space now rather than on the next run.
async function handleDeleteBackup(backupId: string): Promise<void> {
  if (!confirm(t('backupsView.confirmDelete'))) {
    return
  }

  try {
    await api.deleteBackup(backupId)
    await fetchBackups()
  } catch (e) {
    showToast(`${t('backupsView.deleteFailed')}: ${errorText(e)}`, 'error')
  }
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : 'Unknown error'
}

// =============================================================================
// Utilities
// =============================================================================

function getBackupStatusClass(state: string): string {
  switch (state) {
    case 'completed':
      return 'bg-green-100 text-green-800'
    case 'in_progress':
      return 'bg-blue-100 text-blue-800'
    case 'pending':
      return 'bg-yellow-100 text-yellow-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return formatDateTime(dateStr)
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
        <h1 class="text-2xl font-bold text-gray-900">{{ $t('backupsView.statefulServices') }}</h1>
        <p class="text-sm text-gray-500 mt-1">
          {{ $t('backupsView.manageBackups') }}
        </p>
      </div>
    </div>

    <!-- Backups Header -->
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-gray-800">{{ $t('backupsView.backupHistory') }}</h2>
      <button
        @click="showCreateBackupDialog = true"
        class="btn btn-primary flex items-center gap-2"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        {{ $t('backupsView.createBackup') }}
      </button>
    </div>

    <!-- Backups Table -->
    <div class="card overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.backupID') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.node') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.service') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.size') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.location') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.status') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.created') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('backupsView.actions') }}</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-for="backup in backups" :key="backup.backup_id">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
              {{ backup.backup_id.slice(0, 8) }}...
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
              {{ getNodeHostname(backup.node_id) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ backup.service_type }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ formatBytes(backup.size_bytes, { units: ['B', 'KB', 'MB', 'GB', 'TB'], zeroText: '0 B' }) }}
            </td>
            <!-- #13307: backup_path was already in the API response and the
                 page never rendered it, which is the whole of "no idea where
                 they are created". title= carries the full path for a copy. -->
            <td class="px-6 py-4 text-sm text-gray-500 max-w-xs">
              <span v-if="backup.backup_path" class="font-mono text-xs break-all" :title="backup.backup_path">
                {{ backup.backup_path }}
              </span>
              <span v-else class="text-gray-400">{{ $t('backupsView.locationPending') }}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span :class="['px-2 py-1 text-xs font-medium rounded-full', getBackupStatusClass(backup.status)]">
                {{ backup.status }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ formatDate(backup.started_at) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm space-x-3">
              <button
                v-if="backup.status === 'completed'"
                @click="handleRestore(backup.backup_id)"
                class="text-blue-600 hover:text-blue-800 font-medium"
              >
                {{ $t('backupsView.restore') }}
              </button>
              <button
                v-if="backup.status !== 'in_progress'"
                @click="handleDeleteBackup(backup.backup_id)"
                class="text-red-600 hover:text-red-800 font-medium"
              >
                {{ $t('backupsView.delete') }}
              </button>
              <span v-if="backup.status === 'in_progress'" class="text-gray-400">-</span>
            </td>
          </tr>
          <tr v-if="backups.length === 0 && !isLoadingBackups">
            <td colspan="8" class="px-6 py-12 text-center text-gray-500">
              {{ $t('backupsView.noBackupsYetClick') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Backups Loading -->
    <div v-if="isLoadingBackups" class="flex items-center justify-center py-12">
      <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
    </div>

    <!-- Create Backup Dialog -->
    <div
      v-if="showCreateBackupDialog"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="showCreateBackupDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">{{ $t('backupsView.createBackup') }}</h3>
        </div>
        <div class="px-6 py-4 space-y-4">
          <!-- Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('backupsView.node') }}</label>
            <select
              v-model="newBackup.node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">{{ $t('backupsView.selectANode') }}</option>
              <option v-for="opt in nodeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- Service Type Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('backupsView.serviceType') }}</label>
            <select
              v-model="newBackup.service_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option v-for="svc in serviceTypes" :key="svc" :value="svc">
                {{ svc }}
              </option>
            </select>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            @click="showCreateBackupDialog = false"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            {{ $t('backupsView.cancel') }}
          </button>
          <button
            @click="handleCreateBackup"
            :disabled="!newBackup.node_id || isCreatingBackup"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <div v-if="isCreatingBackup" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            {{ $t('backupsView.createBackup') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
