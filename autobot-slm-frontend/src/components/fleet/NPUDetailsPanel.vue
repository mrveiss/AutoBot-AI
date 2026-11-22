// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
import { BaseAlert, BaseDrawer } from '@autobot/ui'
/**
 * NPUDetailsPanel - Slide-out panel for NPU node details
 *
 * Shows device info, live metrics, model management, worker configuration,
 * and management actions.
 *
 * Related to Issue #255 (NPU Fleet Integration), enhanced in Issue #590.
 */

import { ref, computed, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFleetStore } from '@/stores/fleet'
import type { SLMNode, NPUNodeStatus, NPUWorkerMetrics, NPUWorkerConfig } from '@/types/slm'
import { formatFleetDateTime } from '@/composables/useTimezone'
import { errorText } from '@/utils/errorText'

const props = defineProps<{
  node: SLMNode
  npuStatus?: NPUNodeStatus
  /** Drives the drawer, so it slides out and hands focus back when closed (#14780). */
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  refresh: []
}>()

const fleetStore = useFleetStore()
const { t: translate } = useI18n()
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const liveMetrics = ref<NPUWorkerMetrics | null>(null)
const showConfigSection = ref(false)

// #13138: `assigned_models` is `default_factory=list` server-side and therefore
// OPTIONAL in the contract, but this form always keeps a concrete array so the
// checkbox list and `toggleModel` have something to index.
const CONFIG_DEFAULTS: Pick<NPUWorkerConfig, 'priority' | 'weight' | 'max_concurrent' | 'failure_action' | 'max_retries'> = {
  priority: 1,
  weight: 1,
  max_concurrent: 1,
  failure_action: 'retry',
  max_retries: 3,
}
const workerConfig = reactive<NPUWorkerConfig & { assigned_models: string[] }>({
  ...CONFIG_DEFAULTS,
  assigned_models: [],
})

// The panel stays mounted between nodes: each (re)load bumps the token, and a response
// carrying an older token belongs to a node no longer shown, so it is dropped.
let loadToken = 0
const isCurrent = (token: number): boolean => token === loadToken

function resetNodeState(): void {
  Object.assign(workerConfig, CONFIG_DEFAULTS, { assigned_models: [] })
  liveMetrics.value = null
  error.value = null
  success.value = null
}

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
  return formatFleetDateTime(props.npuStatus.lastHealthCheck)
})

const availableModels = computed(() => props.npuStatus?.capabilities?.models ?? [])
const loadedModels = computed(() => props.npuStatus?.loadedModels ?? [])

const memoryPercent = computed(() => {
  if (!liveMetrics.value || !liveMetrics.value.memory_total_gb) return 0
  return Math.round((liveMetrics.value.memory_used_gb / liveMetrics.value.memory_total_gb) * 100)
})

const tempColor = computed(() => {
  const t = liveMetrics.value?.temperature_celsius
  if (t == null) return 'text-autobot-text-tertiary'
  if (t >= 75) return 'text-autobot-error'
  if (t >= 60) return 'text-autobot-pill-warn-fg'
  return 'text-autobot-success'
})

async function loadWorkerConfig(token: number): Promise<void> {
  const cfg = await fleetStore.fetchNpuWorkerConfig(props.node.node_id)
  if (!isCurrent(token)) return
  // No config means defaults, never the previous node's form; `assigned_models` may be omitted.
  Object.assign(workerConfig, CONFIG_DEFAULTS, cfg ?? {}, { assigned_models: cfg?.assigned_models ?? [] })
}

async function loadLiveMetrics(token: number): Promise<void> {
  const metrics = await fleetStore.fetchNpuNodeMetrics(props.node.node_id)
  if (isCurrent(token)) liveMetrics.value = metrics
}

async function saveConfig(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    const ok = await fleetStore.updateNpuWorkerConfig(props.node.node_id, { ...workerConfig })
    if (ok) {
      success.value = translate('fleet.nPUDetailsPanel.configurationSaved')
      setTimeout(() => { success.value = null }, 3000)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : translate('fleet.nPUDetailsPanel.failedToSaveConfiguration')
  } finally {
    saving.value = false
  }
}

