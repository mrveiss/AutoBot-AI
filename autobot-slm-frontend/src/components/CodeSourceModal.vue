<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Source Assignment Modal (Issue #779)
 *
 * Allows selecting a node to serve as the code source for the fleet.
 */

import { ref, onMounted } from 'vue'
import axios from 'axios'
import { getBackendUrl } from '@/config/ssot-config'

const emit = defineEmits<{
  close: []
  saved: []
}>()

interface Node {
  node_id: string
  hostname: string
  ip_address: string
}

const nodes = ref<Node[]>([])
const selectedNodeId = ref('')
const repoPath = ref('/opt/autobot')
const branch = ref('main')
const isLoading = ref(true)
const isSaving = ref(false)
const error = ref<string | null>(null)

const API_BASE = getBackendUrl()

onMounted(async () => {
  try {
    const response = await axios.get<{ nodes: Node[] }>(`${API_BASE}/api/nodes`)
    nodes.value = response.data.nodes
  } catch {
    error.value = 'Failed to load nodes'
  } finally {
    isLoading.value = false
  }
})

async function handleAssign(): Promise<void> {
  if (!selectedNodeId.value) return

  isSaving.value = true
  error.value = null

  try {
    await axios.post(`${API_BASE}/api/code-source/assign`, {
      node_id: selectedNodeId.value,
      repo_path: repoPath.value,
      branch: branch.value,
    })
    emit('saved')
    emit('close')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err.response?.data?.detail || err.message || 'Failed to assign code source'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div
    class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
    @click.self="emit('close')"
  >
    <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
      <h3 class="text-lg font-semibold text-gray-900 mb-4">Assign Code Source</h3>

      <div v-if="isLoading" class="text-gray-500">Loading nodes...</div>

      <div v-else class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Node</label>
          <select
            v-model="selectedNodeId"
            class="w-full border border-gray-300 rounded-md p-2 bg-white text-gray-900"
          >
            <option value="">Select a node...</option>
            <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
              {{ node.hostname }} ({{ node.ip_address }})
            </option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Repository Path</label>
          <input
            v-model="repoPath"
            type="text"
            class="w-full border border-gray-300 rounded-md p-2 text-gray-900"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Branch</label>
          <input
            v-model="branch"
            type="text"
            class="w-full border border-gray-300 rounded-md p-2 text-gray-900"
          />
        </div>

        <div v-if="error" class="text-red-600 text-sm">{{ error }}</div>
      </div>

      <div class="flex justify-end gap-3 mt-6">
        <button @click="emit('close')" class="btn btn-secondary">
          Cancel
        </button>
        <button
          @click="handleAssign"
          :disabled="!selectedNodeId || isSaving"
          class="btn btn-primary"
        >
          {{ isSaving ? 'Assigning...' : 'Assign' }}
        </button>
      </div>
    </div>
  </div>
</template>
