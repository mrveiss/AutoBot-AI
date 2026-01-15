<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import type { Backup } from '@/types/slm'

const api = useSlmApi()

const backups = ref<Backup[]>([])
const isLoading = ref(false)
const showCreateDialog = ref(false)

onMounted(async () => {
  await fetchBackups()
})

async function fetchBackups(): Promise<void> {
  isLoading.value = true
  try {
    backups.value = await api.getBackups()
  } finally {
    isLoading.value = false
  }
}

async function handleRestore(backupId: string): Promise<void> {
  if (!confirm('Are you sure you want to restore this backup? This will overwrite current data.')) {
    return
  }

  try {
    await api.restoreBackup(backupId)
    await fetchBackups()
  } catch (err) {
    // Handle error
  }
}

function getStatusClass(state: string): string {
  switch (state) {
    case 'completed': return 'bg-green-100 text-green-800'
    case 'in_progress': return 'bg-blue-100 text-blue-800'
    case 'pending': return 'bg-yellow-100 text-yellow-800'
    case 'failed': return 'bg-red-100 text-red-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Backups</h1>
        <p class="text-sm text-gray-500 mt-1">
          Manage backups and restore operations for stateful services
        </p>
      </div>
      <button
        @click="showCreateDialog = true"
        class="btn btn-primary flex items-center gap-2"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Create Backup
      </button>
    </div>

    <!-- Backups Table -->
    <div class="card overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Backup ID</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Node</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Size</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-for="backup in backups" :key="backup.backup_id">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
              {{ backup.backup_id.slice(0, 8) }}...
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
              {{ backup.node_id }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ backup.service_type }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ formatBytes(backup.size_bytes) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(backup.state)]">
                {{ backup.state }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ backup.started_at ? new Date(backup.started_at).toLocaleString() : '-' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm">
              <button
                v-if="backup.state === 'completed'"
                @click="handleRestore(backup.backup_id)"
                class="text-blue-600 hover:text-blue-800"
              >
                Restore
              </button>
            </td>
          </tr>
          <tr v-if="backups.length === 0 && !isLoading">
            <td colspan="7" class="px-6 py-12 text-center text-gray-500">
              No backups yet. Click "Create Backup" to get started.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
    </div>
  </div>
</template>
