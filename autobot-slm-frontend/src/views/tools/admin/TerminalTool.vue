// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

<script setup lang="ts">
/**
 * TerminalTool - SSH Terminal Interface
 *
 * Uses @autobot/terminal SshTerminal for real xterm.js + WebSocket SSH.
 * GH#4983: Replaced fake text-input with real SSH terminal plugin.
 */

import { ref, computed } from 'vue'
import { SshTerminal } from '@autobot/terminal'
import { getHosts, getSlmApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TerminalTool')

interface Host {
  id: string
  name: string
  ip: string
  description: string
}

const hosts = ref<Host[]>(getHosts())
const selectedHostId = ref(hosts.value[0]?.id || '')
const isConnected = ref(false)
const connectionError = ref<string | null>(null)

const currentHost = computed(() => hosts.value.find(h => h.id === selectedHostId.value))

function onConnected() {
  isConnected.value = true
  connectionError.value = null
  logger.info('SSH session connected to', selectedHostId.value)
}

function onDisconnected() {
  isConnected.value = false
  logger.info('SSH session disconnected from', selectedHostId.value)
}

function onError(message: string) {
  connectionError.value = message
  isConnected.value = false
  logger.error('SSH session error:', message)
}
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 flex-1 flex flex-col overflow-hidden">
      <!-- Header -->
      <div class="bg-gray-100 border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div class="flex gap-1.5">
            <div class="w-3 h-3 bg-red-500 rounded-full"></div>
            <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
            <div class="w-3 h-3 bg-green-500 rounded-full"></div>
          </div>

          <div class="flex items-center gap-2 text-sm">
            <svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span class="font-medium">{{ $t('tools.admin.terminalTool.systemTerminal') }}</span>
          </div>

          <select
            v-model="selectedHostId"
            :disabled="isConnected"
            class="text-sm px-3 py-1 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
          >
            <option v-for="host in hosts" :key="host.id" :value="host.id">
              {{ host.name }} ({{ host.ip }})
            </option>
          </select>
        </div>

        <div class="flex items-center gap-1.5 text-xs">
          <div class="w-2 h-2 rounded-full" :class="isConnected ? 'bg-green-500' : 'bg-red-500'"></div>
          <span class="text-gray-600">{{ isConnected ? 'Connected' : 'Disconnected' }}</span>
        </div>
      </div>

      <div v-if="connectionError" class="m-3 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
        {{ connectionError }}
      </div>

      <div class="flex-1 overflow-hidden">
        <SshTerminal
          v-if="selectedHostId"
          :host-id="selectedHostId"
          :ws-base-path="`${getSlmApiBase()}/terminal/ws/ssh/`"
          class="h-full"
          @connected="onConnected"
          @disconnected="onDisconnected"
          @error="onError"
        />
        <div v-else class="h-full flex items-center justify-center text-gray-500 text-sm">
          Select a host above to start an SSH session.
        </div>
      </div>
    </div>

    <div v-if="currentHost" class="mt-4 p-4 bg-gray-100 rounded-lg">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-medium text-gray-900">{{ currentHost.name }}</h3>
          <p class="text-sm text-gray-600">{{ currentHost.description }}</p>
        </div>
        <code class="text-sm bg-gray-200 px-2 py-1 rounded-sm">{{ currentHost.ip }}</code>
      </div>
    </div>
  </div>
</template>
