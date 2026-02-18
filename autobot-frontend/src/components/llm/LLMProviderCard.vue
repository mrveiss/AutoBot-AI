<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LLMProviderCard - Individual LLM provider configuration card
 * Issue #897 - LLM Configuration Panel
 */

import { ref, computed } from 'vue'
import type { LLMProvider } from '@/composables/useLlmConfig'
import type { ConnectionTestResult } from '@/composables/useLlmConfig'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LLMProviderCard')

interface Props {
  provider: LLMProvider
  isActive: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  activate: [providerName: string]
  test: [providerName: string]
  configure: [providerName: string]
}>()

const testing = ref(false)
const testResult = ref<ConnectionTestResult | null>(null)

const statusColor = computed(() => {
  if (!props.provider.is_available) return 'bg-autobot-bg-secondary text-secondary'
  if (props.isActive) return 'bg-autobot-success-bg text-autobot-success'
  return 'bg-autobot-warning-bg text-autobot-warning'
})

const statusText = computed(() => {
  if (!props.provider.is_available) return 'Unavailable'
  if (props.isActive) return 'Active'
  return 'Available'
})

function handleActivate() {
  logger.debug('Activating provider:', props.provider.name)
  emit('activate', props.provider.name)
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  logger.debug('Testing provider:', props.provider.name)
  emit('test', props.provider.name)
  // Simulate test delay
  setTimeout(() => {
    testing.value = false
  }, 2000)
}

function handleConfigure() {
  logger.debug('Configuring provider:', props.provider.name)
  emit('configure', props.provider.name)
}
</script>

<template>
  <div class="bg-autobot-bg-card rounded border border-default p-6 hover:shadow-md transition-shadow">
    <!-- Header -->
    <div class="flex items-start justify-between mb-4">
      <div class="flex-1">
        <h3 class="text-lg font-semibold text-primary">
          {{ provider.display_name }}
        </h3>
        <p class="text-sm text-secondary mt-1">
          {{ provider.models.length }} model{{ provider.models.length !== 1 ? 's' : '' }} available
        </p>
      </div>
      <span
        :class="['px-3 py-1 text-xs font-medium rounded-sm', statusColor]"
      >
        {{ statusText }}
      </span>
    </div>

    <!-- Models List -->
    <div v-if="provider.models.length > 0" class="mb-4">
      <div class="text-sm font-medium text-primary mb-2">Available Models:</div>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="model in provider.models.slice(0, 3)"
          :key="model"
          class="px-2 py-1 text-xs bg-autobot-bg-secondary text-primary rounded"
        >
          {{ model }}
        </span>
        <span
          v-if="provider.models.length > 3"
          class="px-2 py-1 text-xs bg-autobot-bg-secondary text-secondary rounded"
        >
          +{{ provider.models.length - 3 }} more
        </span>
      </div>
    </div>

    <!-- Test Result -->
    <div v-if="testResult" class="mb-4 p-3 rounded" :class="[
      testResult.success ? 'bg-success-50 border border-success-200' : 'bg-autobot-error-bg border border-autobot-error'
    ]">
      <div class="flex items-start gap-2">
        <svg
          v-if="testResult.success"
          class="w-5 h-5 text-autobot-success mt-0.5"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
        </svg>
        <svg
          v-else
          class="w-5 h-5 text-autobot-error mt-0.5"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <p :class="['text-sm font-medium', testResult.success ? 'text-autobot-success' : 'text-autobot-error']">
            {{ testResult.message }}
          </p>
          <p v-if="testResult.latency_ms" class="text-xs text-secondary mt-1">
            Latency: {{ testResult.latency_ms }}ms
          </p>
        </div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="flex gap-2">
      <button
        v-if="!isActive && provider.is_available"
        @click="handleActivate"
        class="flex-1 px-4 py-2 text-sm font-medium text-white bg-autobot-primary rounded hover:bg-autobot-primary-hover transition-colors"
      >
        Activate
      </button>
      <button
        v-if="isActive"
        disabled
        class="flex-1 px-4 py-2 text-sm font-medium text-white bg-autobot-success rounded cursor-default"
      >
        Active Provider
      </button>
      <button
        @click="handleTest"
        :disabled="testing || !provider.is_available"
        class="px-4 py-2 text-sm font-medium text-primary bg-autobot-bg-card border border-default rounded hover:bg-autobot-bg-secondary disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
      >
        <svg
          v-if="testing"
          class="animate-spin h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        {{ testing ? 'Testing...' : 'Test' }}
      </button>
      <button
        @click="handleConfigure"
        :disabled="!provider.is_available"
        class="px-4 py-2 text-sm font-medium text-primary bg-autobot-bg-card border border-default rounded hover:bg-autobot-bg-secondary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Configure
      </button>
    </div>
  </div>
</template>
