<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LLMConfigView - Main LLM configuration and monitoring view
 * Issue #897 - LLM Configuration Panel
 */

import { ref, onMounted, computed } from 'vue'
import { useLlmConfig, type LLMConfig } from '@/composables/useLlmConfig'
import { useLlmHealth } from '@/composables/useLlmHealth'
import LLMProviderCard from '@/components/llm/LLMProviderCard.vue'
import LLMHealthMonitor from '@/components/llm/LLMHealthMonitor.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LLMConfigView')

const {
  config,
  providers,
  models,
  currentProvider,
  isLoading: configLoading,
  error: configError,
  fetchProviders,
  fetchConfig,
  updateConfig,
  fetchModels,
  switchProvider,
  testProviderConnection,
} = useLlmConfig({ autoFetch: false })

const {
  healthMetrics,
  healthSummary,
  usageStats,
  isLoading: healthLoading,
  error: healthError,
  lastUpdate,
  refreshAll: refreshHealth,
} = useLlmHealth({ autoFetch: false, pollInterval: 60000 })

const activeTab = ref<'providers' | 'health' | 'usage'>('providers')
const showConfigModal = ref(false)
const selectedProvider = ref<string | null>(null)
const configForm = ref({ api_key: '', model: '', endpoint: '', temperature: 0.7, max_tokens: 2048 })
const isSavingConfig = ref(false)
const configTestResult = ref<{ success: boolean; message: string } | null>(null)

const isLoading = computed(() => configLoading.value || healthLoading.value)
const error = computed(() => configError.value || healthError.value)

async function loadData() {
  logger.debug('Loading LLM configuration data')
  await Promise.all([
    fetchProviders(),
    fetchConfig(),
    refreshHealth(),
  ])
}

async function handleActivate(providerName: string) {
  logger.debug('Activating provider:', providerName)
  const success = await switchProvider(providerName)
  if (success) {
    logger.debug('Provider activated successfully')
    await loadData()
  }
}

async function handleTest(providerName: string) {
  logger.debug('Testing provider:', providerName)
  const result = await testProviderConnection(providerName)
  if (result) {
    logger.debug('Test result:', result)
  }
}

async function handleConfigure(providerName: string) {
  logger.debug('Opening configuration for provider:', providerName)
  selectedProvider.value = providerName
  configForm.value = { api_key: '', model: '', endpoint: '', temperature: 0.7, max_tokens: 2048 }
  configTestResult.value = null
  showConfigModal.value = true
  await fetchModels(providerName)
}

function closeConfigModal() {
  showConfigModal.value = false
  selectedProvider.value = null
  configTestResult.value = null
}

async function handleSaveConfig(): Promise<void> {
  if (!selectedProvider.value) return
  isSavingConfig.value = true
  configTestResult.value = null
  const payload: Partial<LLMConfig> = {
    provider: selectedProvider.value,
    model: configForm.value.model || undefined,
    endpoint: configForm.value.endpoint || undefined,
    temperature: configForm.value.temperature,
    max_tokens: configForm.value.max_tokens,
  }
  if (configForm.value.api_key) payload.api_key = configForm.value.api_key
  const saved = await updateConfig(payload)
  isSavingConfig.value = false
  if (saved) {
    closeConfigModal()
    await loadData()
  }
}

async function handleTestConfig(): Promise<void> {
  if (!selectedProvider.value) return
  isSavingConfig.value = true
  configTestResult.value = null
  const result = await testProviderConnection(selectedProvider.value)
  isSavingConfig.value = false
  configTestResult.value = result
    ? { success: result.success, message: result.message || result.error || 'Test complete' }
    : { success: false, message: 'Test failed — no response' }
}

async function handleRefresh() {
  await loadData()
}

