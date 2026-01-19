<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * MonitoringSettings - Monitoring configuration
 *
 * Configure Prometheus, Grafana, and monitoring stack settings.
 */

import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getGrafanaUrl, getPrometheusUrl } from '@/config/ssot-config'

const authStore = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const settings = ref({
  monitoring_location: 'local',
  prometheus_url: 'http://localhost:9090',
  grafana_url: 'http://localhost:3000',
  scrape_interval: '15',
  retention_days: '30',
  alerting_enabled: true,
})

async function fetchSettings(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await fetch(`${authStore.getApiUrl()}/api/settings`, {
      headers: authStore.getAuthHeaders(),
    })

    if (response.ok) {
      const data = await response.json()
      data.forEach((s: { key: string; value: string | null }) => {
        if (s.value !== null && s.key in settings.value) {
          (settings.value as Record<string, any>)[s.key] = s.value
        }
      })
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load settings'
  } finally {
    loading.value = false
  }
}

async function saveSetting(key: string, value: string): Promise<void> {
  saving.value = true
  error.value = null
  success.value = null

  try {
    const response = await fetch(`${authStore.getApiUrl()}/api/settings/${key}`, {
      method: 'PUT',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ value }),
    })

    if (!response.ok) {
      throw new Error('Failed to save setting')
    }

    success.value = 'Setting saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save setting'
  } finally {
    saving.value = false
  }
}

async function deployMonitoringRole(): Promise<void> {
  alert('Monitoring role deployment will be triggered via Ansible')
}

async function testPrometheusConnection(): Promise<void> {
  try {
    const response = await fetch(`${getPrometheusUrl()}/-/healthy`)
    if (response.ok) {
      success.value = 'Prometheus connection successful'
      setTimeout(() => { success.value = null }, 3000)
    } else {
      error.value = 'Prometheus connection failed'
    }
  } catch (e) {
    error.value = 'Cannot reach Prometheus server'
  }
}

async function testGrafanaConnection(): Promise<void> {
  try {
    const response = await fetch(`${getGrafanaUrl()}/api/health`)
    if (response.ok) {
      success.value = 'Grafana connection successful'
      setTimeout(() => { success.value = null }, 3000)
    } else {
      error.value = 'Grafana connection failed'
    }
  } catch (e) {
    error.value = 'Cannot reach Grafana server'
  }
}

onMounted(fetchSettings)
</script>

<template>
  <div class="p-6">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-8">
      <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <template v-else>
      <!-- Messages -->
      <div v-if="error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
        {{ error }}
      </div>
      <div v-if="success" class="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">
        {{ success }}
      </div>

      <!-- Settings Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <h2 class="text-lg font-semibold mb-6">Monitoring Configuration</h2>
        <p class="text-sm text-gray-500 mb-6">
          Configure where Prometheus and Grafana monitoring services are hosted.
        </p>

        <div class="space-y-6">
          <!-- Monitoring Location -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Monitoring Location</label>
              <p class="text-xs text-gray-500 mt-1">Choose where monitoring services are running</p>
            </div>
            <select
              v-model="settings.monitoring_location"
              @change="saveSetting('monitoring_location', settings.monitoring_location)"
              class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="local">Local (on SLM host)</option>
              <option value="external">External (separate host)</option>
            </select>
          </div>

          <!-- Prometheus URL -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Prometheus URL</label>
              <p class="text-xs text-gray-500 mt-1">URL to access Prometheus</p>
            </div>
            <div class="flex gap-2">
              <input
                v-model="settings.prometheus_url"
                type="text"
                class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              />
              <button
                @click="testPrometheusConnection"
                class="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                title="Test Connection"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </button>
              <button
                @click="saveSetting('prometheus_url', settings.prometheus_url)"
                :disabled="saving"
                class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>

          <!-- Grafana URL -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Grafana URL</label>
              <p class="text-xs text-gray-500 mt-1">URL to access Grafana</p>
            </div>
            <div class="flex gap-2">
              <input
                v-model="settings.grafana_url"
                type="text"
                class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              />
              <button
                @click="testGrafanaConnection"
                class="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                title="Test Connection"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </button>
              <button
                @click="saveSetting('grafana_url', settings.grafana_url)"
                :disabled="saving"
                class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>

          <!-- Scrape Interval -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Scrape Interval</label>
              <p class="text-xs text-gray-500 mt-1">How often Prometheus collects metrics</p>
            </div>
            <select
              v-model="settings.scrape_interval"
              class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="10">10 seconds</option>
              <option value="15">15 seconds</option>
              <option value="30">30 seconds</option>
              <option value="60">1 minute</option>
            </select>
          </div>

          <!-- Retention -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Data Retention</label>
              <p class="text-xs text-gray-500 mt-1">How long to keep metrics data</p>
            </div>
            <select
              v-model="settings.retention_days"
              class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="7">7 days</option>
              <option value="15">15 days</option>
              <option value="30">30 days</option>
              <option value="60">60 days</option>
              <option value="90">90 days</option>
            </select>
          </div>

          <!-- Alerting -->
          <div class="flex items-center justify-between">
            <div>
              <label class="block text-sm font-medium text-gray-900">Alerting</label>
              <p class="text-xs text-gray-500 mt-1">Enable alert notifications</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                v-model="settings.alerting_enabled"
                class="sr-only peer"
              />
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>
        </div>
      </div>

      <!-- Deploy Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="font-semibold text-gray-900 mb-2">Deploy Monitoring Stack</h3>
        <p class="text-sm text-gray-500 mb-4">
          Use Ansible to deploy or migrate the monitoring stack to a different node.
        </p>
        <button
          @click="deployMonitoringRole"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Deploy Monitoring Role
        </button>
      </div>
    </template>
  </div>
</template>
