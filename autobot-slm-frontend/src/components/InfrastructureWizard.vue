<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Infrastructure Wizard Component
 *
 * Issue #786: Multi-step wizard for running infrastructure setup playbooks
 * such as database deployment, monitoring setup, etc.
 */

import { ref, computed, watch, onMounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('InfrastructureWizard')

interface PlaybookInfo {
  id: string
  name: string
  description: string
  category: string
  playbook_file: string
  target_hosts: string[]
  variables: Record<string, unknown>
  estimated_duration: string
  requires_confirmation: boolean
}

interface PlaybookExecution {
  execution_id: string
  playbook_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  started_at: string | null
  completed_at: string | null
  output: string[]
  error: string | null
  triggered_by: string
}

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  executed: [executionId: string]
}>()

const step = ref(1)
const playbooks = ref<PlaybookInfo[]>([])
const selectedPlaybookId = ref<string>('')
const isLoadingPlaybooks = ref(false)
const isExecuting = ref(false)
const executeError = ref<string | null>(null)
const currentExecution = ref<PlaybookExecution | null>(null)
const customVariables = ref<Record<string, string>>({})
const confirmationChecked = ref(false)

// Polling interval for execution status
let statusPollInterval: ReturnType<typeof setInterval> | null = null

const selectedPlaybook = computed(() =>
  playbooks.value.find((p) => p.id === selectedPlaybookId.value)
)

const canProceedStep1 = computed(() => selectedPlaybookId.value !== '')

const canProceedStep2 = computed(() => {
  if (!selectedPlaybook.value) return false
  if (selectedPlaybook.value.requires_confirmation && !confirmationChecked.value) {
    return false
  }
  return true
})

const playbooksByCategory = computed(() => {
  const groups: Record<string, PlaybookInfo[]> = {}
  for (const playbook of playbooks.value) {
    if (!groups[playbook.category]) {
      groups[playbook.category] = []
    }
    groups[playbook.category].push(playbook)
  }
  return groups
})

const isExecutionComplete = computed(() =>
  currentExecution.value?.status === 'completed' ||
  currentExecution.value?.status === 'failed' ||
  currentExecution.value?.status === 'cancelled'
)

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      reset()
      loadPlaybooks()
    } else {
      stopPolling()
    }
  }
)

onMounted(() => {
  if (props.visible) {
    loadPlaybooks()
  }
})

function reset(): void {
  step.value = 1
  selectedPlaybookId.value = ''
  executeError.value = null
  currentExecution.value = null
  customVariables.value = {}
  confirmationChecked.value = false
  stopPolling()
}

function stopPolling(): void {
  if (statusPollInterval) {
    clearInterval(statusPollInterval)
    statusPollInterval = null
  }
}

async function loadPlaybooks(): Promise<void> {
  isLoadingPlaybooks.value = true
  try {
    const response = await fetch('/api/infrastructure/playbooks', {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('slm_access_token')}`,
      },
    })
    if (response.ok) {
      const data = await response.json()
      playbooks.value = data.playbooks
    } else {
      logger.error('Failed to load playbooks:', response.statusText)
    }
  } catch (e) {
    logger.error('Error loading playbooks:', e)
  } finally {
    isLoadingPlaybooks.value = false
  }
}

async function execute(): Promise<void> {
  if (!selectedPlaybook.value) return

  isExecuting.value = true
  executeError.value = null

  try {
    const response = await fetch('/api/infrastructure/execute', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('slm_access_token')}`,
      },
      body: JSON.stringify({
        playbook_id: selectedPlaybookId.value,
        variables: customVariables.value,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to execute playbook')
    }

    const data = await response.json()
    currentExecution.value = data.execution
    step.value = 3

    // Start polling for status
    startStatusPolling(data.execution.execution_id)
  } catch (e) {
    executeError.value = e instanceof Error ? e.message : 'Failed to execute playbook'
  } finally {
    isExecuting.value = false
  }
}

function startStatusPolling(executionId: string): void {
  stopPolling()
  statusPollInterval = setInterval(async () => {
    await pollExecutionStatus(executionId)
  }, 1000)
}

async function pollExecutionStatus(executionId: string): Promise<void> {
  try {
    const response = await fetch(`/api/infrastructure/executions/${executionId}`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('slm_access_token')}`,
      },
    })

    if (response.ok) {
      const data = await response.json()
      currentExecution.value = data.execution

      // Stop polling when execution is complete
      if (isExecutionComplete.value) {
        stopPolling()
        emit('executed', executionId)
      }
    }
  } catch (e) {
    logger.error('Error polling execution status:', e)
  }
}

async function cancelExecution(): Promise<void> {
  if (!currentExecution.value) return

  try {
    const response = await fetch(
      `/api/infrastructure/executions/${currentExecution.value.execution_id}/cancel`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('slm_access_token')}`,
        },
      }
    )

    if (response.ok) {
      const data = await response.json()
      currentExecution.value = data.execution
      stopPolling()
    }
  } catch (e) {
    logger.error('Error cancelling execution:', e)
  }
}

function nextStep(): void {
  if (step.value < 3) {
    step.value++
  }
}