onMounted(async () => {
  await loadData()
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-primary">LLM Configuration</h2>
        <p class="text-sm text-secondary mt-1">
          Manage and monitor LLM providers
          <span v-if="lastUpdate" class="ml-2">
            • Last updated: {{ lastUpdate.toLocaleTimeString() }}
          </span>
        </p>
      </div>
      <button
        @click="handleRefresh"
        :disabled="isLoading"
        class="px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
      >
        <svg
          :class="['w-4 h-4', { 'animate-spin': isLoading }]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Refresh
      </button>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="bg-autobot-error-bg border border-autobot-error rounded p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-autobot-error mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <h3 class="text-sm font-medium text-autobot-error">Error</h3>
          <p class="text-sm text-autobot-error mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-default">
      <nav class="-mb-px flex space-x-8">
        <button
          @click="activeTab = 'providers'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'providers'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Providers
        </button>
        <button
          @click="activeTab = 'health'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'health'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Health Monitor
        </button>
        <button
          @click="activeTab = 'usage'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'usage'
              ? 'border-autobot-info text-autobot-info'
              : 'border-transparent text-secondary hover:text-primary hover:border-default'
          ]"
        >
          Usage Statistics
        </button>
      </nav>
    </div>

    <!-- Tab Content -->
    <div class="mt-6">
      <!-- Providers Tab -->
      <div v-show="activeTab === 'providers'">
        <div v-if="configLoading && providers.length === 0" class="flex items-center justify-center py-12">
          <div class="text-center">
            <div class="animate-spin rounded-sm h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
            <p class="text-secondary mt-4">Loading providers...</p>
          </div>
        </div>

        <div v-else-if="providers.length === 0" class="text-center py-12">
          <svg class="mx-auto h-12 w-12 text-autobot-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 class="mt-2 text-sm font-medium text-primary">No providers configured</h3>
          <p class="mt-1 text-sm text-secondary">Get started by configuring an LLM provider.</p>
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <LLMProviderCard
            v-for="provider in providers"
            :key="provider.name"
            :provider="provider"
            :is-active="currentProvider === provider.name"
            @activate="handleActivate"
            @test="handleTest"
            @configure="handleConfigure"
          />
        </div>
      </div>

      <!-- Health Tab -->
      <div v-show="activeTab === 'health'">
        <LLMHealthMonitor
          :health-summary="healthSummary"
          :health-metrics="healthMetrics"
          :loading="healthLoading"
          :last-update="lastUpdate"
        />
      </div>

      <!-- Usage Tab -->
      <div v-show="activeTab === 'usage'">
        <div class="bg-autobot-bg-card rounded shadow-sm border border-default p-6">
          <h3 class="text-lg font-semibold text-primary mb-4">Usage Statistics</h3>
          <div v-if="healthLoading && usageStats.length === 0" class="flex justify-center py-12">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-autobot-primary"></div>
          </div>
          <div v-else-if="usageStats.length === 0" class="text-center py-12 text-secondary">
            <svg class="mx-auto h-12 w-12 text-autobot-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p class="mt-4">No usage data available yet</p>
          </div>
          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="border-b border-default text-left">
                  <th class="pb-3 pr-4 font-medium text-secondary">Provider</th>
                  <th class="pb-3 pr-4 font-medium text-secondary">Model</th>
                  <th class="pb-3 pr-4 font-medium text-secondary text-right">Requests</th>
                  <th class="pb-3 pr-4 font-medium text-secondary text-right">Total Tokens</th>
                  <th class="pb-3 pr-4 font-medium text-secondary text-right">Avg Latency</th>
                  <th class="pb-3 font-medium text-secondary text-right">Cost (USD)</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-default">
                <tr
                  v-for="stat in usageStats"
                  :key="`${stat.provider}-${stat.model}`"
                  class="hover:bg-autobot-bg-secondary"
                >
                  <td class="py-3 pr-4 font-medium text-primary">{{ stat.provider }}</td>
                  <td class="py-3 pr-4 text-secondary">{{ stat.model }}</td>
                  <td class="py-3 pr-4 text-right text-primary">{{ stat.total_requests.toLocaleString() }}</td>
                  <td class="py-3 pr-4 text-right text-primary">{{ stat.total_tokens.toLocaleString() }}</td>
                  <td class="py-3 pr-4 text-right text-primary">{{ Math.round(stat.avg_response_time_ms) }}ms</td>
                  <td class="py-3 text-right text-primary">${{ stat.cost_usd.toFixed(4) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Configuration Modal -->
    <div
      v-if="showConfigModal"
      class="fixed inset-0 bg-autobot-bg-secondary bg-opacity-75 flex items-center justify-center z-50"
      @click.self="closeConfigModal"
    >
      <div class="bg-autobot-bg-card rounded shadow-xl max-w-lg w-full mx-4 p-6 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-primary">Configure {{ selectedProvider }}</h3>
          <button
            @click="closeConfigModal"
            class="text-autobot-text-muted hover:text-secondary"
            aria-label="Close configuration modal"
          >
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="space-y-4">
          <!-- API Key -->
          <div>
            <label class="block text-sm font-medium text-secondary mb-1">API Key</label>
            <input
              v-model="configForm.api_key"
              type="password"
              placeholder="Leave blank to keep existing key"
              class="w-full px-3 py-2 text-sm border border-default rounded bg-autobot-bg-secondary text-primary focus:outline-none focus:ring-2 focus:ring-autobot-primary"
              autocomplete="new-password"
            />
          </div>

          <!-- Model -->
          <div>
            <label class="block text-sm font-medium text-secondary mb-1">Model</label>
            <select
              v-model="configForm.model"
              class="w-full px-3 py-2 text-sm border border-default rounded bg-autobot-bg-secondary text-primary focus:outline-none focus:ring-2 focus:ring-autobot-primary"
            >
              <option value="">Select a model</option>
              <option v-for="m in models" :key="m.id" :value="m.id">{{ m.name || m.id }}</option>
            </select>
          </div>

          <!-- Endpoint -->
          <div>
            <label class="block text-sm font-medium text-secondary mb-1">Endpoint URL</label>
            <input
              v-model="configForm.endpoint"
              type="url"
              placeholder="https://api.example.com/v1"
              class="w-full px-3 py-2 text-sm border border-default rounded bg-autobot-bg-secondary text-primary focus:outline-none focus:ring-2 focus:ring-autobot-primary"
            />
          </div>

          <!-- Temperature -->
          <div>
            <label class="block text-sm font-medium text-secondary mb-1">
              Temperature: {{ configForm.temperature }}
            </label>
            <input
              v-model.number="configForm.temperature"
              type="range"
              min="0"
              max="2"
              step="0.1"
              class="w-full accent-autobot-primary"
            />
          </div>

          <!-- Max Tokens -->
          <div>
            <label class="block text-sm font-medium text-secondary mb-1">Max Tokens</label>
            <input
              v-model.number="configForm.max_tokens"
              type="number"
              min="1"
              max="128000"
              class="w-full px-3 py-2 text-sm border border-default rounded bg-autobot-bg-secondary text-primary focus:outline-none focus:ring-2 focus:ring-autobot-primary"
            />
          </div>
        </div>

        <!-- Test Result -->
        <div
          v-if="configTestResult"
          class="mt-4 p-3 rounded text-sm"
          :class="configTestResult.success ? 'bg-green-900/20 text-green-400' : 'bg-red-900/20 text-red-400'"
        >
          {{ configTestResult.message }}
        </div>

        <div class="flex justify-between mt-6">
          <button
            @click="handleTestConfig"
            :disabled="isSavingConfig"
            class="px-4 py-2 text-sm font-medium text-secondary bg-autobot-bg-secondary border border-default rounded hover:bg-autobot-bg-tertiary disabled:opacity-50"
          >
            {{ isSavingConfig ? 'Working...' : 'Test Connection' }}
          </button>
          <div class="flex gap-3">
            <button
              @click="closeConfigModal"
              class="px-4 py-2 text-sm font-medium text-secondary bg-autobot-bg-card border border-default rounded hover:bg-autobot-bg-secondary"
            >
              Cancel
            </button>
            <button
              @click="handleSaveConfig"
              :disabled="isSavingConfig"
              class="px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover disabled:opacity-50"
            >
              {{ isSavingConfig ? 'Saving...' : 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
