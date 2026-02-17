<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LLMConfigView - Main LLM configuration and monitoring view
 * Issue #897 - LLM Configuration Panel
 */

import { ref, onMounted, computed } from 'vue'
import { useLlmConfig } from '@/composables/useLlmConfig'
import { useLlmHealth } from '@/composables/useLlmHealth'
import LLMProviderCard from '@/components/llm/LLMProviderCard.vue'
import LLMHealthMonitor from '@/components/llm/LLMHealthMonitor.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LLMConfigView')

const {
  config,
  providers,
  currentProvider,
  isLoading: configLoading,
  error: configError,
  fetchProviders,
  fetchConfig,
  switchProvider,
  testProviderConnection,
} = useLlmConfig({ autoFetch: false })

const {
  healthMetrics,
  healthSummary,
  isLoading: healthLoading,
  error: healthError,
  lastUpdate,
  refreshAll: refreshHealth,
} = useLlmHealth({ autoFetch: false, pollInterval: 60000 })

const activeTab = ref<'providers' | 'health' | 'usage'>('providers')
const showConfigModal = ref(false)
const selectedProvider = ref<string | null>(null)

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

function handleConfigure(providerName: string) {
  logger.debug('Opening configuration for provider:', providerName)
  selectedProvider.value = providerName
  showConfigModal.value = true
}

function closeConfigModal() {
  showConfigModal.value = false
  selectedProvider.value = null
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
          <div class="text-center py-12 text-secondary">
            <svg class="mx-auto h-12 w-12 text-autobot-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p class="mt-4">Usage statistics coming soon</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Configuration Modal (placeholder) -->
    <div
      v-if="showConfigModal"
      class="fixed inset-0 bg-autobot-bg-secondary0 bg-opacity-75 flex items-center justify-center z-50"
      @click.self="closeConfigModal"
    >
      <div class="bg-autobot-bg-card rounded shadow-xl max-w-md w-full mx-4 p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-primary">Configure Provider</h3>
          <button
            @click="closeConfigModal"
            class="text-autobot-text-muted hover:text-secondary"
          >
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <p class="text-sm text-secondary mb-4">
          Configuration interface for {{ selectedProvider }} coming soon.
        </p>
        <div class="flex justify-end">
          <button
            @click="closeConfigModal"
            class="px-4 py-2 text-sm font-medium text-primary bg-autobot-bg-card border border-default rounded hover:bg-autobot-bg-secondary"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
