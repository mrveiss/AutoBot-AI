<template>
  <div
    class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow duration-200"
    :class="{
      'border-green-300': host.status === 'active',
      'border-yellow-300': host.status === 'pending',
      'border-red-300': host.status === 'error',
      'border-blue-300': host.status === 'deploying'
    }"
  >
    <!-- Header -->
    <div class="flex items-start justify-between mb-3">
      <div class="flex-1">
        <h3 class="text-lg font-semibold text-gray-900">{{ host.hostname }}</h3>
        <p class="text-sm text-gray-500">{{ host.ip_address }}</p>
      </div>
      <div class="flex items-center space-x-2">
        <span
          :class="{
            'bg-green-100 text-green-800': host.status === 'active',
            'bg-yellow-100 text-yellow-800': host.status === 'pending',
            'bg-red-100 text-red-800': host.status === 'error',
            'bg-blue-100 text-blue-800': host.status === 'deploying'
          }"
          class="px-2 py-1 text-xs font-medium rounded-full"
        >
          {{ host.status || 'unknown' }}
        </span>
      </div>
    </div>

    <!-- Description -->
    <p v-if="host.description" class="text-sm text-gray-600 mb-3">
      {{ host.description }}
    </p>

    <!-- Tags -->
    <div v-if="host.tags && host.tags.length > 0" class="flex flex-wrap gap-1 mb-3">
      <span
        v-for="tag in host.tags"
        :key="tag"
        class="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded"
      >
        {{ tag }}
      </span>
    </div>

    <!-- Metadata -->
    <div class="grid grid-cols-2 gap-2 text-xs text-gray-500 mb-3">
      <div>
        <span class="font-medium">User:</span> {{ host.ssh_user }}
      </div>
      <div v-if="host.ansible_group">
        <span class="font-medium">Group:</span> {{ host.ansible_group }}
      </div>
      <div v-if="host.last_deployed_at">
        <span class="font-medium">Last Deploy:</span> {{ formatDate(host.last_deployed_at) }}
      </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center space-x-2 pt-3 border-t border-gray-100">
      <button
        @click="$emit('deploy', host.id)"
        :disabled="host.status === 'deploying'"
        class="flex-1 px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
      >
        <span v-if="host.status === 'deploying'" class="flex items-center justify-center">
          <svg class="animate-spin h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Deploying...
        </span>
        <span v-else>Deploy</span>
      </button>

      <button
        @click="$emit('test', host.id)"
        class="px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition-colors duration-200"
        title="Test SSH connection"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
        </svg>
      </button>

      <button
        @click="$emit('edit', host)"
        class="px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition-colors duration-200"
        title="Edit host"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
        </svg>
      </button>

      <button
        @click="$emit('delete', host.id)"
        class="px-3 py-2 text-sm font-medium text-red-600 bg-red-50 rounded-md hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors duration-200"
        title="Delete host"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { defineProps, defineEmits } from 'vue'
import type { Host } from '@/composables/useInfrastructure'
import { formatDateTime } from '@/utils/formatHelpers'

defineProps<{
  host: Host
}>()

defineEmits<{
  deploy: [hostId: string]
  test: [hostId: string]
  edit: [host: Host]
  delete: [hostId: string]
}>()

// NOTE: formatDate removed - now using formatDateTime from @/utils/formatHelpers
const formatDate = formatDateTime
</script>