async function removeNpuRole(): Promise<void> {
  if (!confirm(translate('fleet.nPUDetailsPanel.removeNpuWorkerRoleFrom', { hostname: props.node.hostname }))) return
  loading.value = true
  error.value = null
  try {
    await fleetStore.removeNpuRole(props.node.node_id)
    emit('close')
    emit('refresh')
  } catch (e) {
    error.value = e instanceof Error ? e.message : translate('fleet.nPUDetailsPanel.failedToRemoveNpuRole')
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
      loadLiveMetrics(loadToken),
    ])
  } catch (e) {
    error.value = e instanceof Error ? e.message : translate('fleet.nPUDetailsPanel.failedToRefreshNpuStatus')
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

// Load each time the panel opens, or shows another node while open: it stays mounted between uses.
watch(
  () => [props.open, props.node.node_id] as const,
  ([open]) => {
    if (!open) return
    const token = ++loadToken
    resetNodeState()
    Promise.all([loadLiveMetrics(token), loadWorkerConfig(token)]).catch((e: unknown) => {
      if (isCurrent(token)) error.value = errorText(e)
    })
  },
  { immediate: true },
)
</script>

<template>
  <BaseDrawer
    :model-value="open"
    :title="node.hostname"
    width="32rem"
    :close-label="$t('fleet.nPUDetailsPanel.close')"
    @close="emit('close')"
  >
    <template #subtitle>{{ node.ip_address }}</template>

    <div class="space-y-6">
      <!-- Messages -->
      <BaseAlert v-if="error" variant="error" :message="error" />
      <BaseAlert v-if="success" variant="success" size="compact" :message="success" />

      <!-- Device Info -->
      <div class="bg-autobot-bg-secondary rounded-lg p-4">
        <h3 class="text-sm font-medium text-autobot-text-secondary mb-3">{{ $t('fleet.nPUDetailsPanel.deviceInformation') }}</h3>
        <dl class="space-y-2">
          <div class="flex justify-between">
            <dt class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.deviceType') }}</dt>
            <dd class="text-sm font-medium text-autobot-text-primary">{{ deviceTypeLabel }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.memory') }}</dt>
            <dd class="text-sm font-medium text-autobot-text-primary">
              {{ npuStatus?.capabilities?.memoryGB ?? $t('fleet.nPUDetailsPanel.notAvailable') }} GB
            </dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.maxConcurrent') }}</dt>
            <dd class="text-sm font-medium text-autobot-text-primary">
              {{ npuStatus?.capabilities?.maxConcurrent ?? $t('fleet.nPUDetailsPanel.notAvailable') }}
            </dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.lastHealthCheck') }}</dt>
            <dd class="text-sm font-medium text-autobot-text-primary">{{ lastHealthCheck }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.detectionStatus') }}</dt>
            <dd class="text-sm font-medium">
              <span v-if="npuStatus?.detectionStatus === 'detected'" class="text-autobot-success">{{ $t('fleet.nPUDetailsPanel.detected') }}</span>
              <span v-else-if="npuStatus?.detectionStatus === 'pending'" class="text-autobot-pill-warn-fg">{{ $t('fleet.nPUDetailsPanel.pending') }}</span>
              <span v-else-if="npuStatus?.detectionStatus === 'failed'" class="text-autobot-error">{{ $t('fleet.nPUDetailsPanel.failed') }}</span>
              <span v-else class="text-autobot-text-secondary">{{ $t('fleet.nPUDetailsPanel.unknown') }}</span>
            </dd>
          </div>
        </dl>
      </div>

      <!-- Live Metrics (Issue #590) -->
      <div v-if="liveMetrics" class="bg-autobot-bg-secondary rounded-lg p-4">
        <h3 class="text-sm font-medium text-autobot-text-secondary mb-3">{{ $t('fleet.nPUDetailsPanel.liveMetrics') }}</h3>
        <div class="grid grid-cols-2 gap-3">
          <div class="text-center p-2 bg-white rounded-sm border border-autobot-border-subtle">
            <p class="text-lg font-semibold text-autobot-text-primary">{{ liveMetrics.inference_count }}</p>
            <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.inferences') }}</p>
          </div>
          <div class="text-center p-2 bg-white rounded-sm border border-autobot-border-subtle">
            <p class="text-lg font-semibold text-autobot-text-primary">{{ liveMetrics.avg_latency_ms.toFixed(1) }}ms</p>
            <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.avgLatency') }}</p>
          </div>
          <div class="text-center p-2 bg-white rounded-sm border border-autobot-border-subtle">
            <p class="text-lg font-semibold text-autobot-text-primary">{{ liveMetrics.throughput_rps.toFixed(1) }}</p>
            <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.throughputReqS') }}</p>
          </div>
          <div class="text-center p-2 bg-white rounded-sm border border-autobot-border-subtle">
            <p class="text-lg font-semibold" :class="tempColor">
              {{ liveMetrics.temperature_celsius != null ? `${liveMetrics.temperature_celsius}°C` : $t('fleet.nPUDetailsPanel.notAvailable') }}
            </p>
            <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUDetailsPanel.temperature') }}</p>
          </div>
        </div>

        <!-- Memory bar -->
        <div class="mt-3">
          <div class="flex justify-between text-xs text-autobot-text-tertiary mb-1">
            <span>{{ $t('fleet.nPUDetailsPanel.memory') }}</span>
            <span>{{ liveMetrics.memory_used_gb.toFixed(1) }} / {{ liveMetrics.memory_total_gb.toFixed(1) }} GB</span>
          </div>
          <div class="w-full h-2 bg-autobot-bg-active rounded-full overflow-hidden">
            <div
              class="h-full bg-autobot-primary transition-all"
              :style="{ width: `${memoryPercent}%` }"
            />
          </div>
        </div>

        <!-- Error count -->
        <div v-if="liveMetrics.error_count > 0" class="mt-3 text-xs text-autobot-error">{{ $t('fleet.nPUDetailsPanel.value0ErrorsRecorded', { value0: liveMetrics.error_count }) }}</div>
      </div>

      <!-- Utilization -->
      <div>
        <h3 class="text-sm font-medium text-autobot-text-secondary mb-3">{{ $t('fleet.nPUDetailsPanel.currentUtilization') }}</h3>
        <div class="flex items-center gap-4">
          <div class="flex-1">
            <div class="w-full h-4 bg-autobot-bg-active rounded-full overflow-hidden">
              <div
                class="h-full bg-primary-500 transition-all"
                :style="{ width: `${npuStatus?.capabilities?.utilization ?? 0}%` }"
              />
            </div>
          </div>
          <span class="text-lg font-semibold text-autobot-text-primary">
            {{ npuStatus?.capabilities?.utilization ?? 0 }}%
          </span>
        </div>
        <p class="text-xs text-autobot-text-tertiary mt-2">{{ $t('fleet.nPUDetailsPanel.queueDepthValue0Requests', { value0: npuStatus?.queueDepth ?? 0 }) }}</p>
      </div>

      <!-- Available Models with Assignment (Issue #590) -->
      <div>
        <h3 class="text-sm font-medium text-autobot-text-secondary mb-3">{{ $t('fleet.nPUDetailsPanel.modelsCount', { count: availableModels.length }) }}</h3>
        <div v-if="availableModels.length === 0" class="text-sm text-autobot-text-tertiary">
          {{ $t('fleet.nPUDetailsPanel.noModelsDetected') }}
        </div>
        <ul v-else class="space-y-2">
          <li
            v-for="model in availableModels"
            :key="model"
            class="flex items-center justify-between p-2 bg-autobot-bg-secondary rounded-sm"
          >
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                :checked="workerConfig.assigned_models.includes(model)"
                @change="toggleModel(model)"
                class="rounded-sm border-autobot-border-strong text-primary-600 focus:ring-primary-500"
              />
              <span class="text-sm text-autobot-text-primary">{{ model }}</span>
            </div>
            <span
              v-if="loadedModels.includes(model)"
              class="px-2 py-0.5 bg-autobot-pill-ok-bg text-autobot-pill-ok-fg text-xs rounded-sm"
            >
              {{ $t('fleet.nPUDetailsPanel.loaded') }}
            </span>
            <span
              v-else
              class="px-2 py-0.5 bg-autobot-bg-tertiary text-autobot-text-secondary text-xs rounded-sm"
            >
              {{ $t('fleet.nPUDetailsPanel.available') }}
            </span>
          </li>
        </ul>
      </div>

      <!-- Worker Configuration (Issue #590) -->
      <div>
        <button
          @click="showConfigSection = !showConfigSection"
          class="flex items-center justify-between w-full text-sm font-medium text-autobot-text-secondary hover:text-autobot-text-primary"
        >
          <span>{{ $t('fleet.nPUDetailsPanel.workerConfiguration') }}</span>
          <svg
            :class="['w-4 h-4 transition-transform', showConfigSection ? 'rotate-180' : '']"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <div v-if="showConfigSection" class="mt-3 space-y-4 bg-autobot-bg-secondary rounded-lg p-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('fleet.nPUDetailsPanel.priority110') }}</label>
              <input
                v-model.number="workerConfig.priority"
                type="number" min="1" max="10"
                class="w-full px-2 py-1.5 text-sm border border-autobot-border-strong rounded-sm focus:ring-1 focus:ring-primary-500"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('fleet.nPUDetailsPanel.weight1100') }}</label>
              <input
                v-model.number="workerConfig.weight"
                type="number" min="1" max="100"
                class="w-full px-2 py-1.5 text-sm border border-autobot-border-strong rounded-sm focus:ring-1 focus:ring-primary-500"
              />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('fleet.nPUDetailsPanel.maxConcurrent') }}</label>
              <input
                v-model.number="workerConfig.max_concurrent"
                type="number" min="1"
                class="w-full px-2 py-1.5 text-sm border border-autobot-border-strong rounded-sm focus:ring-1 focus:ring-primary-500"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('fleet.nPUDetailsPanel.maxRetries') }}</label>
              <input
                v-model.number="workerConfig.max_retries"
                type="number" min="0" max="10"
                class="w-full px-2 py-1.5 text-sm border border-autobot-border-strong rounded-sm focus:ring-1 focus:ring-primary-500"
              />
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-autobot-text-secondary mb-1">{{ $t('fleet.nPUDetailsPanel.failureAction') }}</label>
            <select
              v-model="workerConfig.failure_action"
              class="w-full px-2 py-1.5 text-sm border border-autobot-border-strong rounded-sm focus:ring-1 focus:ring-primary-500"
            >
              <option value="retry">{{ $t('fleet.nPUDetailsPanel.retryOnSameWorker') }}</option>
              <option value="failover">{{ $t('fleet.nPUDetailsPanel.failoverToAnotherWorker') }}</option>
              <option value="skip">{{ $t('fleet.nPUDetailsPanel.skipTask') }}</option>
              <option value="alert">{{ $t('fleet.nPUDetailsPanel.alertOnly') }}</option>
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
            {{ saving ? $t('fleet.nPUDetailsPanel.saving') : $t('fleet.nPUDetailsPanel.saveConfiguration') }}
          </button>
        </div>
      </div>

      <!-- Detection Error -->
      <BaseAlert
        v-if="npuStatus?.detectionError"
        variant="error"
        :title="$t('fleet.nPUDetailsPanel.detectionError')"
        :message="npuStatus.detectionError"
      />
    </div>


    <template #actions>
      <div class="flex w-full items-center justify-between">
        <button
          @click="removeNpuRole"
          :disabled="loading"
          class="px-4 py-2 text-autobot-error hover:bg-autobot-error-bg rounded-lg transition-colors disabled:opacity-50"
        >
          {{ $t('fleet.nPUDetailsPanel.removeNPURole') }}
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
          {{ loading ? $t('fleet.nPUDetailsPanel.refreshing') : $t('fleet.nPUDetailsPanel.refreshStatus') }}
        </button>
      </div>
    </template>
  </BaseDrawer>
</template>
