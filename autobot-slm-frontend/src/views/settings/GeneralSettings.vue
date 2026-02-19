<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * GeneralSettings - General system configuration
 *
 * Handles system settings: timezone (full IANA list), NTP servers, display preferences.
 * NTP sync triggers Ansible time_sync role across all fleet nodes.
 */

import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

interface Setting {
  key: string
  value: string | null
  value_type: string
  description: string | null
}

interface TimeConfig {
  timezone: string
  ntp_servers: string[]
}

const authStore = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const syncing = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const syncResult = ref<{ success: boolean; message: string; node_count: number; output?: string } | null>(null)

const settings = ref({
  system_name: 'AutoBot Production',
  default_timezone: 'UTC',
  dark_mode: true,
  auto_refresh: true,
  refresh_interval: '30',
})

const timeConfig = ref<TimeConfig>({
  timezone: 'UTC',
  ntp_servers: ['0.pool.ntp.org', '1.pool.ntp.org', '2.pool.ntp.org', '3.pool.ntp.org'],
})

const ntpServersText = computed({
  get: () => timeConfig.value.ntp_servers.join('\n'),
  set: (val: string) => {
    timeConfig.value.ntp_servers = val
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
  },
})

// Full IANA timezone list from browser Intl API, with UTC first
const allTimezones = computed<string[]>(() => {
  try {
    const zones: string[] = (Intl as unknown as { supportedValuesOf: (key: string) => string[] }).supportedValuesOf('timeZone')
    return ['UTC', ...zones.filter((z) => z !== 'UTC')]
  } catch {
    // Fallback for older browsers
    return [
      'UTC',
      'America/New_York',
      'America/Chicago',
      'America/Denver',
      'America/Los_Angeles',
      'America/Anchorage',
      'America/Honolulu',
      'America/Sao_Paulo',
      'America/Toronto',
      'America/Vancouver',
      'America/Mexico_City',
      'America/Buenos_Aires',
      'America/Bogota',
      'America/Lima',
      'America/Santiago',
      'Europe/London',
      'Europe/Paris',
      'Europe/Berlin',
      'Europe/Madrid',
      'Europe/Rome',
      'Europe/Amsterdam',
      'Europe/Brussels',
      'Europe/Vienna',
      'Europe/Zurich',
      'Europe/Stockholm',
      'Europe/Oslo',
      'Europe/Copenhagen',
      'Europe/Helsinki',
      'Europe/Warsaw',
      'Europe/Prague',
      'Europe/Budapest',
      'Europe/Bucharest',
      'Europe/Sofia',
      'Europe/Athens',
      'Europe/Istanbul',
      'Europe/Kiev',
      'Europe/Moscow',
      'Europe/Riga',
      'Europe/Tallinn',
      'Europe/Vilnius',
      'Africa/Cairo',
      'Africa/Lagos',
      'Africa/Nairobi',
      'Africa/Johannesburg',
      'Africa/Casablanca',
      'Asia/Dubai',
      'Asia/Karachi',
      'Asia/Kolkata',
      'Asia/Dhaka',
      'Asia/Bangkok',
      'Asia/Jakarta',
      'Asia/Singapore',
      'Asia/Shanghai',
      'Asia/Hong_Kong',
      'Asia/Taipei',
      'Asia/Seoul',
      'Asia/Tokyo',
      'Asia/Almaty',
      'Asia/Tashkent',
      'Asia/Tehran',
      'Asia/Baghdad',
      'Asia/Beirut',
      'Asia/Riyadh',
      'Asia/Kabul',
      'Asia/Kathmandu',
      'Asia/Colombo',
      'Asia/Rangoon',
      'Asia/Kuala_Lumpur',
      'Asia/Manila',
      'Asia/Vladivostok',
      'Asia/Magadan',
      'Asia/Kamchatka',
      'Pacific/Auckland',
      'Pacific/Fiji',
      'Pacific/Guam',
      'Pacific/Honolulu',
      'Pacific/Midway',
      'Pacific/Tongatapu',
      'Australia/Sydney',
      'Australia/Melbourne',
      'Australia/Brisbane',
      'Australia/Adelaide',
      'Australia/Darwin',
      'Australia/Perth',
    ]
  }
})

async function fetchSettings(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const [settingsRes, timeRes] = await Promise.all([
      fetch(`${authStore.getApiUrl()}/api/settings`, {
        headers: authStore.getAuthHeaders(),
      }),
      fetch(`${authStore.getApiUrl()}/api/settings/time/config`, {
        headers: authStore.getAuthHeaders(),
      }),
    ])

    if (settingsRes.ok) {
      const data: Setting[] = await settingsRes.json()
      data.forEach((s) => {
        if (s.value !== null && s.key in settings.value) {
          (settings.value as Record<string, any>)[s.key] = s.value
        }
      })
    }

    if (timeRes.ok) {
      const tc: TimeConfig = await timeRes.json()
      timeConfig.value = tc
      settings.value.default_timezone = tc.timezone
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load settings'
  } finally {
    loading.value = false
  }
}

