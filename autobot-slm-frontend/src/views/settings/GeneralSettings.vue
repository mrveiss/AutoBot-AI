<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * GeneralSettings - General system configuration
 *
 * Handles basic system settings like timezone, display preferences.
 */

import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

interface Setting {
  key: string
  value: string | null
  value_type: string
  description: string | null
}

const authStore = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const settings = ref({
  system_name: 'AutoBot Production',
  default_timezone: 'UTC',
  dark_mode: true,
  auto_refresh: true,
  refresh_interval: '30',
})

async function fetchSettings(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await fetch(`${authStore.getApiUrl()}/api/settings`, {
      headers: authStore.getAuthHeaders(),
    })

    if (!response.ok) {
      throw new Error('Failed to fetch settings')
    }

    const data: Setting[] = await response.json()
    data.forEach((s) => {
      if (s.value !== null && s.key in settings.value) {
        (settings.value as Record<string, any>)[s.key] = s.value
      }
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load settings'
  } finally {
    loading.value = false
  }
}

async function saveSetting(key: string, value: string | boolean): Promise<void> {
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
      body: JSON.stringify({ value: String(value) }),
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

async function saveAllSettings(): Promise<void> {
  saving.value = true
  error.value = null
  success.value = null

  try {
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
    success.value = 'All settings saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save settings'
  } finally {
    saving.value = false
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

          <!-- Default Timezone -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Default Timezone</label>
              <p class="text-xs text-gray-500 mt-1">Timezone for displaying dates and times</p>
            </div>
            <select
              v-model="settings.default_timezone"
              class="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="UTC">UTC</option>
              <option value="America/New_York">America/New_York (EST)</option>
              <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
              <option value="Europe/London">Europe/London (GMT)</option>
              <option value="Europe/Paris">Europe/Paris (CET)</option>
              <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
              <option value="Australia/Sydney">Australia/Sydney (AEST)</option>
            </select>
          </div>

          <!-- Dark Mode -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Dark Mode</label>
              <p class="text-xs text-gray-500 mt-1">Use dark theme for the interface</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                v-model="settings.dark_mode"
                class="sr-only peer"
              />
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
              <input
                type="checkbox"
                v-model="settings.auto_refresh"
                class="sr-only peer"
              />
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
    </template>
  </div>
</template>
