// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * AssignNPURoleModal - Modal for assigning NPU Worker role to nodes
 *
 * Allows selecting a node and assigning the npu-worker role with auto-detection.
 *
 * Related to Issue #255 (NPU Fleet Integration).
 */

import { ref, computed } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import type { SLMNode } from '@/types/slm'
import { BaseAlert, BaseModal } from '@autobot/ui'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = defineProps<{
  visible: boolean
  availableNodes: SLMNode[]
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  assigned: []
}>()

const fleetStore = useFleetStore()
const selectedNodeId = ref<string>('')
const loading = ref(false)
const error = ref<string | null>(null)

const selectedNode = computed(() => {
  if (!selectedNodeId.value) return null
  return props.availableNodes.find(n => n.node_id === selectedNodeId.value) || null
})

const eligibleNodes = computed(() => {
  // Filter to nodes that are online and don't already have npu-worker role
  return props.availableNodes.filter(n =>
    n.status === 'online' &&
    !n.roles.includes('npu-worker')
  )
})

function close(): void {
  emit('update:visible', false)
  selectedNodeId.value = ''
  error.value = null
}

async function assignRole(): Promise<void> {
  if (!selectedNodeId.value) {
    error.value = t('fleet.assignNPURoleModal.pleaseSelectANode')
    return
  }

  loading.value = true
  error.value = null

  try {
    await fleetStore.assignNpuRole(selectedNodeId.value)
    emit('assigned')
    close()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('fleet.assignNPURoleModal.failedToAssignNpuRole')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <BaseModal
    :model-value="visible"
    :title="$t('fleet.assignNPURoleModal.assignNPUWorkerRole')"
    size="sm"
    :close-label="$t('ui.modal.closeDialog')"
    @close="close"
  >
    <template #subtitle>
      {{ $t('fleet.assignNPURoleModal.selectANodeTo') }}
    </template>
    <div class="space-y-4">
      <!-- Error Message -->
      <BaseAlert v-if="error" variant="error" :message="error" />

      <!-- Node Selection -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">
          {{ $t('fleet.assignNPURoleModal.selectNode') }}
        </label>
        <select
          v-model="selectedNodeId"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
        >
          <option value="">{{ $t('fleet.assignNPURoleModal.selectANode') }}</option>
          <option
            v-for="node in eligibleNodes"
            :key="node.node_id"
            :value="node.node_id"
          >
            {{ node.hostname }} ({{ node.ip_address }})
          </option>
        </select>
      </div>

      <!-- Selected Node Info -->
      <div v-if="selectedNode" class="bg-gray-50 rounded-lg p-4">
        <h4 class="text-sm font-medium text-gray-700 mb-2">{{ $t('fleet.assignNPURoleModal.nodeDetails') }}</h4>
        <dl class="space-y-1 text-sm">
          <div class="flex justify-between">
            <dt class="text-gray-500">{{ $t('fleet.assignNPURoleModal.hostname') }}</dt>
            <dd class="text-gray-900">{{ selectedNode.hostname }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-gray-500">{{ $t('fleet.assignNPURoleModal.iPAddress') }}</dt>
            <dd class="text-gray-900">{{ selectedNode.ip_address }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-gray-500">{{ $t('fleet.assignNPURoleModal.status') }}</dt>
            <dd class="text-gray-900">{{ selectedNode.status }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-gray-500">{{ $t('fleet.assignNPURoleModal.currentRoles') }}</dt>
            <dd class="text-gray-900">
              {{ selectedNode.roles.length > 0 ? selectedNode.roles.join(', ') : 'None' }}
            </dd>
          </div>
        </dl>
      </div>

      <!-- Info Box -->
      <BaseAlert variant="info" :title="$t('fleet.assignNPURoleModal.autoDetection')" :message="$t('fleet.assignNPURoleModal.afterAssigningTheRole')" />
      <!-- No Eligible Nodes Warning -->
      <BaseAlert v-if="eligibleNodes.length === 0" variant="warning" :title="$t('fleet.assignNPURoleModal.noEligibleNodes')" :message="$t('fleet.assignNPURoleModal.allAvailableNodesEither')" />
    </div>
    <template #actions>
      <button
        @click="close"
        class="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
      >
        {{ $t('fleet.assignNPURoleModal.cancel') }}
      </button>
      <button
        @click="assignRole"
        :disabled="loading || !selectedNodeId"
        class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center gap-2"
      >
        <svg
          v-if="loading"
          class="animate-spin w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        {{ loading ? $t('fleet.assignNPURoleModal.assigning') : $t('fleet.assignNPURoleModal.assignNPURole') }}
      </button>
    </template>
  </BaseModal>
</template>
