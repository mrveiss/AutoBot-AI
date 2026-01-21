// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * TerminalTool - Web Terminal Interface
 *
 * Multi-tab terminal with host switching capabilities.
 * Migrated from main AutoBot frontend - Issue #729.
 * Note: Full xterm.js integration requires terminal components migration.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const commandInput = ref('')
const commandHistory = ref<string[]>([])
const output = ref<{ type: 'command' | 'output' | 'error'; text: string }[]>([])
const isConnected = ref(false)
const selectedHost = ref('main')

interface Host {
  id: string
  name: string
  ip: string
  description: string
}

const hosts = ref<Host[]>([
  { id: 'main', name: 'Main Server', ip: '172.16.168.20', description: 'WSL Backend Server' },
  { id: 'frontend', name: 'Frontend VM', ip: '172.16.168.21', description: 'Vue.js Frontend' },
  { id: 'npu', name: 'NPU Worker', ip: '172.16.168.22', description: 'Neural Processing Unit' },
  { id: 'redis', name: 'Redis Server', ip: '172.16.168.23', description: 'Data Layer' },
  { id: 'ai', name: 'AI Stack', ip: '172.16.168.24', description: 'AI Processing' },
])

const currentHost = computed(() => hosts.value.find(h => h.id === selectedHost.value))

// Terminal tabs
interface Tab {
  id: string
  name: string
  hostId: string
  active: boolean
}

const tabs = ref<Tab[]>([
  { id: 'tab-1', name: 'Terminal 1', hostId: 'main', active: true }
])

const activeTab = computed(() => tabs.value.find(t => t.active))

function addTab(): void {
  const newId = `tab-${Date.now()}`
  tabs.value.forEach(t => t.active = false)
  tabs.value.push({
    id: newId,
    name: `Terminal ${tabs.value.length + 1}`,
    hostId: selectedHost.value,
    active: true
  })
}

function closeTab(tabId: string): void {
  if (tabs.value.length <= 1) return
  const index = tabs.value.findIndex(t => t.id === tabId)
  if (index > -1) {
    const wasActive = tabs.value[index].active
    tabs.value.splice(index, 1)
    if (wasActive && tabs.value.length > 0) {
      tabs.value[Math.max(0, index - 1)].active = true
    }
  }
}

function switchTab(tabId: string): void {
  tabs.value.forEach(t => t.active = t.id === tabId)
}

async function connect(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    output.value.push({
      type: 'output',
      text: `Connecting to ${currentHost.value?.name} (${currentHost.value?.ip})...`
    })

    // Simulate connection - full WebSocket integration would require terminal service
    await new Promise(resolve => setTimeout(resolve, 500))
    isConnected.value = true

    output.value.push({
      type: 'output',
      text: `Connected to ${currentHost.value?.name}`
    })
    output.value.push({
      type: 'output',
      text: `Session started. Type 'help' for available commands.`
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Connection failed'
    output.value.push({
      type: 'error',
      text: `Connection failed: ${error.value}`
    })
  } finally {
    loading.value = false
  }
}

function disconnect(): void {
  isConnected.value = false
  output.value.push({
    type: 'output',
    text: 'Disconnected from terminal session.'
  })
}

async function executeCommand(): Promise<void> {
  if (!commandInput.value.trim()) return

  const cmd = commandInput.value.trim()
  commandHistory.value.push(cmd)
  output.value.push({ type: 'command', text: `$ ${cmd}` })
  commandInput.value = ''

  if (!isConnected.value) {
    output.value.push({ type: 'error', text: 'Not connected. Click Connect to start a session.' })
    return
  }

  loading.value = true
  try {
    // Execute via backend terminal API
    const result = await api.post('/terminal/execute', {
      command: cmd,
      host: currentHost.value?.ip
    })

    if (result.stdout) {
      output.value.push({ type: 'output', text: result.stdout })
    }
    if (result.stderr) {
      output.value.push({ type: 'error', text: result.stderr })
    }
  } catch (e) {
    output.value.push({
      type: 'error',
      text: `Error: ${e instanceof Error ? e.message : 'Command execution failed'}`
    })
  } finally {
    loading.value = false
  }
}

function clearTerminal(): void {
  output.value = []
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    executeCommand()
  }
}

