<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed } from 'vue'
import type { SLMNode } from '@/types/slm'

const props = defineProps<{
  node: SLMNode
}>()

const emit = defineEmits<{
  (e: 'action', action: string, nodeId: string): void
}>()

const showMenu = ref(false)

const statusClass = computed(() => {
  switch (props.node.status) {
    case 'online': return 'bg-green-500'
    case 'healthy': return 'bg-green-500'
    case 'degraded': return 'bg-yellow-500'
    case 'unhealthy': return 'bg-red-500'
    case 'offline': return 'bg-gray-400'
    case 'error': return 'bg-red-500'
    case 'enrolling': return 'bg-blue-500 animate-pulse'
    case 'pending': return 'bg-gray-400'
    case 'registered': return 'bg-gray-400'
    default: return 'bg-gray-400'
  }
})

const statusText = computed(() => {
  return props.node.status.charAt(0).toUpperCase() + props.node.status.slice(1)
})

const lastSeen = computed(() => {
  if (!props.node.health?.last_heartbeat) return 'Never'
  const date = new Date(props.node.health.last_heartbeat)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  return `${diffHr}h ago`
})

const canEnroll = computed(() => {
  return props.node.status === 'registered' || props.node.status === 'pending'
})

const isEnrolling = computed(() => {
  return props.node.status === 'enrolling'
})

const authMethodBadge = computed(() => {
  const method = props.node.auth_method || 'password'
  switch (method) {
    case 'key':
      return { label: 'SSH Key', class: 'bg-green-100 text-green-700' }
    case 'pki':
      return { label: 'PKI', class: 'bg-blue-100 text-blue-700' }
    default:
      return { label: 'Password', class: 'bg-yellow-100 text-yellow-700' }
  }
})

function handleAction(action: string): void {
  showMenu.value = false
  emit('action', action, props.node.node_id)
}

function toggleMenu(): void {
  showMenu.value = !showMenu.value
}

function closeMenu(): void {
  showMenu.value = false
}
</script>

<template>
  <div class="card p-4 hover:shadow-md transition-shadow relative" @mouseleave="closeMenu">
    <!-- Header -->
    <div class="flex items-start justify-between mb-3">
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <div :class="['w-3 h-3 rounded-full flex-shrink-0', statusClass]"></div>
        <span class="font-medium text-gray-900 truncate">{{ node.hostname }}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-gray-500 whitespace-nowrap">{{ statusText }}</span>
        <!-- Actions Menu Button -->
        <div class="relative">
          <button
            @click.stop="toggleMenu"
            class="p-1 text-gray-400 hover:text-gray-600 transition-colors rounded hover:bg-gray-100"
            title="Actions"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>
          <!-- Dropdown Menu -->
          <div
            v-if="showMenu"
            class="absolute right-0 top-full mt-1 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50"
          >
            <button
              @click="handleAction('edit')"
              class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Edit Node
            </button>
            <button
              @click="handleAction('roles')"
              class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              Manage Roles
            </button>
            <button
              v-if="canEnroll"
              @click="handleAction('enroll')"
              :disabled="isEnrolling"
              class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2 disabled:opacity-50"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {{ isEnrolling ? 'Enrolling...' : 'Enroll Node' }}
            </button>
            <button
              @click="handleAction('test')"
              class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
              </svg>
              Test Connection
            </button>
            <button
              @click="handleAction('certificate')"
              class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Certificate
            </button>
            <button
              @click="handleAction('events')"
              class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              View Events
            </button>
            <button
              @click="handleAction('services')"
              class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
              </svg>
              Services
            </button>
            <hr class="my-1 border-gray-200" />
            <button
              @click="handleAction('delete')"
              class="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete Node
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- IP Address & Auth Method -->
    <div class="flex items-center justify-between mb-3">
      <div class="text-sm text-gray-500">
        {{ node.ip_address }}
        <span v-if="node.ssh_port && node.ssh_port !== 22" class="text-gray-400">:{{ node.ssh_port }}</span>
      </div>
      <!-- Auth Method Badge (#722) -->
      <span
        :class="['px-2 py-0.5 text-xs font-medium rounded', authMethodBadge.class]"
        :title="`Authentication: ${authMethodBadge.label}`"
      >
        {{ authMethodBadge.label }}
      </span>
    </div>

    <!-- Enrolling Transition Indicator (#722) -->
    <div
      v-if="isEnrolling"
      class="flex items-center gap-2 px-2 py-1.5 mb-3 bg-blue-50 border border-blue-200 rounded text-xs text-blue-700"
    >
      <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <span>Transitioning to SSH key auth...</span>
    </div>

    <!-- Roles -->
    <div class="flex flex-wrap gap-1 mb-3">
      <span
        v-for="role in node.roles"
        :key="role"
        class="px-2 py-0.5 text-xs font-medium bg-primary-100 text-primary-700 rounded"
      >
        {{ role }}
      </span>
      <span v-if="node.roles.length === 0" class="text-xs text-gray-400 italic">
        No roles assigned
      </span>
    </div>

    <!-- Health Metrics -->
    <div v-if="node.health" class="space-y-2 mb-3">
      <!-- CPU -->
      <div class="flex items-center gap-2 text-xs">
        <span class="w-12 text-gray-500">CPU</span>
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            :class="[
              'h-full rounded-full transition-all',
              node.health.cpu_percent > 80 ? 'bg-red-500' :
              node.health.cpu_percent > 60 ? 'bg-yellow-500' : 'bg-green-500'
            ]"
            :style="{ width: `${node.health.cpu_percent}%` }"
          ></div>
        </div>
        <span class="w-8 text-right text-gray-600">{{ node.health.cpu_percent?.toFixed(0) || 0 }}%</span>
      </div>

      <!-- Memory -->
      <div class="flex items-center gap-2 text-xs">
        <span class="w-12 text-gray-500">MEM</span>
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            :class="[
              'h-full rounded-full transition-all',
              node.health.memory_percent > 80 ? 'bg-red-500' :
              node.health.memory_percent > 60 ? 'bg-yellow-500' : 'bg-green-500'
            ]"
            :style="{ width: `${node.health.memory_percent}%` }"
          ></div>
        </div>
        <span class="w-8 text-right text-gray-600">{{ node.health.memory_percent?.toFixed(0) || 0 }}%</span>
      </div>

      <!-- Disk -->
      <div class="flex items-center gap-2 text-xs">
        <span class="w-12 text-gray-500">DISK</span>
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            :class="[
              'h-full rounded-full transition-all',
              node.health.disk_percent > 80 ? 'bg-red-500' :
              node.health.disk_percent > 60 ? 'bg-yellow-500' : 'bg-green-500'
            ]"
            :style="{ width: `${node.health.disk_percent}%` }"
          ></div>
        </div>
        <span class="w-8 text-right text-gray-600">{{ node.health.disk_percent?.toFixed(0) || 0 }}%</span>
      </div>
    </div>

    <!-- No Health Data -->
    <div v-else class="text-xs text-gray-400 italic mb-3 py-4 text-center">
      No health data available
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between pt-3 border-t border-gray-100">
      <span class="text-xs text-gray-400">Last seen: {{ lastSeen }}</span>
      <div class="flex gap-1">
        <button
          @click="handleAction('view')"
          class="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 transition-colors rounded"
          title="View details"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
        </button>
        <button
          @click="handleAction('restart')"
          class="p-1.5 text-gray-400 hover:text-yellow-600 hover:bg-yellow-50 transition-colors rounded"
          title="Restart services"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
