// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NoVNCTool - noVNC Remote Desktop Viewer
 *
 * Remote desktop access via noVNC WebSocket connection.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'

// State
const loading = ref(false)
const error = ref<string | null>(null)
const isConnected = ref(false)
const isFullscreen = ref(false)

interface VNCHost {
  id: string
  name: string
  host: string
  port: number
  description: string
}

const hosts = ref<VNCHost[]>([
  { id: 'main', name: 'Main WSL', host: '172.16.168.20', port: 6080, description: 'Main backend server VNC' },
])

const selectedHost = ref<string>('main')
const currentHost = computed(() => hosts.value.find(h => h.id === selectedHost.value))

// VNC URL
const vncUrl = computed(() => {
  if (!currentHost.value) return ''
  return `http://${currentHost.value.host}:${currentHost.value.port}/vnc.html?autoconnect=true&resize=scale`
})

function connect(): void {
  if (!currentHost.value) {
    error.value = 'Please select a host'
    return
  }

  loading.value = true
  error.value = null

  // VNC connection is handled by iframe
  setTimeout(() => {
    isConnected.value = true
    loading.value = false
  }, 1000)
}

function disconnect(): void {
  isConnected.value = false
}

function toggleFullscreen(): void {
  const iframe = document.getElementById('vnc-frame') as HTMLIFrameElement
  if (!iframe) return

  if (!document.fullscreenElement) {
    iframe.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

function handleFullscreenChange(): void {
  isFullscreen.value = !!document.fullscreenElement
}

onMounted(() => {
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <!-- VNC Container -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 flex-1 flex flex-col overflow-hidden">
      <!-- Header -->
      <div class="bg-gray-100 border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <span class="font-medium text-gray-900">noVNC Remote Desktop</span>
          </div>

          <!-- Host Selector -->
          <select
            v-model="selectedHost"
            :disabled="isConnected"
            class="text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
          >
            <option v-for="host in hosts" :key="host.id" :value="host.id">
              {{ host.name }} ({{ host.host }}:{{ host.port }})
            </option>
          </select>

          <!-- Connection Status -->
          <div class="flex items-center gap-2">
            <div
              class="w-2 h-2 rounded-full"
              :class="isConnected ? 'bg-green-500' : 'bg-red-500'"
            ></div>
            <span class="text-xs text-gray-600">{{ isConnected ? 'Connected' : 'Disconnected' }}</span>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <!-- Connect/Disconnect -->
          <button
            @click="isConnected ? disconnect() : connect()"
            :disabled="loading"
            :class="[
              'px-4 py-1.5 text-sm font-medium rounded-lg transition-colors',
              isConnected
                ? 'bg-red-100 text-red-700 hover:bg-red-200'
                : 'bg-green-100 text-green-700 hover:bg-green-200'
            ]"
          >
            <span v-if="loading">Connecting...</span>
            <span v-else>{{ isConnected ? 'Disconnect' : 'Connect' }}</span>
          </button>

          <!-- Fullscreen -->
          <button
            @click="toggleFullscreen"
            :disabled="!isConnected"
            class="p-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
            title="Toggle Fullscreen"
          >
            <svg v-if="!isFullscreen" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
            <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Error Message -->
      <div v-if="error" class="m-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        {{ error }}
      </div>

      <!-- VNC Viewport -->
      <div class="flex-1 bg-gray-900 overflow-hidden">
        <div v-if="loading" class="h-full flex items-center justify-center">
          <div class="text-center">
            <svg class="animate-spin w-8 h-8 mx-auto text-white" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <p class="mt-4 text-gray-400">Connecting to {{ currentHost?.name }}...</p>
          </div>
        </div>

        <div v-else-if="!isConnected" class="h-full flex items-center justify-center">
          <div class="text-center p-8">
            <svg class="w-16 h-16 mx-auto text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <h3 class="mt-4 text-lg font-medium text-gray-300">noVNC Remote Desktop</h3>
            <p class="mt-2 text-gray-500">Select a host and click Connect to start a VNC session</p>
            <div v-if="currentHost" class="mt-4 p-4 bg-gray-800 rounded-lg">
              <p class="text-sm text-gray-400">{{ currentHost.description }}</p>
              <p class="text-xs text-gray-500 mt-2 font-mono">{{ currentHost.host }}:{{ currentHost.port }}</p>
            </div>
          </div>
        </div>

        <iframe
          v-else
          id="vnc-frame"
          :src="vncUrl"
          class="w-full h-full border-0"
          allow="fullscreen"
        ></iframe>
      </div>
    </div>

    <!-- Info Panel -->
    <div class="mt-4 p-4 bg-gray-100 rounded-lg">
      <h3 class="text-sm font-medium text-gray-900 mb-2">Connection Info</h3>
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span class="text-gray-500">Host:</span>
          <span class="ml-2 text-gray-900 font-mono">{{ currentHost?.host || 'Not selected' }}</span>
        </div>
        <div>
          <span class="text-gray-500">Port:</span>
          <span class="ml-2 text-gray-900 font-mono">{{ currentHost?.port || '-' }}</span>
        </div>
        <div>
          <span class="text-gray-500">Status:</span>
          <span :class="isConnected ? 'text-green-600' : 'text-red-600'" class="ml-2">
            {{ isConnected ? 'Connected' : 'Disconnected' }}
          </span>
        </div>
        <div>
          <span class="text-gray-500">Protocol:</span>
          <span class="ml-2 text-gray-900">WebSocket VNC</span>
        </div>
      </div>
    </div>
  </div>
</template>
