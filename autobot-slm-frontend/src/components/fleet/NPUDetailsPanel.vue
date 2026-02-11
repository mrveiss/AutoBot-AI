// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUDetailsPanel - Slide-out panel for NPU node details
 *
 * Shows device info, live metrics, model management, worker configuration,
 * and management actions.
 *
 * Related to Issue #255 (NPU Fleet Integration), enhanced in Issue #590.
 */

import { ref, computed, reactive, onMounted } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import type { SLMNode, NPUNodeStatus, NPUWorkerMetrics, NPUWorkerConfig } from '@/types/slm'

const props = defineProps<{
  node: SLMNode
  npuStatus?: NPUNodeStatus
}>()

const emit = defineEmits<{
  close: []
  refresh: []
}>()

const fleetStore = useFleetStore()
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const liveMetrics = ref<NPUWorkerMetrics | null>(null)
const showConfigSection = ref(false)

const workerConfig = reactive<NPUWorkerConfig>({
  priority: 1,
  weight: 1,
  max_concurrent: 1,
  failure_action: 'retry',
  max_retries: 3,
  assigned_models: [],
})

const deviceTypeLabel = computed(() => {
  if (!props.npuStatus?.capabilities?.deviceType) return 'Unknown Device'
  const labels: Record<string, string> = {
    'intel-npu': 'Intel Neural Processing Unit',
    'nvidia-gpu': 'NVIDIA Graphics Processing Unit',
    'amd-gpu': 'AMD Graphics Processing Unit',
  }
  return labels[props.npuStatus.capabilities.deviceType] ?? props.npuStatus.capabilities.deviceType
})

const lastHealthCheck = computed(() => {
  if (!props.npuStatus?.lastHealthCheck) return 'Never'
  return new Date(props.npuStatus.lastHealthCheck).toLocaleString()
})

const availableModels = computed(() => props.npuStatus?.capabilities?.models ?? [])
const loadedModels = computed(() => props.npuStatus?.loadedModels ?? [])

const memoryPercent = computed(() => {
  if (!liveMetrics.value || !liveMetrics.value.memory_total_gb) return 0
  return Math.round((liveMetrics.value.memory_used_gb / liveMetrics.value.memory_total_gb) * 100)
})

const tempColor = computed(() => {
  const t = liveMetrics.value?.temperature_celsius
  if (t == null) return 'text-gray-500'
  if (t >= 75) return 'text-red-600'
  if (t >= 60) return 'text-yellow-600'
  return 'text-green-600'
})

async function loadWorkerConfig(): Promise<void> {
  const cfg = await fleetStore.fetchNpuWorkerConfig(props.node.node_id)
  if (cfg) {
    Object.assign(workerConfig, cfg)
  }
}

async function loadLiveMetrics(): Promise<void> {
  liveMetrics.value = await fleetStore.fetchNpuNodeMetrics(props.node.node_id)
}

async function saveConfig(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    const ok = await fleetStore.updateNpuWorkerConfig(props.node.node_id, { ...workerConfig })
    if (ok) {
      success.value = 'Configuration saved'
      setTimeout(() => { success.value = null }, 3000)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save configuration'
  } finally {
    saving.value = false
  }
}

async function removeNpuRole(): Promise<void> {
  if (!confirm(`Remove NPU Worker role from ${props.node.hostname}?`)) return
  loading.value = true
  error.value = null
  try {
    await fleetStore.removeNpuRole(props.node.node_id)
    emit('close')
    emit('refresh')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to remove NPU role'
  } finally {
    loading.value = false
  }
}

async function refreshStatus(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await Promise.all([
      fleetStore.fetchNpuStatus(props.node.node_id),
      loadLiveMetrics(),
    ])
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to refresh NPU status'
  } finally {
    loading.value = false
  }
}

function toggleModel(model: string): void {
  const idx = workerConfig.assigned_models.indexOf(model)
  if (idx >= 0) {
    workerConfig.assigned_models.splice(idx, 1)
  } else {
    workerConfig.assigned_models.push(model)
  }
}

onMounted(async () => {
  await Promise.all([loadLiveMetrics(), loadWorkerConfig()])
})
</script>

