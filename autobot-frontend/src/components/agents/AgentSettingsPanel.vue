<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

AgentSettingsPanel.vue - Runtime agent configuration panel (#1822)
Provides controls for concurrency, timeouts, memory, logging, retry, and execution settings.
-->

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from '@/composables/useLoadingState'

const { t } = useI18n()
const logger = createLogger('AgentSettingsPanel')

// ===== Types =====

interface AgentSettings {
  concurrency: {
    maxConcurrentAgents: number
  }
  timeouts: {
    agentTimeoutSeconds: number
  }
  memory: {
    enabled: boolean
  }
  logging: {
    level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
  }
  retry: {
    attempts: number
    delayMs: number
  }
  execution: {
    parallelExecution: boolean
    priorityQueue: boolean
  }
}

// ===== State =====

const { isLoading, wrap } = useLoadingState()
const { isLoading: isSaving, wrap: wrapSaving } = useLoadingState()
const saveStatus = ref<'idle' | 'success' | 'error'>('idle')
const saveError = ref<string | null>(null)
const hasChanges = ref(false)

const defaults: AgentSettings = {
  concurrency: { maxConcurrentAgents: 5 },
  timeouts: { agentTimeoutSeconds: 300 },
  memory: { enabled: true },
  logging: { level: 'INFO' },
  retry: { attempts: 3, delayMs: 1000 },
  execution: { parallelExecution: true, priorityQueue: false },
}

const settings = reactive<AgentSettings>(structuredClone(defaults))

const logLevels: Array<{ value: AgentSettings['logging']['level']; label: string }> = [
  { value: 'DEBUG', label: 'Debug' },
  { value: 'INFO', label: 'Info' },
  { value: 'WARNING', label: 'Warning' },
  { value: 'ERROR', label: 'Error' },
]

const isValid = computed(() => {
  return (
    settings.concurrency.maxConcurrentAgents >= 1 &&
    settings.concurrency.maxConcurrentAgents <= 20 &&
    settings.timeouts.agentTimeoutSeconds >= 30 &&
    settings.timeouts.agentTimeoutSeconds <= 3600 &&
    settings.retry.attempts >= 0 &&
    settings.retry.attempts <= 10 &&
    settings.retry.delayMs >= 100 &&
    settings.retry.delayMs <= 30000
  )
})

// ===== Methods =====

function markChanged(): void {
  hasChanges.value = true
  saveStatus.value = 'idle'
}

async function loadSettings(): Promise<void> {
  await wrap(async () => {
  try {
    const data = await ApiClient.getSettings()
    const stored = data.agentSettings as Partial<AgentSettings> | undefined
    if (stored) {
      Object.assign(settings.concurrency, defaults.concurrency, stored.concurrency)
      Object.assign(settings.timeouts, defaults.timeouts, stored.timeouts)
      Object.assign(settings.memory, defaults.memory, stored.memory)
      Object.assign(settings.logging, defaults.logging, stored.logging)
      Object.assign(settings.retry, defaults.retry, stored.retry)
      Object.assign(settings.execution, defaults.execution, stored.execution)
    }
    hasChanges.value = false
    logger.debug('Agent settings loaded')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to load agent settings: %s', msg)
  }
  })
}

async function saveSettings(): Promise<void> {
  if (!isValid.value) return

  saveStatus.value = 'idle'
  saveError.value = null
  await wrapSaving(async () => {
  try {
    await ApiClient.saveSettings({ agentSettings: structuredClone(settings) })
    saveStatus.value = 'success'
    hasChanges.value = false
    logger.debug('Agent settings saved')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    saveStatus.value = 'error'
    saveError.value = msg
    logger.error('Failed to save agent settings: %s', msg)
  }
  })
}

function resetToDefaults(): void {
  Object.assign(settings.concurrency, defaults.concurrency)
  Object.assign(settings.timeouts, defaults.timeouts)
  Object.assign(settings.memory, defaults.memory)
  Object.assign(settings.logging, defaults.logging)
  Object.assign(settings.retry, defaults.retry)
  Object.assign(settings.execution, defaults.execution)
  markChanged()
}

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="text-center">
        <div class="animate-spin rounded-sm h-10 w-10 border-b-2 border-primary-600 mx-auto"></div>
        <p class="text-secondary mt-4">{{ t('agent.settings.loading') }}</p>
      </div>
    </div>

    <template v-else>
      <!-- Save Status Banner -->
      <div
        v-if="saveStatus === 'success'"
        class="bg-autobot-success-bg border border-autobot-success-light rounded p-3 flex items-center gap-2"
      >
        <svg class="w-5 h-5 text-autobot-success" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
        </svg>
        <span class="text-sm text-autobot-success">{{ t('agent.settings.saveSuccess') }}</span>
      </div>

      <div
        v-if="saveStatus === 'error'"
        class="bg-autobot-error-bg border border-autobot-error rounded p-3 flex items-center gap-2"
      >
        <svg class="w-5 h-5 text-autobot-error" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <span class="text-sm text-autobot-error">{{ saveError }}</span>
      </div>

      <!-- Settings Grid -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Concurrency Section -->
        <div class="bg-card border border-default rounded-lg p-5">
          <h3 class="text-sm font-semibold text-primary flex items-center gap-2 mb-4">
            <svg class="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
            {{ t('agent.settings.concurrency.title') }}
          </h3>
          <div>
            <label class="block text-xs font-medium text-secondary mb-1">
              {{ t('agent.settings.concurrency.maxAgents') }}
            </label>
            <input
              v-model.number="settings.concurrency.maxConcurrentAgents"
              type="number"
              min="1"
              max="20"
              class="w-full rounded border border-default bg-card px-3 py-2 text-sm text-primary focus:border-autobot-info focus:ring-1 focus:ring-autobot-info"
              @input="markChanged"
            />
            <p class="text-xs text-tertiary mt-1">{{ t('agent.settings.concurrency.maxAgentsHint') }}</p>
          </div>
        </div>

        <!-- Timeouts Section -->
        <div class="bg-card border border-default rounded-lg p-5">
          <h3 class="text-sm font-semibold text-primary flex items-center gap-2 mb-4">
            <svg class="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ t('agent.settings.timeouts.title') }}
          </h3>
          <div>
            <label class="block text-xs font-medium text-secondary mb-1">
              {{ t('agent.settings.timeouts.agentTimeout') }}
            </label>
            <div class="flex items-center gap-2">
              <input
                v-model.number="settings.timeouts.agentTimeoutSeconds"
                type="number"
                min="30"
                max="3600"
                step="30"
                class="flex-1 rounded border border-default bg-card px-3 py-2 text-sm text-primary focus:border-autobot-info focus:ring-1 focus:ring-autobot-info"
                @input="markChanged"
              />
              <span class="text-xs text-tertiary shrink-0">{{ t('agent.settings.timeouts.seconds') }}</span>
            </div>
            <p class="text-xs text-tertiary mt-1">{{ t('agent.settings.timeouts.agentTimeoutHint') }}</p>
          </div>
        </div>

        <!-- Memory Section -->
        <div class="bg-card border border-default rounded-lg p-5">
          <h3 class="text-sm font-semibold text-primary flex items-center gap-2 mb-4">
            <svg class="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
            {{ t('agent.settings.memory.title') }}
          </h3>
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-primary">{{ t('agent.settings.memory.enableLabel') }}</p>
              <p class="text-xs text-tertiary mt-0.5">{{ t('agent.settings.memory.enableHint') }}</p>
            </div>
            <button
              type="button"
              :class="[
                'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-autobot-info focus:ring-offset-2',
                settings.memory.enabled ? 'bg-autobot-primary' : 'bg-autobot-bg-tertiary'
              ]"
              role="switch"
              :aria-checked="settings.memory.enabled"
              @click="settings.memory.enabled = !settings.memory.enabled; markChanged()"
            >
              <span
                :class="[
                  'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-autobot-bg-card shadow ring-0 transition duration-200 ease-in-out',
                  settings.memory.enabled ? 'translate-x-5' : 'translate-x-0'
                ]"
              />
            </button>
          </div>
        </div>

        <!-- Logging Section -->
        <div class="bg-card border border-default rounded-lg p-5">
          <h3 class="text-sm font-semibold text-primary flex items-center gap-2 mb-4">
            <svg class="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            {{ t('agent.settings.logging.title') }}
          </h3>
          <div>
            <label class="block text-xs font-medium text-secondary mb-1">
              {{ t('agent.settings.logging.levelLabel') }}
            </label>
            <select
              v-model="settings.logging.level"
              class="w-full rounded border border-default bg-card px-3 py-2 text-sm text-primary focus:border-autobot-info focus:ring-1 focus:ring-autobot-info"
              @change="markChanged"
            >
              <option v-for="level in logLevels" :key="level.value" :value="level.value">
                {{ level.label }}
              </option>
            </select>
            <p class="text-xs text-tertiary mt-1">{{ t('agent.settings.logging.levelHint') }}</p>
          </div>
        </div>

        <!-- Retry Section -->
        <div class="bg-card border border-default rounded-lg p-5">
          <h3 class="text-sm font-semibold text-primary flex items-center gap-2 mb-4">
            <svg class="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {{ t('agent.settings.retry.title') }}
          </h3>
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-medium text-secondary mb-1">
                {{ t('agent.settings.retry.attemptsLabel') }}
              </label>
              <input
                v-model.number="settings.retry.attempts"
                type="number"
                min="0"
                max="10"
                class="w-full rounded border border-default bg-card px-3 py-2 text-sm text-primary focus:border-autobot-info focus:ring-1 focus:ring-autobot-info"
                @input="markChanged"
              />
              <p class="text-xs text-tertiary mt-1">{{ t('agent.settings.retry.attemptsHint') }}</p>
            </div>
            <div>
              <label class="block text-xs font-medium text-secondary mb-1">
                {{ t('agent.settings.retry.delayLabel') }}
              </label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="settings.retry.delayMs"
                  type="number"
                  min="100"
                  max="30000"
                  step="100"
                  class="flex-1 rounded border border-default bg-card px-3 py-2 text-sm text-primary focus:border-autobot-info focus:ring-1 focus:ring-autobot-info"
                  @input="markChanged"
                />
                <span class="text-xs text-tertiary shrink-0">ms</span>
              </div>
              <p class="text-xs text-tertiary mt-1">{{ t('agent.settings.retry.delayHint') }}</p>
            </div>
          </div>
        </div>

        <!-- Execution Section -->
        <div class="bg-card border border-default rounded-lg p-5">
          <h3 class="text-sm font-semibold text-primary flex items-center gap-2 mb-4">
            <svg class="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            {{ t('agent.settings.execution.title') }}
          </h3>
          <div class="space-y-4">
            <div class="flex items-center justify-between">
              <div>
                <p class="text-sm text-primary">{{ t('agent.settings.execution.parallelLabel') }}</p>
                <p class="text-xs text-tertiary mt-0.5">{{ t('agent.settings.execution.parallelHint') }}</p>
              </div>
              <button
                type="button"
                :class="[
                  'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-autobot-info focus:ring-offset-2',
                  settings.execution.parallelExecution ? 'bg-autobot-primary' : 'bg-autobot-bg-tertiary'
                ]"
                role="switch"
                :aria-checked="settings.execution.parallelExecution"
                @click="settings.execution.parallelExecution = !settings.execution.parallelExecution; markChanged()"
              >
                <span
                  :class="[
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-autobot-bg-card shadow ring-0 transition duration-200 ease-in-out',
                    settings.execution.parallelExecution ? 'translate-x-5' : 'translate-x-0'
                  ]"
                />
              </button>
            </div>
            <div class="flex items-center justify-between">
              <div>
                <p class="text-sm text-primary">{{ t('agent.settings.execution.priorityLabel') }}</p>
                <p class="text-xs text-tertiary mt-0.5">{{ t('agent.settings.execution.priorityHint') }}</p>
              </div>
              <button
                type="button"
                :class="[
                  'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-autobot-info focus:ring-offset-2',
                  settings.execution.priorityQueue ? 'bg-autobot-primary' : 'bg-autobot-bg-tertiary'
                ]"
                role="switch"
                :aria-checked="settings.execution.priorityQueue"
                @click="settings.execution.priorityQueue = !settings.execution.priorityQueue; markChanged()"
              >
                <span
                  :class="[
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-autobot-bg-card shadow ring-0 transition duration-200 ease-in-out',
                    settings.execution.priorityQueue ? 'translate-x-5' : 'translate-x-0'
                  ]"
                />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions Bar -->
      <div class="flex items-center justify-between pt-4 border-t border-default">
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-secondary border border-default rounded hover:bg-autobot-bg-hover transition-colors"
          @click="resetToDefaults"
        >
          {{ t('agent.settings.resetDefaults') }}
        </button>
        <div class="flex items-center gap-3">
          <span v-if="hasChanges" class="text-xs text-autobot-warning">
            {{ t('agent.settings.unsavedChanges') }}
          </span>
          <button
            type="button"
            :disabled="!hasChanges || !isValid || isSaving"
            class="px-5 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
            @click="saveSettings"
          >
            <svg
              v-if="isSaving"
              class="w-4 h-4 animate-spin"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {{ isSaving ? t('agent.settings.saving') : t('agent.settings.save') }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>