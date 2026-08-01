<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Source Assignment Modal (Issue #779)
 *
 * Allows selecting a node to serve as the code source for the fleet.
 *
 * The code-source POST is migrated onto the canonical `slmApiClient` (#12420
 * Phase 2): it resolves the base URL via `getSlmApiBase()`, injects the SLM
 * bearer token, and centrally handles 401 — replacing the local axios instance
 * and request interceptor. Node loading still flows through `useSlmApi`.
 */

import { ref, onMounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'
import slmApiClient from '@/utils/ApiClient'
import type { SLMNode } from '@/types/slm'

const logger = createLogger('CodeSourceModal')
const slmApi = useSlmApi()

const props = defineProps<{
  currentNodeId?: string
  currentRepoPath?: string
  currentBranch?: string
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const isEditing = Boolean(props.currentNodeId)

const nodes = ref<SLMNode[]>([])
const selectedNodeId = ref(props.currentNodeId ?? '')
const repoPath = ref(props.currentRepoPath ?? '/opt/autobot/code_source')
const branch = ref(props.currentBranch ?? 'Dev_new_gui')
const isLoading = ref(true)
const isSaving = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    // Reuse existing API composable (Issue #860)
    nodes.value = await slmApi.getNodes()
  } catch (e: unknown) {
    // Show actual error for debugging (Issue #860)
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err.response?.data?.detail || err.message || 'Failed to load nodes'
    logger.error('Failed to load nodes:', e)
  } finally {
    isLoading.value = false
  }
})

async function handleAssign(): Promise<void> {
  if (!selectedNodeId.value) return

  isSaving.value = true
  error.value = null

  try {
    await slmApiClient.post('/code-source/assign', {
      node_id: selectedNodeId.value,
      repo_path: repoPath.value,
      branch: branch.value,
    })
    emit('saved')
    emit('close')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to assign code source'
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
      <h3 class="text-lg font-semibold text-gray-900 mb-4">
        {{ isEditing ? $t('codeSourceModal.editCodeSource') : $t('codeSourceModal.assignCodeSource') }}
      </h3>

      <div v-if="isLoading" class="text-gray-500">{{ $t('codeSourceModal.loadingNodes') }}</div>

      <div v-else class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('codeSourceModal.node') }}</label>
          <select
            v-model="selectedNodeId"
            class="w-full border border-gray-300 rounded-md p-2 bg-white text-gray-900"
          >
            <option value="">{{ $t('codeSourceModal.selectANode') }}</option>
            <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
              {{ node.hostname }} ({{ node.ip_address }})
            </option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('codeSourceModal.repositoryPath') }}</label>
          <input
            v-model="repoPath"
            type="text"
            class="w-full border border-gray-300 rounded-md p-2 text-gray-900"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('codeSourceModal.branch') }}</label>
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
          {{ $t('codeSourceModal.cancel') }}
        </button>
        <button
          @click="handleAssign"
          :disabled="!selectedNodeId || isSaving"
          class="btn btn-primary"
        >
          {{ isSaving ? $t('codeSourceModal.saving') : (isEditing ? $t('codeSourceModal.update') : $t('codeSourceModal.assign')) }}
        </button>
      </div>
    </div>
  </div>
</template>