<template>
  <div class="fixed inset-0 z-50 overflow-hidden">
    <!-- Backdrop -->
    <div
      class="absolute inset-0 bg-gray-500 bg-opacity-50 transition-opacity"
      @click="emit('close')"
    />

    <!-- Panel -->
    <div class="absolute inset-y-0 right-0 max-w-lg w-full bg-white shadow-xl">
      <div class="h-full flex flex-col">
        <!-- Header -->
        <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">{{ node.hostname }}</h2>
            <p class="text-sm text-gray-500">{{ node.ip_address }}</p>
          </div>
          <button
            @click="emit('close')"
            class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6">
          <!-- Messages -->
          <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {{ error }}
          </div>
          <div v-if="success" class="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
            {{ success }}
          </div>

          <!-- Device Info -->
          <div class="bg-gray-50 rounded-lg p-4">
            <h3 class="text-sm font-medium text-gray-700 mb-3">Device Information</h3>
            <dl class="space-y-2">
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Device Type</dt>
                <dd class="text-sm font-medium text-gray-900">{{ deviceTypeLabel }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Memory</dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ npuStatus?.capabilities?.memoryGB ?? 'N/A' }} GB
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Max Concurrent</dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ npuStatus?.capabilities?.maxConcurrent ?? 'N/A' }}
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Last Health Check</dt>
                <dd class="text-sm font-medium text-gray-900">{{ lastHealthCheck }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Detection Status</dt>
                <dd class="text-sm font-medium">
                  <span v-if="npuStatus?.detectionStatus === 'detected'" class="text-green-600">Detected</span>
                  <span v-else-if="npuStatus?.detectionStatus === 'pending'" class="text-yellow-600">Pending</span>
                  <span v-else-if="npuStatus?.detectionStatus === 'failed'" class="text-red-600">Failed</span>
                  <span v-else class="text-gray-600">Unknown</span>
                </dd>
              </div>
            </dl>
          </div>

          <!-- Live Metrics (Issue #590) -->
          <div v-if="liveMetrics" class="bg-gray-50 rounded-lg p-4">
            <h3 class="text-sm font-medium text-gray-700 mb-3">Live Metrics</h3>
            <div class="grid grid-cols-2 gap-3">
              <div class="text-center p-2 bg-white rounded border border-gray-100">
                <p class="text-lg font-semibold text-gray-900">{{ liveMetrics.inference_count }}</p>
                <p class="text-xs text-gray-500">Inferences</p>
              </div>
              <div class="text-center p-2 bg-white rounded border border-gray-100">
                <p class="text-lg font-semibold text-gray-900">{{ liveMetrics.avg_latency_ms.toFixed(1) }}ms</p>
                <p class="text-xs text-gray-500">Avg Latency</p>
              </div>
              <div class="text-center p-2 bg-white rounded border border-gray-100">
                <p class="text-lg font-semibold text-gray-900">{{ liveMetrics.throughput_rps.toFixed(1) }}</p>
                <p class="text-xs text-gray-500">Throughput (req/s)</p>
              </div>
              <div class="text-center p-2 bg-white rounded border border-gray-100">
                <p class="text-lg font-semibold" :class="tempColor">
                  {{ liveMetrics.temperature_celsius != null ? `${liveMetrics.temperature_celsius}°C` : 'N/A' }}
                </p>
                <p class="text-xs text-gray-500">Temperature</p>
              </div>
            </div>

            <!-- Memory bar -->
            <div class="mt-3">
              <div class="flex justify-between text-xs text-gray-500 mb-1">
                <span>Memory</span>
                <span>{{ liveMetrics.memory_used_gb.toFixed(1) }} / {{ liveMetrics.memory_total_gb.toFixed(1) }} GB</span>
              </div>
              <div class="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="h-full bg-blue-500 transition-all"
                  :style="{ width: `${memoryPercent}%` }"
                />
              </div>
            </div>

            <!-- Error count -->
            <div v-if="liveMetrics.error_count > 0" class="mt-3 text-xs text-red-600">
              {{ liveMetrics.error_count }} errors recorded
            </div>
          </div>

          <!-- Utilization -->
          <div>
            <h3 class="text-sm font-medium text-gray-700 mb-3">Current Utilization</h3>
            <div class="flex items-center gap-4">
              <div class="flex-1">
                <div class="w-full h-4 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-primary-500 transition-all"
                    :style="{ width: `${npuStatus?.capabilities?.utilization ?? 0}%` }"
                  />
                </div>
              </div>
              <span class="text-lg font-semibold text-gray-900">
                {{ npuStatus?.capabilities?.utilization ?? 0 }}%
              </span>
            </div>
            <p class="text-xs text-gray-500 mt-2">
              Queue Depth: {{ npuStatus?.queueDepth ?? 0 }} requests
            </p>
          </div>

          <!-- Available Models with Assignment (Issue #590) -->
          <div>
            <h3 class="text-sm font-medium text-gray-700 mb-3">
              Models ({{ availableModels.length }})
            </h3>
            <div v-if="availableModels.length === 0" class="text-sm text-gray-500">
              No models detected
            </div>
            <ul v-else class="space-y-2">
              <li
                v-for="model in availableModels"
                :key="model"
                class="flex items-center justify-between p-2 bg-gray-50 rounded"
              >
                <div class="flex items-center gap-2">
                  <input
                    type="checkbox"
                    :checked="workerConfig.assigned_models.includes(model)"
                    @change="toggleModel(model)"
                    class="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                  <span class="text-sm text-gray-900">{{ model }}</span>
                </div>
                <span
                  v-if="loadedModels.includes(model)"
                  class="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded"
                >
                  Loaded
                </span>
                <span
                  v-else
                  class="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded"
                >
                  Available
                </span>
              </li>
            </ul>
          </div>

          <!-- Worker Configuration (Issue #590) -->
          <div>
            <button
              @click="showConfigSection = !showConfigSection"
              class="flex items-center justify-between w-full text-sm font-medium text-gray-700 hover:text-gray-900"
            >
              <span>Worker Configuration</span>
              <svg
                :class="['w-4 h-4 transition-transform', showConfigSection ? 'rotate-180' : '']"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <div v-if="showConfigSection" class="mt-3 space-y-4 bg-gray-50 rounded-lg p-4">
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-xs font-medium text-gray-600 mb-1">Priority (1-10)</label>
                  <input
                    v-model.number="workerConfig.priority"
                    type="number" min="1" max="10"
                    class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label class="block text-xs font-medium text-gray-600 mb-1">Weight (1-100)</label>
                  <input
                    v-model.number="workerConfig.weight"
                    type="number" min="1" max="100"
                    class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                  />
                </div>
              </div>

              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-xs font-medium text-gray-600 mb-1">Max Concurrent</label>
                  <input
                    v-model.number="workerConfig.max_concurrent"
                    type="number" min="1"
                    class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label class="block text-xs font-medium text-gray-600 mb-1">Max Retries</label>
                  <input
                    v-model.number="workerConfig.max_retries"
                    type="number" min="0" max="10"
                    class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                  />
                </div>
              </div>

              <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">Failure Action</label>
                <select
                  v-model="workerConfig.failure_action"
                  class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-primary-500"
                >
                  <option value="retry">Retry on Same Worker</option>
                  <option value="failover">Failover to Another Worker</option>
                  <option value="skip">Skip Task</option>
                  <option value="alert">Alert Only</option>
                </select>
              </div>

              <button
                @click="saveConfig"
                :disabled="saving"
                class="w-full px-3 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <svg v-if="saving" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ saving ? 'Saving...' : 'Save Configuration' }}
              </button>
            </div>
          </div>

          <!-- Detection Error -->
          <div v-if="npuStatus?.detectionError" class="bg-red-50 rounded-lg p-4">
            <h3 class="text-sm font-medium text-red-700 mb-2">Detection Error</h3>
            <p class="text-sm text-red-600">{{ npuStatus.detectionError }}</p>
          </div>
        </div>

        <!-- Footer Actions -->
        <div class="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
          <button
            @click="removeNpuRole"
            :disabled="loading"
            class="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
          >
            Remove NPU Role
          </button>
          <button
            @click="refreshStatus"
            :disabled="loading"
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
            {{ loading ? 'Refreshing...' : 'Refresh Status' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
