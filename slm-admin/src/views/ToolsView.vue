<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'

const tools = [
  {
    id: 'network-test',
    name: 'Network Connectivity Test',
    description: 'Test network connectivity between infrastructure nodes',
    icon: 'network',
  },
  {
    id: 'redis-cli',
    name: 'Redis CLI',
    description: 'Execute Redis commands on the cluster',
    icon: 'database',
  },
  {
    id: 'service-restart',
    name: 'Service Restart',
    description: 'Restart services on selected nodes',
    icon: 'refresh',
  },
  {
    id: 'log-viewer',
    name: 'Log Viewer',
    description: 'View and search service logs across nodes',
    icon: 'document',
  },
  {
    id: 'ssh-console',
    name: 'SSH Console',
    description: 'Open SSH session to a node',
    icon: 'terminal',
  },
  {
    id: 'health-check',
    name: 'Deep Health Check',
    description: 'Run comprehensive health diagnostics',
    icon: 'heart',
  },
]

const activeTool = ref<string | null>(null)

function selectTool(toolId: string): void {
  activeTool.value = toolId
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Infrastructure Tools</h1>
      <p class="text-sm text-gray-500 mt-1">
        Diagnostic and management tools for infrastructure operations
      </p>
    </div>

    <!-- Tools Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
      <button
        v-for="tool in tools"
        :key="tool.id"
        @click="selectTool(tool.id)"
        :class="[
          'card p-6 text-left hover:shadow-md transition-shadow',
          activeTool === tool.id ? 'ring-2 ring-primary-500' : ''
        ]"
      >
        <div class="flex items-start gap-4">
          <div class="p-3 bg-primary-100 rounded-lg">
            <!-- Network icon -->
            <svg v-if="tool.icon === 'network'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
            </svg>
            <!-- Database icon -->
            <svg v-else-if="tool.icon === 'database'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            <!-- Refresh icon -->
            <svg v-else-if="tool.icon === 'refresh'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <!-- Document icon -->
            <svg v-else-if="tool.icon === 'document'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <!-- Terminal icon -->
            <svg v-else-if="tool.icon === 'terminal'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <!-- Heart icon -->
            <svg v-else-if="tool.icon === 'heart'" class="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
          </div>
          <div>
            <h3 class="font-medium text-gray-900">{{ tool.name }}</h3>
            <p class="text-sm text-gray-500 mt-1">{{ tool.description }}</p>
          </div>
        </div>
      </button>
    </div>

    <!-- Tool Content Area -->
    <div v-if="activeTool" class="card p-6">
      <div class="text-center py-8 text-gray-500">
        <p>Tool interface for <strong>{{ tools.find(t => t.id === activeTool)?.name }}</strong> will be displayed here.</p>
        <p class="text-sm mt-2">Implementation in progress...</p>
      </div>
    </div>
  </div>
</template>