async function saveAllSettings(): Promise<void> {
  saving.value = true
  error.value = null
  success.value = null

  try {
    // Save general settings
    for (const [key, value] of Object.entries(settings.value)) {
      await fetch(`${authStore.getApiUrl()}/api/settings/${key}`, {
        method: 'PUT',
        headers: {
          ...authStore.getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: String(value) }),
      })
    }

    // Save time config (timezone + NTP)
    timeConfig.value.timezone = settings.value.default_timezone
    const timeRes = await fetch(`${authStore.getApiUrl()}/api/settings/time/config`, {
      method: 'PUT',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(timeConfig.value),
    })

    if (!timeRes.ok) {
      throw new Error('Failed to save time configuration')
    }

    success.value = 'Settings saved successfully'
    setTimeout(() => {
      success.value = null
    }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save settings'
  } finally {
    saving.value = false
  }
}

async function syncTimeToNodes(): Promise<void> {
  syncing.value = true
  syncResult.value = null
  error.value = null

  try {
    const res = await fetch(`${authStore.getApiUrl()}/api/settings/time/sync`, {
      method: 'POST',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ node_ids: null }),
    })

    if (!res.ok) {
      const detail = await res.text()
      throw new Error(detail || 'Time sync request failed')
    }

    syncResult.value = await res.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Time sync failed'
  } finally {
    syncing.value = false
  }
}

onMounted(fetchSettings)
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-8">
      <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <template v-else>
      <!-- Messages -->
      <div v-if="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        {{ error }}
      </div>
      <div v-if="success" class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
        {{ success }}
      </div>

      <!-- General Settings Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 class="text-lg font-semibold mb-6">General Settings</h2>

        <div class="space-y-6">
          <!-- System Name -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">System Name</label>
              <p class="text-xs text-gray-500 mt-1">Display name for this installation</p>
            </div>
            <input
              type="text"
              v-model="settings.system_name"
              class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <!-- Default Timezone — full IANA list -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Default Timezone</label>
              <p class="text-xs text-gray-500 mt-1">
                Timezone for displaying dates and times ({{ allTimezones.length }} zones available)
              </p>
            </div>
            <select
              v-model="settings.default_timezone"
              class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option v-for="tz in allTimezones" :key="tz" :value="tz">{{ tz }}</option>
            </select>
          </div>

          <!-- Dark Mode -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Dark Mode</label>
              <p class="text-xs text-gray-500 mt-1">Use dark theme for the interface</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="settings.dark_mode" class="sr-only peer" />
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>

          <!-- Auto Refresh -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Auto Refresh</label>
              <p class="text-xs text-gray-500 mt-1">Automatically refresh data on dashboards</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="settings.auto_refresh" class="sr-only peer" />
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>

          <!-- Refresh Interval -->
          <div class="flex items-center justify-between">
            <div>
              <label class="block text-sm font-medium text-gray-900">Refresh Interval</label>
              <p class="text-xs text-gray-500 mt-1">How often to refresh data (in seconds)</p>
            </div>
            <select
              v-model="settings.refresh_interval"
              :disabled="!settings.auto_refresh"
              class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:bg-gray-100 disabled:text-gray-500"
            >
              <option value="10">10 seconds</option>
              <option value="30">30 seconds</option>
              <option value="60">1 minute</option>
              <option value="120">2 minutes</option>
              <option value="300">5 minutes</option>
            </select>
          </div>
        </div>

        <!-- Save Button -->
        <div class="mt-8 pt-6 border-t border-gray-200 flex justify-end">
          <button
            @click="saveAllSettings"
            class="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center gap-2 disabled:opacity-50"
            :disabled="saving"
          >
            <svg v-if="saving" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ saving ? 'Saving...' : 'Save Changes' }}
          </button>
        </div>
      </div>

      <!-- NTP / Time Sync Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between mb-6">
          <div>
            <h2 class="text-lg font-semibold">Fleet Time Synchronization</h2>
            <p class="text-sm text-gray-500 mt-1">
              Configure NTP servers and push time settings to all fleet nodes via Ansible.
            </p>
          </div>
          <button
            @click="syncTimeToNodes"
            :disabled="syncing"
            class="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            <svg v-if="syncing" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ syncing ? 'Syncing…' : 'Sync All Nodes' }}
          </button>
        </div>

        <!-- NTP Servers textarea -->
        <div class="mb-6">
          <label class="block text-sm font-medium text-gray-900 mb-1">
            NTP Servers
            <span class="text-gray-400 font-normal">(one per line)</span>
          </label>
          <textarea
            v-model="ntpServersText"
            rows="4"
            placeholder="0.pool.ntp.org&#10;1.pool.ntp.org&#10;time.google.com"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
          />
          <p class="text-xs text-gray-500 mt-1">
            Servers are tried in order. Changes are applied on next "Save Changes" or "Sync All Nodes".
          </p>
        </div>

        <!-- Sync result -->
        <div
          v-if="syncResult"
          :class="syncResult.success
            ? 'bg-green-50 border-green-200 text-green-800'
            : 'bg-red-50 border-red-200 text-red-800'"
          class="border rounded-lg p-4 text-sm"
        >
          <div class="font-medium mb-1">
            {{ syncResult.success ? '✅ Sync complete' : '❌ Sync failed' }}
            — {{ syncResult.node_count }} node{{ syncResult.node_count !== 1 ? 's' : '' }}
          </div>
          <div class="text-xs opacity-80">{{ syncResult.message }}</div>
          <details v-if="syncResult.output" class="mt-2">
            <summary class="cursor-pointer text-xs font-medium">Ansible output</summary>
            <pre class="mt-2 text-xs whitespace-pre-wrap font-mono opacity-80">{{ syncResult.output }}</pre>
          </details>
        </div>
      </div>
    </template>
  </div>
</template>
