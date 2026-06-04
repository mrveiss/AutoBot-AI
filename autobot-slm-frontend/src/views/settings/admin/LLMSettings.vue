// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * LLMSettings - LLM Provider Configuration (#2371)
 *
 * Admin-only page for managing LLM provider configuration.
 * Config is stored on SLM and pushed to fleet nodes via Ansible.
 */

import { ref, reactive, onMounted } from 'vue'
import {
  useLlmConfigApi,
  type LLMConfig,
  type LLMProviderConfig,
  type LLMTestResponse,
} from '@/composables/useLlmConfigApi'
import ssotConfig from '@/config/ssot-config'

const api = useLlmConfigApi()

const loading = ref(false)
const saving = ref(false)
const applying = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const testResult = ref<LLMTestResponse | null>(null)

const activeTab = ref<'providers' | 'server' | 'models'>('providers')

const config = reactive<LLMConfig>({
  active_provider: 'ollama',
  providers: [],
  ollama_host: '0.0.0.0',
  ollama_port: ssotConfig.port.ollama,
  gpu_models: [],
  cpu_models: [],
  max_loaded_models: 5,
  num_parallel: 4,
  keep_alive: '10m',
  flash_attention: true,
  kv_cache_type: 'q8_0',
})

const showAddProvider = ref(false)
const newProvider = reactive<LLMProviderConfig>({
  name: '',
  enabled: false,
  api_key: '',
  endpoint: '',
  model: '',
  temperature: 0.7,
  max_tokens: 2048,
})

const newGpuModel = ref('')
const newCpuModel = ref('')
const hasUnsavedChanges = ref(false)

function markDirty() {
  hasUnsavedChanges.value = true
}

function showSuccessMsg(msg: string) {
  success.value = msg
  setTimeout(() => { success.value = null }, 3000)
}

async function fetchConfig(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const resp = await api.getConfig()
    Object.assign(config, resp.config)
    hasUnsavedChanges.value = false
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Failed to load LLM config'
  } finally {
    loading.value = false
  }
}

async function saveConfig(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    const resp = await api.saveConfig({ ...config })
    Object.assign(config, resp.config)
    hasUnsavedChanges.value = false
    showSuccessMsg('Configuration saved')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Failed to save LLM config'
  } finally {
    saving.value = false
  }
}

async function testProvider(provider: LLMProviderConfig): Promise<void> {
  testResult.value = null
  error.value = null
  try {
    testResult.value = await api.testConnection({
      provider: provider.name,
      endpoint: provider.endpoint,
      api_key: provider.api_key,
      model: provider.model,
    })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Connection test failed'
  }
}

