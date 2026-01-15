<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'

const activeTab = ref('overview')

const tabs = [
  { id: 'overview', name: 'Security Overview' },
  { id: 'audit', name: 'Audit Logs' },
  { id: 'threats', name: 'Threat Detection' },
  { id: 'policies', name: 'Security Policies' },
]
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Security Analytics</h1>
      <p class="text-sm text-gray-500 mt-1">
        Monitor security events and manage security policies
      </p>
    </div>

    <!-- Tab Navigation -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex gap-4">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="[
            'px-1 py-3 text-sm font-medium border-b-2 transition-colors',
            activeTab === tab.id
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          {{ tab.name }}
        </button>
      </nav>
    </div>

    <!-- Security Overview -->
    <div v-if="activeTab === 'overview'">
      <!-- Security Score -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Security Score</div>
          <div class="text-3xl font-bold text-success-600">94%</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Active Threats</div>
          <div class="text-3xl font-bold text-gray-900">0</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Failed Logins (24h)</div>
          <div class="text-3xl font-bold text-warning-600">3</div>
        </div>
        <div class="card p-4">
          <div class="text-sm text-gray-500 mb-1">Policy Violations</div>
          <div class="text-3xl font-bold text-gray-900">0</div>
        </div>
      </div>

      <!-- Recent Events -->
      <div class="card">
        <div class="px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-semibold">Recent Security Events</h2>
        </div>
        <div class="divide-y divide-gray-200">
          <div class="px-6 py-4 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-2 h-2 rounded-full bg-green-500"></div>
              <div>
                <div class="text-sm font-medium text-gray-900">Successful authentication</div>
                <div class="text-xs text-gray-500">User: admin | IP: 172.16.168.1</div>
              </div>
            </div>
            <div class="text-xs text-gray-500">2 minutes ago</div>
          </div>
          <div class="px-6 py-4 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-2 h-2 rounded-full bg-yellow-500"></div>
              <div>
                <div class="text-sm font-medium text-gray-900">Failed login attempt</div>
                <div class="text-xs text-gray-500">User: unknown | IP: 192.168.1.100</div>
              </div>
            </div>
            <div class="text-xs text-gray-500">1 hour ago</div>
          </div>
          <div class="px-6 py-4 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-2 h-2 rounded-full bg-blue-500"></div>
              <div>
                <div class="text-sm font-medium text-gray-900">Configuration change</div>
                <div class="text-xs text-gray-500">Setting: firewall_rules | User: admin</div>
              </div>
            </div>
            <div class="text-xs text-gray-500">3 hours ago</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Audit Logs -->
    <div v-else-if="activeTab === 'audit'">
      <div class="card p-6">
        <p class="text-gray-500 text-center">Audit logs will be displayed here.</p>
      </div>
    </div>

    <!-- Threat Detection -->
    <div v-else-if="activeTab === 'threats'">
      <div class="card p-6">
        <p class="text-gray-500 text-center">Threat detection dashboard will be displayed here.</p>
      </div>
    </div>

    <!-- Security Policies -->
    <div v-else-if="activeTab === 'policies'">
      <div class="card p-6">
        <p class="text-gray-500 text-center">Security policies configuration will be displayed here.</p>
      </div>
    </div>
  </div>
</template>
