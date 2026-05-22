// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

<script setup lang="ts">
/**
 * NoVNCTool - noVNC Remote Desktop Viewer
 *
 * Uses @autobot/vnc plugin (VncViewer + VncToolbar).
 * GH#4985: Migrated to shared plugin components.
 */

import { ref, computed, onMounted } from 'vue'
import { VncViewer, VncToolbar } from '@autobot/vnc'
import type { VncHost } from '@autobot/vnc'
import { getVNCHosts, getSlmApiBase } from '@/config/ssot-config'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('NoVNCTool')
const api = useSlmApi()

const loading = ref(false)
const loadingEndpoints = ref(false)
const error = ref<string | null>(null)
const isConnected = ref(false)

const staticHosts = getVNCHosts().map(h => ({ ...h, proxied: h.id === 'main', source: 'static' as const }))
const dynamicHosts = ref<VncHost[]>([])

const hosts = computed<VncHost[]>(() => [...staticHosts, ...dynamicHosts.value])
const selectedHostId = ref(staticHosts[0]?.id || '')
const currentHost = computed(() => hosts.value.find(h => h.id === selectedHostId.value))

async function fetchDynamicEndpoints(): Promise<void> {
  loadingEndpoints.value = true
  try {
    const response = await api.getVncEndpoints()
    dynamicHosts.value = response.endpoints.map(ep => ({
      id: `slm-${ep.credential_id}`,
      name: ep.name || `${ep.hostname} (${ep.vnc_type})`,
      host: ep.ip_address,
      port: ep.port,
      description: `SLM-managed VNC on ${ep.hostname}`,
      proxied: false,
    }))
  } catch (e) {
    logger.warn('VNC endpoints API not available:', e)
  } finally {
    loadingEndpoints.value = false
  }
}

function connect(): void {
  if (!currentHost.value) { error.value = 'Please select a host'; return }
  loading.value = true
  error.value = null
  setTimeout(() => { isConnected.value = true; loading.value = false }, 1000)
}

function disconnect(): void { isConnected.value = false }

function onToolbarError(message: string) { error.value = message }

onMounted(() => fetchDynamicEndpoints())
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 flex-1 flex flex-col overflow-hidden">
      <!-- Header -->
      <div class="bg-gray-100 border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <span class="font-medium text-gray-900">{{ $t('tools.admin.noVNCTool.noVNCRemoteDesktop') }}</span>
          </div>

          <select
            v-model="selectedHostId"
            :disabled="isConnected || loadingEndpoints"
            class="text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
          >
            <optgroup v-if="staticHosts.length > 0" label="Static Hosts">
              <option v-for="host in staticHosts" :key="host.id" :value="host.id">
                {{ host.name }} ({{ host.host }}:{{ host.port }})
              </option>
            </optgroup>
            <optgroup v-if="dynamicHosts.length > 0" label="SLM-Managed">
              <option v-for="host in dynamicHosts" :key="host.id" :value="host.id">
                {{ host.name }} ({{ host.host }}:{{ host.port }})
              </option>
            </optgroup>
          </select>

          <button
            @click="fetchDynamicEndpoints"
            :disabled="loadingEndpoints || isConnected"
            class="p-1.5 text-gray-500 hover:bg-gray-200 rounded-sm transition-colors disabled:opacity-50"
            title="Refresh VNC endpoints"
          >
            <svg class="w-4 h-4" :class="{ 'animate-spin': loadingEndpoints }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          <div class="flex items-center gap-2">
            <div class="w-2 h-2 rounded-full" :class="isConnected ? 'bg-green-500' : 'bg-red-500'"></div>
            <span class="text-xs text-gray-600">{{ isConnected ? 'Connected' : 'Disconnected' }}</span>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            @click="isConnected ? disconnect() : connect()"
            :disabled="loading || !selectedHostId"
            :class="[
              'px-4 py-1.5 text-sm font-medium rounded-lg transition-colors',
              isConnected ? 'bg-red-100 text-red-700 hover:bg-red-200' : 'bg-green-100 text-green-700 hover:bg-green-200'
            ]"
          >
            <span v-if="loading">{{ $t('tools.admin.noVNCTool.connecting') }}</span>
            <span v-else>{{ isConnected ? 'Disconnect' : 'Connect' }}</span>
          </button>
        </div>
      </div>

      <div v-if="error" class="m-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        {{ error }}
      </div>

      <div class="flex-1 overflow-hidden">
        <VncViewer v-model="isConnected" :host="currentHost" :loading="loading" class="h-full" />
      </div>
    </div>

    <div class="mt-4 p-4 bg-gray-100 rounded-lg">
      <h3 class="text-sm font-medium text-gray-900 mb-2">{{ $t('tools.admin.noVNCTool.connectionInfo') }}</h3>
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span class="text-gray-500">{{ $t('tools.admin.noVNCTool.host') }}</span>
          <span class="ml-2 text-gray-900 font-mono">{{ currentHost?.host || 'Not selected' }}</span>
        </div>
        <div>
          <span class="text-gray-500">{{ $t('tools.admin.noVNCTool.port') }}</span>
          <span class="ml-2 text-gray-900 font-mono">{{ currentHost?.port || '-' }}</span>
        </div>
        <div>
          <span class="text-gray-500">{{ $t('tools.admin.noVNCTool.status') }}</span>
          <span :class="isConnected ? 'text-green-600' : 'text-red-600'" class="ml-2">
            {{ isConnected ? 'Connected' : 'Disconnected' }}
          </span>
        </div>
      </div>
    </div>

    <div class="mt-4">
      <VncToolbar :connected="isConnected" :api-base-url="getSlmApiBase()" @error="onToolbarError" />
    </div>
  </div>
</template>