async function applyToFleet(): Promise<void> {
  if (hasUnsavedChanges.value) {
    error.value = 'Save configuration before applying to fleet'
    return
  }
  applying.value = true
  error.value = null
  try {
    const resp = await api.applyToFleet()
    if (resp.success) {
      showSuccessMsg(`Config applied to ${resp.node_count} nodes`)
    } else {
      error.value = resp.message || 'Apply failed'
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Failed to apply config to fleet'
  } finally {
    applying.value = false
  }
}

function addProvider(): void {
  if (!newProvider.name) return
  config.providers.push({ ...newProvider })
  newProvider.name = ''
  newProvider.enabled = false
  newProvider.api_key = ''
  newProvider.endpoint = ''
  newProvider.model = ''
  newProvider.temperature = 0.7
  newProvider.max_tokens = 2048
  showAddProvider.value = false
  markDirty()
}

function removeProvider(index: number): void {
  const name = config.providers[index]?.name
  if (!confirm(`Remove provider "${name}"?`)) return
  config.providers.splice(index, 1)
  markDirty()
}

function toggleProvider(index: number): void {
  config.providers[index].enabled = !config.providers[index].enabled
  markDirty()
}

function setActiveProvider(name: string): void {
  config.active_provider = name
  markDirty()
}

function addModel(type: 'gpu' | 'cpu'): void {
  if (type === 'gpu' && newGpuModel.value) {
    config.gpu_models.push(newGpuModel.value)
    newGpuModel.value = ''
    markDirty()
  } else if (type === 'cpu' && newCpuModel.value) {
    config.cpu_models.push(newCpuModel.value)
    newCpuModel.value = ''
    markDirty()
  }
}

function removeModel(type: 'gpu' | 'cpu', index: number): void {
  if (type === 'gpu') {
    config.gpu_models.splice(index, 1)
  } else {
    config.cpu_models.splice(index, 1)
  }
  markDirty()
}

onMounted(fetchConfig)
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <div
      v-if="error"
      class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-3"
    >
      <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ error }}
      <button class="ml-auto text-red-500 hover:text-red-700" @click="error = null" aria-label="Dismiss error">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div
      v-if="success"
      class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3"
    >
      <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ success }}
    </div>

    <!-- Test Result Banner -->
    <div
      v-if="testResult"
      class="p-4 rounded-lg flex items-center gap-3"
      :class="testResult.success
        ? 'bg-green-50 border border-green-200 text-green-700'
        : 'bg-red-50 border border-red-200 text-red-700'"
    >
      <span class="font-medium">{{ testResult.provider }}:</span>
      {{ testResult.message }}
      <span v-if="testResult.latency_ms" class="text-sm opacity-75">
        ({{ testResult.latency_ms }}ms)
      </span>
      <button class="ml-auto opacity-60 hover:opacity-100" @click="testResult = null" aria-label="Dismiss">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">{{ $t('settings.admin.lLMSettings.lLMConfiguration') }}</h2>
        <p class="text-sm text-gray-500 mt-1">
          {{ $t('settings.admin.lLMSettings.manageLLMProvidersModels') }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="hasUnsavedChanges" class="text-sm text-amber-600 font-medium">{{ $t('settings.admin.lLMSettings.unsavedChanges') }}</span>
        <button
          :disabled="!hasUnsavedChanges || saving"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          @click="saveConfig"
        >
          {{ saving ? 'Saving...' : 'Save' }}
        </button>
        <button
          :disabled="hasUnsavedChanges || applying"
          class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          @click="applyToFleet"
        >
          {{ applying ? 'Applying...' : 'Apply to Fleet' }}
        </button>
        <button
          :disabled="loading"
          class="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 transition-colors text-sm"
          @click="fetchConfig"
        >
          <svg :class="['w-4 h-4', { 'animate-spin': loading }]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200">
      <nav class="-mb-px flex space-x-8">
        <button
          v-for="tab in [
            { id: 'providers', label: 'Providers' },
            { id: 'server', label: 'Server Settings' },
            { id: 'models', label: 'Models' },
          ]"
          :key="tab.id"
          @click="activeTab = tab.id as 'providers' | 'server' | 'models'"
          :class="[
            'py-3 px-1 border-b-2 font-medium text-sm transition-colors',
            activeTab === tab.id
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>

    <!-- Providers Tab -->
    <div v-else-if="activeTab === 'providers'" class="space-y-4">
      <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium text-blue-800">{{ $t('settings.admin.lLMSettings.activeProvider') }}</span>
          <span class="text-sm text-blue-700 font-mono">{{ config.active_provider }}</span>
        </div>
      </div>

      <div class="flex justify-end">
        <button
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          @click="showAddProvider = !showAddProvider"
        >
          {{ showAddProvider ? 'Cancel' : 'Add Provider' }}
        </button>
      </div>

      <div v-if="showAddProvider" class="bg-gray-50 border border-gray-200 rounded-lg p-5 space-y-4">
        <h3 class="font-medium text-gray-900">{{ $t('settings.admin.lLMSettings.newProvider') }}</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.name') }}</label>
            <input v-model="newProvider.name" type="text" placeholder="e.g. ollama, openai, anthropic"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.model') }}</label>
            <input v-model="newProvider.model" type="text" placeholder="e.g. mistral:7b-instruct"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.endpoint') }}</label>
            <input v-model="newProvider.endpoint" type="url" placeholder="https://api.example.com/v1"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.aPIKey') }}</label>
            <input v-model="newProvider.api_key" type="password" placeholder="API key (encrypted at rest)"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm font-mono" />
          </div>
        </div>
        <div class="flex justify-end">
          <button :disabled="!newProvider.name"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
            @click="addProvider">
            {{ $t('settings.admin.lLMSettings.addProvider') }}
          </button>
        </div>
      </div>

      <div v-if="config.providers.length === 0" class="text-center py-12 bg-gray-50 rounded-lg border border-gray-200">
        <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
        <h3 class="mt-2 text-sm font-medium text-gray-900">{{ $t('settings.admin.lLMSettings.noProvidersConfigured') }}</h3>
        <p class="mt-1 text-sm text-gray-500">{{ $t('settings.admin.lLMSettings.addAnLLMProvider') }}</p>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="(provider, idx) in config.providers" :key="provider.name"
          class="border rounded-lg p-4"
          :class="config.active_provider === provider.name ? 'border-blue-300 bg-blue-50' : 'border-gray-200 bg-white'">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-900">{{ provider.name }}</span>
              <span v-if="config.active_provider === provider.name"
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">{{ $t('settings.admin.lLMSettings.active') }}</span>
              <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
                :class="provider.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'">
                {{ provider.enabled ? 'Enabled' : 'Disabled' }}
              </span>
            </div>
            <button class="text-red-500 hover:text-red-700 text-sm" @click="removeProvider(idx)">{{ $t('settings.admin.lLMSettings.remove') }}</button>
          </div>
          <div class="text-sm text-gray-600 space-y-1">
            <div v-if="provider.model"><span class="font-medium">{{ $t('settings.admin.lLMSettings.model1') }}</span> {{ provider.model }}</div>
            <div v-if="provider.endpoint"><span class="font-medium">{{ $t('settings.admin.lLMSettings.endpoint1') }}</span> {{ provider.endpoint }}</div>
            <div><span class="font-medium">{{ $t('settings.admin.lLMSettings.temperature') }}</span> {{ provider.temperature }}</div>
          </div>
          <div class="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100">
            <button class="text-sm text-blue-600 hover:text-blue-800" @click="setActiveProvider(provider.name)">{{ $t('settings.admin.lLMSettings.setActive') }}</button>
            <button class="text-sm text-gray-600 hover:text-gray-800" @click="toggleProvider(idx)">
              {{ provider.enabled ? 'Disable' : 'Enable' }}
            </button>
            <button class="text-sm text-green-600 hover:text-green-800" @click="testProvider(provider)">{{ $t('settings.admin.lLMSettings.test') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Server Settings Tab -->
    <div v-else-if="activeTab === 'server'" class="space-y-6">
      <div class="bg-white border border-gray-200 rounded-lg p-6">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('settings.admin.lLMSettings.ollamaServer') }}</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.listenHost') }}</label>
            <input v-model="config.ollama_host" type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
              @input="markDirty" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.port') }}</label>
            <input v-model.number="config.ollama_port" type="number"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
              @input="markDirty" />
          </div>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-lg p-6">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('settings.admin.lLMSettings.concurrency') }}</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.maxLoadedModels') }}</label>
            <input v-model.number="config.max_loaded_models" type="number" min="1" max="20"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
              @input="markDirty" />
            <p class="text-xs text-gray-500 mt-1">{{ $t('settings.admin.lLMSettings.modelsKeptHotIn') }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.parallelRequests') }}</label>
            <input v-model.number="config.num_parallel" type="number" min="1" max="16"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
              @input="markDirty" />
            <p class="text-xs text-gray-500 mt-1">{{ $t('settings.admin.lLMSettings.concurrentRequestsPerModel') }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.keepAlive') }}</label>
            <input v-model="config.keep_alive" type="text" placeholder="10m"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
              @input="markDirty" />
            <p class="text-xs text-gray-500 mt-1">{{ $t('settings.admin.lLMSettings.idleTimeoutBeforeUnloading') }}</p>
          </div>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-lg p-6">
        <h3 class="text-sm font-semibold text-gray-900 mb-4">{{ $t('settings.admin.lLMSettings.performance') }}</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="flex items-center justify-between">
            <div>
              <label class="text-sm font-medium text-gray-700">{{ $t('settings.admin.lLMSettings.flashAttention') }}</label>
              <p class="text-xs text-gray-500">{{ $t('settings.admin.lLMSettings.fasterAttentionComputation') }}</p>
            </div>
            <button
              @click="config.flash_attention = !config.flash_attention; markDirty()"
              :class="['relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                config.flash_attention ? 'bg-blue-600' : 'bg-gray-300']">
              <span :class="['inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                config.flash_attention ? 'translate-x-6' : 'translate-x-1']" />
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('settings.admin.lLMSettings.kVCacheType') }}</label>
            <select v-model="config.kv_cache_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
              @change="markDirty">
              <option value="q8_0">{{ $t('settings.admin.lLMSettings.q80QuantizedLess') }}</option>
              <option value="f16">{{ $t('settings.admin.lLMSettings.f16FullPrecision') }}</option>
              <option value="f32">{{ $t('settings.admin.lLMSettings.f32MaximumPrecision') }}</option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- Models Tab -->
    <div v-else-if="activeTab === 'models'" class="space-y-6">
      <div class="bg-white border border-gray-200 rounded-lg p-6">
        <div class="mb-4">
          <h3 class="text-sm font-semibold text-gray-900">{{ $t('settings.admin.lLMSettings.gPUModels') }}</h3>
          <p class="text-xs text-gray-500">{{ $t('settings.admin.lLMSettings.requireGPUForReasonable') }}</p>
        </div>
        <div class="flex gap-2 mb-3">
          <input v-model="newGpuModel" type="text" placeholder="e.g. mistral:7b-instruct"
            class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
            @keyup.enter="addModel('gpu')" />
          <button :disabled="!newGpuModel"
            class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 text-sm"
            @click="addModel('gpu')">{{ $t('settings.admin.lLMSettings.add') }}</button>
        </div>
        <div v-if="config.gpu_models.length === 0" class="text-sm text-gray-500 py-4 text-center">{{ $t('settings.admin.lLMSettings.noGPUModelsConfigured') }}</div>
        <div v-else class="flex flex-wrap gap-2">
          <span v-for="(model, idx) in config.gpu_models" :key="model"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-purple-50 border border-purple-200 text-sm font-mono text-purple-800">
            {{ model }}
            <button class="text-purple-400 hover:text-purple-700" @click="removeModel('gpu', idx)">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </span>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-lg p-6">
        <div class="mb-4">
          <h3 class="text-sm font-semibold text-gray-900">{{ $t('settings.admin.lLMSettings.cPUModels') }}</h3>
          <p class="text-xs text-gray-500">{{ $t('settings.admin.lLMSettings.lightweightModelsThatRun') }}</p>
        </div>
        <div class="flex gap-2 mb-3">
          <input v-model="newCpuModel" type="text" placeholder="e.g. nomic-embed-text"
            class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
            @keyup.enter="addModel('cpu')" />
          <button :disabled="!newCpuModel"
            class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 text-sm"
            @click="addModel('cpu')">{{ $t('settings.admin.lLMSettings.add') }}</button>
        </div>
        <div v-if="config.cpu_models.length === 0" class="text-sm text-gray-500 py-4 text-center">{{ $t('settings.admin.lLMSettings.noCPUModelsConfigured') }}</div>
        <div v-else class="flex flex-wrap gap-2">
          <span v-for="(model, idx) in config.cpu_models" :key="model"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-200 text-sm font-mono text-blue-800">
            {{ model }}
            <button class="text-blue-400 hover:text-blue-700" @click="removeModel('cpu', idx)">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </span>
        </div>
      </div>
    </div>

    <!-- Info Box -->
    <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
      <div class="flex gap-3">
        <svg class="w-5 h-5 text-blue-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div class="text-sm text-blue-800">
          <p class="font-medium">{{ $t('settings.admin.lLMSettings.aboutLLMConfiguration') }}</p>
          <p class="mt-1">
            {{ $t('settings.admin.lLMSettings.changesSavedHereAre') }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
