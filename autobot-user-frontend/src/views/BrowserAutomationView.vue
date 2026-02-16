<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * BrowserAutomationView - Browser control and automation dashboard
 * Issue #900 - Browser Automation Dashboard
 */

import { ref, computed } from 'vue'
import { useBrowserAutomation } from '@/composables/useBrowserAutomation'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BrowserAutomationView')

const {
  workerStatus,
  sessions,
  currentSession,
  screenshots,
  isLoading,
  error,
  launchSession,
  closeSession,
  navigate,
  click,
  type: typeText,
  takeScreenshot,
  executeScript,
  runAutomationScript,
  deleteSession,
} = useBrowserAutomation({ autoFetch: true, pollInterval: 5000 })

const activeTab = ref<'control' | 'sessions' | 'scripts'>('control')
const urlInput = ref('')
const selectorInput = ref('')
const textInput = ref('')
const scriptInput = ref('')
const automationScriptInput = ref('')

const statusColor = computed(() => {
  if (!workerStatus.value) return 'text-gray-500'
  switch (workerStatus.value.status) {
    case 'online': return 'text-success-600'
    case 'degraded': return 'text-warning-600'
    case 'offline': return 'text-danger-600'
    default: return 'text-gray-500'
  }
})

async function handleLaunchSession() {
  const url = urlInput.value.trim() || 'about:blank'
  const session = await launchSession(url)
  if (session) {
    logger.debug('Session launched:', session.id)
    urlInput.value = ''
  }
}

async function handleNavigate() {
  if (!currentSession.value || !urlInput.value.trim()) return
  const success = await navigate(currentSession.value.id, urlInput.value)
  if (success) {
    logger.debug('Navigation successful')
  }
}

async function handleClick() {
  if (!currentSession.value || !selectorInput.value.trim()) return
  const success = await click(currentSession.value.id, selectorInput.value)
  if (success) {
    logger.debug('Click successful')
    selectorInput.value = ''
  }
}

async function handleType() {
  if (!currentSession.value || !selectorInput.value.trim() || !textInput.value) return
  const success = await typeText(currentSession.value.id, selectorInput.value, textInput.value)
  if (success) {
    logger.debug('Type successful')
    textInput.value = ''
  }
}

async function handleScreenshot() {
  if (!currentSession.value) return
  const screenshot = await takeScreenshot(currentSession.value.id)
  if (screenshot) {
    logger.debug('Screenshot captured')
  }
}

async function handleExecuteScript() {
  if (!currentSession.value || !scriptInput.value.trim()) return
  const result = await executeScript(currentSession.value.id, scriptInput.value)
  logger.debug('Script result:', result)
  alert(`Script result: ${JSON.stringify(result, null, 2)}`)
}

async function handleRunAutomation() {
  if (!automationScriptInput.value.trim()) return
  const result = await runAutomationScript(automationScriptInput.value)
  logger.debug('Automation result:', result)
  alert(`Automation completed: ${JSON.stringify(result, null, 2)}`)
}

