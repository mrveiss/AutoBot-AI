<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'

const activeTab = ref('general')

const tabs = [
  { id: 'general', name: 'General', icon: 'cog' },
  { id: 'slm', name: 'SLM Configuration', icon: 'server' },
  { id: 'notifications', name: 'Notifications', icon: 'bell' },
  { id: 'api', name: 'API Settings', icon: 'code' },
]
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Settings</h1>
      <p class="text-sm text-gray-500 mt-1">
        Configure system settings and preferences
      </p>
    </div>

    <div class="flex gap-6">
      <!-- Sidebar -->
      <div class="w-48 shrink-0">
        <nav class="space-y-1">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="[
              'w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors',
              activeTab === tab.id
                ? 'bg-primary-100 text-primary-700'
                : 'text-gray-600 hover:bg-gray-100'
            ]"
          >
            {{ tab.name }}
          </button>
        </nav>
      </div>

      <!-- Content -->
      <div class="flex-1 card p-6">
        <!-- General Settings -->
        <div v-if="activeTab === 'general'">
          <h2 class="text-lg font-semibold mb-4">General Settings</h2>

          <div class="space-y-4">
            <div>
              <label class="label">System Name</label>
              <input type="text" class="input" value="AutoBot Production" />
            </div>

            <div>
              <label class="label">Default Timezone</label>
              <select class="input">
                <option>UTC</option>
                <option>America/New_York</option>
                <option>Europe/London</option>
                <option>Asia/Tokyo</option>
              </select>
            </div>

            <div>
              <label class="flex items-center gap-2">
                <input type="checkbox" class="rounded border-gray-300" checked />
                <span class="text-sm text-gray-700">Enable dark mode</span>
              </label>
            </div>
          </div>
        </div>

        <!-- SLM Configuration -->
        <div v-else-if="activeTab === 'slm'">
          <h2 class="text-lg font-semibold mb-4">SLM Configuration</h2>

          <div class="space-y-4">
            <div>
              <label class="label">Heartbeat Interval (seconds)</label>
              <input type="number" class="input" value="30" />
            </div>

            <div>
              <label class="label">Health Check Timeout (seconds)</label>
              <input type="number" class="input" value="10" />
            </div>

            <div>
              <label class="label">Unhealthy Threshold (missed heartbeats)</label>
              <input type="number" class="input" value="3" />
            </div>

            <div>
              <label class="label">Backup Retention (days)</label>
              <input type="number" class="input" value="30" />
            </div>
          </div>
        </div>

        <!-- Notifications -->
        <div v-else-if="activeTab === 'notifications'">
          <h2 class="text-lg font-semibold mb-4">Notification Settings</h2>

          <div class="space-y-4">
            <div>
              <label class="flex items-center gap-2">
                <input type="checkbox" class="rounded border-gray-300" checked />
                <span class="text-sm text-gray-700">Node health alerts</span>
              </label>
            </div>

            <div>
              <label class="flex items-center gap-2">
                <input type="checkbox" class="rounded border-gray-300" checked />
                <span class="text-sm text-gray-700">Deployment notifications</span>
              </label>
            </div>

            <div>
              <label class="flex items-center gap-2">
                <input type="checkbox" class="rounded border-gray-300" checked />
                <span class="text-sm text-gray-700">Backup completion alerts</span>
              </label>
            </div>

            <div>
              <label class="flex items-center gap-2">
                <input type="checkbox" class="rounded border-gray-300" />
                <span class="text-sm text-gray-700">Maintenance window reminders</span>
              </label>
            </div>
          </div>
        </div>

        <!-- API Settings -->
        <div v-else-if="activeTab === 'api'">
          <h2 class="text-lg font-semibold mb-4">API Settings</h2>

          <div class="space-y-4">
            <div>
              <label class="label">Backend API URL</label>
              <input type="text" class="input" value="http://172.16.168.20:8001" readonly />
            </div>

            <div>
              <label class="label">WebSocket URL</label>
              <input type="text" class="input" value="ws://172.16.168.20:8001/v1/slm/ws" readonly />
            </div>

            <div>
              <label class="label">Request Timeout (ms)</label>
              <input type="number" class="input" value="30000" />
            </div>
          </div>
        </div>

        <!-- Save Button -->
        <div class="mt-6 pt-4 border-t border-gray-200 flex justify-end">
          <button class="btn btn-primary">
            Save Changes
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
