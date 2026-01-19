<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * APISettings - API configuration display
 *
 * Shows API endpoint information and connection details.
 */

import { ref, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import config, { getBackendUrl, getGrafanaUrl, getPrometheusUrl } from '@/config/ssot-config'

const authStore = useAuthStore()
const testingConnection = ref(false)
const connectionStatus = ref<'unknown' | 'connected' | 'failed'>('unknown')
const connectionMessage = ref('')

const apiUrl = computed(() => authStore.getApiUrl())
const wsUrl = computed(() => apiUrl.value.replace('http', 'ws') + '/ws')

async function testConnection(): Promise<void> {
  testingConnection.value = true
  connectionStatus.value = 'unknown'
  connectionMessage.value = ''

  try {
    const startTime = Date.now()
    const response = await fetch(`${apiUrl.value}/api/health`, {
      headers: authStore.getAuthHeaders(),
    })

    const responseTime = Date.now() - startTime

    if (response.ok) {
      connectionStatus.value = 'connected'
      connectionMessage.value = `Connected (${responseTime}ms)`
    } else {
      connectionStatus.value = 'failed'
      connectionMessage.value = `HTTP ${response.status}`
    }
  } catch (e) {
    connectionStatus.value = 'failed'
    connectionMessage.value = e instanceof Error ? e.message : 'Connection failed'
  } finally {
    testingConnection.value = false
  }
}

function copyToClipboard(text: string): void {
  navigator.clipboard.writeText(text)
}
</script>

<template>
  <div class="p-6">
    <!-- Connection Test Card -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Connection Status</h2>
        <button
          @click="testConnection"
          :disabled="testingConnection"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', { 'animate-spin': testingConnection }]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Test Connection
        </button>
      </div>

      <div
        v-if="connectionStatus !== 'unknown'"
        :class="[
          'p-4 rounded-lg flex items-center gap-3',
          connectionStatus === 'connected' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
        ]"
      >
        <div
          :class="[
            'w-3 h-3 rounded-full',
            connectionStatus === 'connected' ? 'bg-green-500' : 'bg-red-500'
          ]"
        ></div>
        <span :class="connectionStatus === 'connected' ? 'text-green-700' : 'text-red-700'">
          {{ connectionMessage }}
        </span>
      </div>
    </div>

    <!-- API Endpoints -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
      <h2 class="text-lg font-semibold mb-6">API Endpoints</h2>

      <div class="space-y-4">
        <!-- Backend API -->
        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div>
            <p class="font-medium text-gray-900">Backend API</p>
            <p class="text-sm text-gray-500 font-mono">{{ apiUrl }}</p>
          </div>
          <button
            @click="copyToClipboard(apiUrl)"
            class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
            title="Copy to clipboard"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>

        <!-- WebSocket -->
        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div>
            <p class="font-medium text-gray-900">WebSocket</p>
            <p class="text-sm text-gray-500 font-mono">{{ wsUrl }}</p>
          </div>
          <button
            @click="copyToClipboard(wsUrl)"
            class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
            title="Copy to clipboard"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>

        <!-- Grafana -->
        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div>
            <p class="font-medium text-gray-900">Grafana (Proxied)</p>
            <p class="text-sm text-gray-500 font-mono">{{ getGrafanaUrl() }}</p>
          </div>
          <button
            @click="copyToClipboard(getGrafanaUrl())"
            class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
            title="Copy to clipboard"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>

        <!-- Prometheus -->
        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div>
            <p class="font-medium text-gray-900">Prometheus (Proxied)</p>
            <p class="text-sm text-gray-500 font-mono">{{ getPrometheusUrl() }}</p>
          </div>
          <button
            @click="copyToClipboard(getPrometheusUrl())"
            class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
            title="Copy to clipboard"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>

        <!-- AutoBot Backend -->
        <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div>
            <p class="font-medium text-gray-900">AutoBot Backend (Proxied)</p>
            <p class="text-sm text-gray-500 font-mono">{{ getBackendUrl() }}</p>
          </div>
          <button
            @click="copyToClipboard(getBackendUrl())"
            class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
            title="Copy to clipboard"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Configuration Reference -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold mb-4">Configuration Reference</h2>
      <p class="text-sm text-gray-500 mb-4">
        These settings are defined in the SSOT configuration file.
      </p>

      <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
        <pre class="text-sm text-gray-300 font-mono">
// src/config/ssot-config.ts
const config = {
  httpProtocol: '{{ config.httpProtocol }}',
  wsProtocol: '{{ config.wsProtocol }}',
  vm: {
    main: '{{ config.vm.main }}',
    frontend: '{{ config.vm.frontend }}',
    slm: '{{ config.vm.slm }}',
    // ...
  },
  port: {
    backend: {{ config.port.backend }},
    frontend: {{ config.port.frontend }},
    slmApi: {{ config.port.slmApi }},
    // ...
  }
}</pre>
      </div>
    </div>
  </div>
</template>