function selectSession(session: typeof sessions.value[0]) {
  currentSession.value = session
  activeTab.value = 'control'
}
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Browser Automation</h2>
        <p class="text-sm text-gray-500 mt-1">Control browser workers and automate web tasks</p>
      </div>
      <div v-if="workerStatus" class="text-right">
        <div class="text-sm text-gray-500">Worker Status</div>
        <div :class="['text-2xl font-bold', statusColor]">
          {{ workerStatus.status.toUpperCase() }}
        </div>
        <div class="text-xs text-gray-500">
          {{ workerStatus.active_sessions }}/{{ workerStatus.max_sessions }} sessions
        </div>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="bg-danger-50 border border-danger-200 rounded-lg p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-danger-600 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <h3 class="text-sm font-medium text-danger-800">Error</h3>
          <p class="text-sm text-danger-700 mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200">
      <nav class="-mb-px flex space-x-8">
        <button
          @click="activeTab = 'control'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'control'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Control Panel
        </button>
        <button
          @click="activeTab = 'sessions'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'sessions'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Sessions ({{ sessions.length }})
        </button>
        <button
          @click="activeTab = 'scripts'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'scripts'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Automation Scripts
        </button>
      </nav>
    </div>

    <!-- Control Panel Tab -->
    <div v-show="activeTab === 'control'" class="space-y-6">
      <!-- Current Session Info -->
      <div v-if="currentSession" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">Active Session</h3>
            <p class="text-sm text-gray-500">{{ currentSession.url }}</p>
          </div>
          <button @click="closeSession(currentSession.id)" class="px-4 py-2 text-sm font-medium text-white bg-danger-600 rounded-lg hover:bg-danger-700">
            Close Session
          </button>
        </div>
      </div>

      <!-- Launch New Session -->
      <div v-if="!currentSession" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Launch New Session</h3>
        <div class="flex gap-3">
          <input v-model="urlInput" type="url" placeholder="https://example.com" class="flex-1 px-3 py-2 border border-gray-300 rounded-lg">
          <button @click="handleLaunchSession" :disabled="isLoading" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
            Launch Browser
          </button>
        </div>
      </div>

      <!-- Navigation Controls -->
      <div v-if="currentSession" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Navigation</h3>
        <div class="flex gap-3">
          <input v-model="urlInput" type="url" placeholder="https://example.com" class="flex-1 px-3 py-2 border border-gray-300 rounded-lg">
          <button @click="handleNavigate" :disabled="isLoading" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
            Navigate
          </button>
        </div>
      </div>

      <!-- Element Interaction -->
      <div v-if="currentSession" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Element Interaction</h3>
        <div class="space-y-4">
          <div class="flex gap-3">
            <input v-model="selectorInput" type="text" placeholder="CSS selector (e.g., #button-id)" class="flex-1 px-3 py-2 border border-gray-300 rounded-lg">
            <button @click="handleClick" :disabled="isLoading" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
              Click
            </button>
          </div>
          <div class="flex gap-3">
            <input v-model="textInput" type="text" placeholder="Text to type" class="flex-1 px-3 py-2 border border-gray-300 rounded-lg">
            <button @click="handleType" :disabled="isLoading" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
              Type Text
            </button>
          </div>
        </div>
      </div>

      <!-- Screenshot & Script Execution -->
      <div v-if="currentSession" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Actions</h3>
        <div class="space-y-4">
          <button @click="handleScreenshot" :disabled="isLoading" class="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
            Take Screenshot
          </button>
          <div class="space-y-2">
            <textarea v-model="scriptInput" rows="4" placeholder="JavaScript code to execute..." class="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"></textarea>
            <button @click="handleExecuteScript" :disabled="isLoading" class="w-full px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
              Execute Script
            </button>
          </div>
        </div>
      </div>

      <!-- Screenshots Display -->
      <div v-if="screenshots.length > 0" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Recent Screenshots</h3>
        <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div v-for="(screenshot, idx) in screenshots.slice(0, 6)" :key="idx" class="border border-gray-200 rounded-lg overflow-hidden">
            <img :src="screenshot.image_data" alt="Screenshot" class="w-full h-auto">
            <div class="p-2 bg-gray-50">
              <p class="text-xs text-gray-500">{{ new Date(screenshot.timestamp).toLocaleTimeString() }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Sessions Tab -->
    <div v-show="activeTab === 'sessions'">
      <div v-if="sessions.length === 0" class="text-center py-12 text-gray-500">
        No active sessions
      </div>

      <div v-else class="bg-white rounded-lg shadow-sm border border-gray-200">
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Session ID</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">URL</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="session in sessions" :key="session.id" class="hover:bg-gray-50">
                <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-600">
                  {{ session.id.slice(0, 8) }}...
                </td>
                <td class="px-6 py-4 text-sm text-gray-900 max-w-xs truncate">
                  {{ session.url }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="[
                    'px-2 py-1 text-xs font-medium rounded-full',
                    session.status === 'active' ? 'bg-success-100 text-success-800' :
                    session.status === 'idle' ? 'bg-gray-100 text-gray-600' :
                    'bg-danger-100 text-danger-800'
                  ]">
                    {{ session.status }}
                  </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {{ new Date(session.created_at).toLocaleString() }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                  <button @click="selectSession(session)" class="text-primary-600 hover:text-primary-800">
                    Control
                  </button>
                  <button @click="deleteSession(session.id)" class="text-danger-600 hover:text-danger-800">
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Scripts Tab -->
    <div v-show="activeTab === 'scripts'">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Run Automation Script</h3>
        <div class="space-y-4">
          <textarea v-model="automationScriptInput" rows="12" placeholder="Enter automation script (JavaScript)..." class="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm"></textarea>
          <button @click="handleRunAutomation" :disabled="isLoading || !automationScriptInput.trim()" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
            Run Automation
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