onMounted(() => {
  output.value.push({
    type: 'output',
    text: 'AutoBot Terminal - Web Interface'
  })
  output.value.push({
    type: 'output',
    text: 'Select a host and click Connect to start a session.'
  })
})
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <!-- Terminal Container -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 flex-1 flex flex-col overflow-hidden">
      <!-- Header -->
      <div class="bg-gray-100 border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <!-- Traffic lights -->
          <div class="flex gap-1.5">
            <div class="w-3 h-3 bg-red-500 rounded-full"></div>
            <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
            <div class="w-3 h-3 bg-green-500 rounded-full"></div>
          </div>

          <div class="flex items-center gap-2 text-sm">
            <svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span class="font-medium">System Terminal</span>
          </div>

          <!-- Host Selector -->
          <select
            v-model="selectedHost"
            :disabled="isConnected"
            class="text-sm px-3 py-1 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
          >
            <option v-for="host in hosts" :key="host.id" :value="host.id">
              {{ host.name }} ({{ host.ip }})
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2">
          <!-- Add Tab -->
          <button
            @click="addTab"
            class="p-1.5 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded transition-colors"
            title="New Tab"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
          </button>

          <!-- Connect/Disconnect -->
          <button
            @click="isConnected ? disconnect() : connect()"
            :class="[
              'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
              isConnected
                ? 'bg-red-100 text-red-700 hover:bg-red-200'
                : 'bg-green-100 text-green-700 hover:bg-green-200'
            ]"
          >
            {{ isConnected ? 'Disconnect' : 'Connect' }}
          </button>

          <!-- Clear -->
          <button
            @click="clearTerminal"
            class="p-1.5 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded transition-colors"
            title="Clear Terminal"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>

          <!-- Connection Status -->
          <div class="flex items-center gap-1.5 text-xs">
            <div
              class="w-2 h-2 rounded-full"
              :class="isConnected ? 'bg-green-500' : 'bg-red-500'"
            ></div>
            <span class="text-gray-600">{{ isConnected ? 'Connected' : 'Disconnected' }}</span>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div v-if="tabs.length > 1" class="bg-gray-200 border-b border-gray-300 px-2 flex gap-1 overflow-x-auto">
        <div
          v-for="tab in tabs"
          :key="tab.id"
          @click="switchTab(tab.id)"
          :class="[
            'flex items-center gap-1 px-3 py-1.5 text-xs cursor-pointer rounded-t transition-colors',
            tab.active
              ? 'bg-white text-gray-900 border-t border-x border-gray-300'
              : 'bg-gray-300 text-gray-700 hover:bg-gray-400'
          ]"
        >
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          {{ tab.name }}
          <button
            v-if="tabs.length > 1"
            @click.stop="closeTab(tab.id)"
            class="ml-1 text-gray-500 hover:text-red-600"
          >
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Terminal Body -->
      <div class="flex-1 bg-gray-900 p-4 overflow-auto font-mono text-sm">
        <div
          v-for="(line, index) in output"
          :key="index"
          :class="[
            line.type === 'command' ? 'text-green-400' : '',
            line.type === 'output' ? 'text-gray-300' : '',
            line.type === 'error' ? 'text-red-400' : ''
          ]"
          class="whitespace-pre-wrap mb-1"
        >
          {{ line.text }}
        </div>

        <!-- Input Line -->
        <div class="flex items-center gap-2 mt-2">
          <span class="text-green-400">$</span>
          <input
            v-model="commandInput"
            @keydown="handleKeydown"
            type="text"
            class="flex-1 bg-transparent text-gray-100 outline-none"
            placeholder="Enter command..."
            :disabled="loading"
          />
          <svg v-if="loading" class="animate-spin w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
      </div>
    </div>

    <!-- Host Info -->
    <div v-if="currentHost" class="mt-4 p-4 bg-gray-100 rounded-lg">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-medium text-gray-900">{{ currentHost.name }}</h3>
          <p class="text-sm text-gray-600">{{ currentHost.description }}</p>
        </div>
        <code class="text-sm bg-gray-200 px-2 py-1 rounded">{{ currentHost.ip }}</code>
      </div>
    </div>
  </div>
</template>