function prevStep(): void {
  if (step.value > 1) {
    step.value--
  }
}

function getCategoryIcon(category: string): string {
  switch (category) {
    case 'database':
      return 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4'
    case 'monitoring':
      return 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'
    case 'security':
      return 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z'
    case 'networking':
      return 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9'
    case 'storage':
      return 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4'
    default:
      return 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z'
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'text-green-600 bg-green-100'
    case 'failed':
      return 'text-red-600 bg-red-100'
    case 'running':
      return 'text-blue-600 bg-blue-100'
    case 'cancelled':
      return 'text-gray-600 bg-gray-100'
    default:
      return 'text-yellow-600 bg-yellow-100'
  }
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
    @click.self="$emit('close')"
  >
    <div class="bg-white rounded-lg shadow-xl w-full max-w-3xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <div>
          <h3 class="text-lg font-semibold text-gray-900">Infrastructure Setup Wizard</h3>
          <p class="text-sm text-gray-500">Step {{ step }} of 3</p>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-600 transition-colors"
          :disabled="currentExecution?.status === 'running'"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Progress Bar -->
      <div class="px-6 pt-4">
        <div class="flex items-center gap-2">
          <div
            v-for="s in 3"
            :key="s"
            :class="[
              'flex-1 h-2 rounded-full transition-colors',
              s <= step ? 'bg-primary-600' : 'bg-gray-200',
            ]"
          />
        </div>
        <div class="flex justify-between mt-2 text-xs text-gray-500">
          <span>Select Playbook</span>
          <span>Review & Configure</span>
          <span>Execute</span>
        </div>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto px-6 py-4">
        <!-- Step 1: Select Playbook -->
        <div v-if="step === 1">
          <h4 class="text-base font-medium text-gray-900 mb-4">Select Infrastructure Playbook</h4>

          <div v-if="isLoadingPlaybooks" class="flex items-center justify-center py-8">
            <div class="animate-spin w-6 h-6 border-2 border-primary-600 border-t-transparent rounded-full" />
          </div>

          <div v-else class="space-y-6">
            <div v-for="(categoryPlaybooks, category) in playbooksByCategory" :key="category">
              <div class="flex items-center gap-2 mb-3">
                <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getCategoryIcon(category)" />
                </svg>
                <h5 class="text-sm font-medium text-gray-700 uppercase tracking-wide">{{ category }}</h5>
              </div>
              <div class="space-y-2">
                <div
                  v-for="playbook in categoryPlaybooks"
                  :key="playbook.id"
                  @click="selectedPlaybookId = playbook.id"
                  :class="[
                    'p-4 border rounded-lg cursor-pointer transition-all',
                    selectedPlaybookId === playbook.id
                      ? 'border-primary-500 bg-primary-50 ring-2 ring-primary-200'
                      : 'border-gray-200 hover:border-gray-300',
                  ]"
                >
                  <div class="flex items-start gap-3">
                    <div
                      :class="[
                        'w-5 h-5 mt-0.5 rounded-full border-2 flex items-center justify-center transition-colors',
                        selectedPlaybookId === playbook.id
                          ? 'border-primary-500 bg-primary-500'
                          : 'border-gray-300',
                      ]"
                    >
                      <div
                        v-if="selectedPlaybookId === playbook.id"
                        class="w-2 h-2 bg-white rounded-full"
                      />
                    </div>
                    <div class="flex-1">
                      <div class="font-medium text-gray-900">{{ playbook.name }}</div>
                      <div class="text-sm text-gray-500 mt-1">{{ playbook.description }}</div>
                      <div class="flex flex-wrap gap-2 mt-2">
                        <span
                          v-for="host in playbook.target_hosts"
                          :key="host"
                          class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
                        >
                          {{ host }}
                        </span>
                        <span class="px-2 py-0.5 text-xs bg-blue-100 text-blue-600 rounded">
                          ~{{ playbook.estimated_duration }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 2: Review & Configure -->
        <div v-else-if="step === 2 && selectedPlaybook">
          <h4 class="text-base font-medium text-gray-900 mb-4">Review Configuration</h4>

          <!-- Error Message -->
          <div
            v-if="executeError"
            class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
          >
            {{ executeError }}
          </div>

          <div class="space-y-4">
            <!-- Playbook Summary -->
            <div class="p-4 bg-gray-50 rounded-lg">
              <div class="text-sm text-gray-500 mb-1">Selected Playbook</div>
              <div class="font-medium text-gray-900">{{ selectedPlaybook.name }}</div>
              <div class="text-sm text-gray-600 mt-1">{{ selectedPlaybook.description }}</div>
            </div>

            <!-- Target Hosts -->
            <div class="p-4 bg-gray-50 rounded-lg">
              <div class="text-sm text-gray-500 mb-2">Target Hosts</div>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="host in selectedPlaybook.target_hosts"
                  :key="host"
                  class="px-3 py-1 bg-primary-100 text-primary-700 rounded-full text-sm font-medium"
                >
                  {{ host }}
                </span>
              </div>
            </div>

            <!-- Default Variables -->
            <div class="p-4 bg-gray-50 rounded-lg">
              <div class="text-sm text-gray-500 mb-2">Default Variables</div>
              <div class="font-mono text-sm">
                <div
                  v-for="(value, key) in selectedPlaybook.variables"
                  :key="key"
                  class="flex justify-between py-1 border-b border-gray-200 last:border-0"
                >
                  <span class="text-gray-600">{{ key }}:</span>
                  <span class="text-gray-900">{{ value }}</span>
                </div>
              </div>
            </div>

            <!-- Warning/Confirmation -->
            <div
              v-if="selectedPlaybook.requires_confirmation"
              class="p-4 bg-amber-50 border border-amber-200 rounded-lg"
            >
              <div class="flex items-start gap-3">
                <svg class="w-5 h-5 text-amber-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div class="flex-1">
                  <p class="font-medium text-amber-800">Confirmation Required</p>
                  <p class="text-sm text-amber-700 mt-1">
                    This playbook will make changes to your infrastructure. Please review the configuration carefully before proceeding.
                  </p>
                  <label class="flex items-center gap-2 mt-3">
                    <input
                      v-model="confirmationChecked"
                      type="checkbox"
                      class="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span class="text-sm text-amber-800">
                      I understand the changes and want to proceed
                    </span>
                  </label>
                </div>
              </div>
            </div>

            <!-- What happens next -->
            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div class="flex items-start gap-3">
                <svg class="w-5 h-5 text-blue-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div class="text-sm text-blue-700">
                  <p class="font-medium">What happens next?</p>
                  <ul class="mt-1 space-y-1 text-blue-600">
                    <li>1. Ansible playbook will be executed</li>
                    <li>2. SSH connections to target hosts established</li>
                    <li>3. Infrastructure components installed and configured</li>
                    <li>4. Services will be started and verified</li>
                  </ul>
                  <p class="mt-2 text-blue-500">
                    Estimated time: {{ selectedPlaybook.estimated_duration }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 3: Execution -->
        <div v-else-if="step === 3 && currentExecution">
          <div class="flex items-center justify-between mb-4">
            <h4 class="text-base font-medium text-gray-900">Execution Progress</h4>
            <span
              :class="[
                'px-3 py-1 rounded-full text-sm font-medium',
                getStatusColor(currentExecution.status),
              ]"
            >
              {{ currentExecution.status }}
            </span>
          </div>

          <!-- Output Console -->
          <div class="bg-gray-900 rounded-lg p-4 font-mono text-sm h-96 overflow-y-auto">
            <div
              v-for="(line, index) in currentExecution.output"
              :key="index"
              :class="[
                'whitespace-pre-wrap',
                line.startsWith('[SUCCESS]') ? 'text-green-400' :
                line.startsWith('[FAILED]') || line.startsWith('[ERROR]') ? 'text-red-400' :
                line.startsWith('[WARNING]') ? 'text-yellow-400' :
                line.startsWith('[INFO]') ? 'text-blue-400' :
                line.startsWith('TASK') ? 'text-cyan-400' :
                line.startsWith('PLAY') ? 'text-purple-400 font-bold' :
                line.includes('changed:') ? 'text-yellow-300' :
                line.includes('ok:') ? 'text-green-300' :
                'text-gray-300'
              ]"
            >
              {{ line }}
            </div>
            <div
              v-if="currentExecution.status === 'running'"
              class="inline-block w-2 h-4 bg-gray-300 animate-pulse ml-1"
            />
          </div>

          <!-- Error Display -->
          <div
            v-if="currentExecution.error"
            class="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
          >
            <strong>Error:</strong> {{ currentExecution.error }}
          </div>

          <!-- Completion Message -->
          <div
            v-if="currentExecution.status === 'completed'"
            class="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg"
          >
            <div class="flex items-center gap-3">
              <svg class="w-6 h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p class="font-medium text-green-800">Infrastructure setup completed successfully!</p>
                <p class="text-sm text-green-600 mt-1">
                  All tasks have been executed. You may need to restart services or run migrations.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50">
        <button
          v-if="step > 1 && step < 3"
          @click="prevStep"
          class="btn btn-secondary"
          :disabled="isExecuting"
        >
          Back
        </button>
        <div v-else></div>

        <div class="flex gap-3">
          <button
            v-if="currentExecution?.status === 'running'"
            @click="cancelExecution"
            class="btn btn-secondary text-red-600 hover:bg-red-50"
          >
            Cancel Execution
          </button>
          <button
            @click="$emit('close')"
            class="btn btn-secondary"
            :disabled="currentExecution?.status === 'running'"
          >
            {{ isExecutionComplete ? 'Close' : 'Cancel' }}
          </button>
          <button
            v-if="step === 1"
            @click="nextStep"
            :disabled="!canProceedStep1"
            class="btn btn-primary"
          >
            Next
          </button>
          <button
            v-else-if="step === 2"
            @click="execute"
            :disabled="!canProceedStep2 || isExecuting"
            class="btn btn-primary flex items-center gap-2"
          >
            <svg
              v-if="isExecuting"
              class="animate-spin w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ isExecuting ? 'Starting...' : 'Execute Playbook' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
