<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Sidebar Navigation Component
 *
 * Main navigation sidebar for SLM Admin.
 * Includes fleet health summary, navigation items, and user controls.
 * Issue #741: Added Code Sync navigation with update badge.
 * Issue #754: Added ARIA attributes, keyboard navigation, high contrast toggle.
 */

import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFleetStore } from '@/stores/fleet'
import { useAuthStore } from '@/stores/auth'
import { useCodeSync } from '@/composables/useCodeSync'
import { useHighContrast } from '@/composables/useAccessibility'

const route = useRoute()
const router = useRouter()
const fleetStore = useFleetStore()
const authStore = useAuthStore()
const codeSync = useCodeSync()
const highContrast = useHighContrast()

// Polling interval for code sync status (1 minute)
const CODE_SYNC_POLL_INTERVAL = 60000
let codeSyncPollTimer: ReturnType<typeof setInterval> | null = null

const navItems = [
  { name: 'Fleet Overview', path: '/', icon: 'grid' },
  { name: 'Services', path: '/services', icon: 'server' },
  { name: 'Deployments', path: '/deployments', icon: 'rocket' },
  // Issue #786: Infrastructure setup wizard
  { name: 'Infrastructure', path: '/infrastructure', icon: 'infra' },
  { name: 'Backups', path: '/backups', icon: 'database' },
  { name: 'Replication', path: '/replications', icon: 'replicate' },
  { name: 'Code Sync', path: '/code-sync', icon: 'download', showBadge: true },
  // Issue #760: Agent LLM configuration management
  { name: 'Agent Config', path: '/agent-config', icon: 'agents' },
  // Issue #838: Service Orchestration page
  { name: 'Orchestration', path: '/orchestration', icon: 'orchestration' },
  // Issue #840: Updates management page
  { name: 'Updates', path: '/updates', icon: 'updates' },
  // Issue #841: Role Registry management page
  { name: 'Roles', path: '/roles', icon: 'roles' },
  // Issue #731: Skills system management
  { name: 'Skills', path: '/skills', icon: 'skills' },
  { name: 'Maintenance', path: '/maintenance', icon: 'wrench' },
  { name: 'Settings', path: '/settings', icon: 'cog' },
  { name: 'Performance', path: '/performance', icon: 'performance' },
  { name: 'Monitoring', path: '/monitoring', icon: 'chart' },
  { name: 'Security', path: '/security', icon: 'shield' },
  { name: 'Tools', path: '/tools', icon: 'tools' },
]

const currentPath = computed(() => route.path)

const healthClass = computed(() => {
  switch (fleetStore.overallHealth) {
    case 'healthy': return 'bg-success-500'
    case 'degraded': return 'bg-warning-500'
    case 'unhealthy': return 'bg-danger-500'
    default: return 'bg-gray-400'
  }
})

const healthLabel = computed(() => {
  return `Fleet health: ${fleetStore.overallHealth || 'unknown'}`
})

/**
 * Navigate to a path.
 */
function navigate(path: string): void {
  router.push(path)
}

/**
 * Handle keyboard navigation within sidebar nav items.
 *
 * Helper for Sidebar keyboard navigation (Issue #754).
 */
function handleNavKeydown(event: KeyboardEvent, index: number): void {
  const items = navItems
  let targetIndex = -1

  switch (event.key) {
    case 'ArrowDown':
      targetIndex = index < items.length - 1 ? index + 1 : 0
      break
    case 'ArrowUp':
      targetIndex = index > 0 ? index - 1 : items.length - 1
      break
    case 'Home':
      targetIndex = 0
      break
    case 'End':
      targetIndex = items.length - 1
      break
    default:
      return
  }

  event.preventDefault()
  const navEl = document.querySelector(`[data-nav-index="${targetIndex}"]`)
  if (navEl instanceof HTMLElement) {
    navEl.focus()
  }
}

/**
 * Handle user logout.
 */
function handleLogout(): void {
  authStore.logout()
}

/**
 * Refresh code sync status from backend.
 */
async function refreshCodeSyncStatus(): Promise<void> {
  await codeSync.fetchStatus()
}

onMounted(async () => {
  if (!authStore.isAuthenticated) return
  // Fetch initial code sync status
  await refreshCodeSyncStatus()
  // Set up polling for code sync status
  codeSyncPollTimer = setInterval(refreshCodeSyncStatus, CODE_SYNC_POLL_INTERVAL)
})

onUnmounted(() => {
  if (codeSyncPollTimer) {
    clearInterval(codeSyncPollTimer)
    codeSyncPollTimer = null
  }
})
</script>

<template>
  <aside
    class="w-64 bg-gray-900 text-white min-h-screen flex flex-col"
    aria-label="Sidebar navigation"
  >
    <!-- Logo & Title -->
    <div class="p-4 border-b border-gray-800">
      <div class="flex items-center gap-3">
        <div
          class="w-10 h-10 bg-primary-600 rounded-lg flex items-center justify-center"
          aria-hidden="true"
        >
          <span class="text-xl font-bold">S</span>
        </div>
        <div>
          <h1 class="font-bold text-lg">SLM Admin</h1>
          <p class="text-xs text-gray-400">Service Lifecycle Manager</p>
        </div>
      </div>
    </div>

    <!-- Fleet Health Summary -->
    <div class="p-4 border-b border-gray-800" role="status" :aria-label="healthLabel">
      <div class="flex items-center gap-2 mb-2">
        <div
          :class="['w-3 h-3 rounded-full', healthClass]"
          role="img"
          :aria-label="healthLabel"
        ></div>
        <span class="text-sm font-medium">Fleet Health</span>
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs">
        <div class="flex justify-between">
          <span class="text-gray-400">Total:</span>
          <span>{{ fleetStore.fleetSummary.total_nodes }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-success-500">Healthy:</span>
          <span>{{ fleetStore.fleetSummary.healthy_nodes }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-warning-500">Degraded:</span>
          <span>{{ fleetStore.fleetSummary.degraded_nodes }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-danger-500">Unhealthy:</span>
          <span>{{ fleetStore.fleetSummary.unhealthy_nodes }}</span>
        </div>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 p-4" aria-label="Main navigation">
      <ul class="space-y-1" role="menubar" aria-orientation="vertical">
        <li v-for="(item, index) in navItems" :key="item.path" role="none">
          <button
            @click="navigate(item.path)"
            @keydown="handleNavKeydown($event, index)"
            :data-nav-index="index"
            :aria-current="currentPath === item.path ? 'page' : undefined"
            role="menuitem"
            :tabindex="currentPath === item.path ? 0 : -1"
            :class="[
              'w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors',
              currentPath === item.path
                ? 'bg-primary-600 text-white'
                : 'text-gray-300 hover:bg-gray-800 hover:text-white'
            ]"
          >
            <span class="w-5 h-5 flex items-center justify-center" aria-hidden="true">
              <!-- Icons -->
              <svg v-if="item.icon === 'grid'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              <svg v-else-if="item.icon === 'server'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
              </svg>
              <svg v-else-if="item.icon === 'rocket'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <svg v-else-if="item.icon === 'database'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
              <svg v-else-if="item.icon === 'switch'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
              <svg v-else-if="item.icon === 'replicate'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <!-- Issue #741: Download icon for Code Sync -->
              <svg v-else-if="item.icon === 'download'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              <!-- Issue #760: Agents icon for Agent Configuration -->
              <svg v-else-if="item.icon === 'agents'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <!-- Issue #786: Infrastructure setup wizard icon -->
              <svg v-else-if="item.icon === 'infra'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              <!-- Issue #838: Orchestration icon (play/network) -->
              <svg v-else-if="item.icon === 'orchestration'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <!-- Issue #840: Updates icon (arrow-up-circle) -->
              <svg v-else-if="item.icon === 'updates'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 11l3-3m0 0l3 3m-3-3v8m0-13a9 9 0 110 18 9 9 0 010-18z" />
              </svg>
              <!-- Issue #841: Roles icon (identification/tag) -->
              <svg v-else-if="item.icon === 'roles'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              <svg v-else-if="item.icon === 'wrench'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <svg v-else-if="item.icon === 'cog'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <!-- Issue #752: Performance/speedometer icon -->
              <svg v-else-if="item.icon === 'performance'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <svg v-else-if="item.icon === 'chart'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <svg v-else-if="item.icon === 'shield'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <svg v-else-if="item.icon === 'tools'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879M12 12L9.121 9.121m0 5.758a3 3 0 10-4.243 4.243 3 3 0 004.243-4.243zm0-5.758a3 3 0 10-4.243-4.243 3 3 0 004.243 4.243z" />
              </svg>
            </span>
            <span class="flex-1 text-left">{{ item.name }}</span>
            <!-- Issue #741: Badge for Code Sync updates -->
            <span
              v-if="item.showBadge && codeSync.hasOutdatedNodes.value"
              class="nav-badge"
              :aria-label="`${codeSync.outdatedCount.value} nodes need updates`"
              role="status"
            >
              {{ codeSync.outdatedCount.value }}
            </span>
          </button>
        </li>
      </ul>
    </nav>

    <!-- User & Logout -->
    <div class="p-4 border-t border-gray-800">
      <!-- Issue #754: High contrast toggle -->
      <button
        @click="highContrast.toggle()"
        class="w-full flex items-center gap-2 px-3 py-2 mb-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white rounded-lg transition-colors"
        :aria-pressed="highContrast.enabled.value"
        aria-label="Toggle high contrast mode"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
        <span>{{ highContrast.enabled.value ? 'Standard Mode' : 'High Contrast' }}</span>
      </button>

      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <div
            class="w-8 h-8 bg-primary-600 rounded-full flex items-center justify-center text-sm font-medium"
            aria-hidden="true"
          >
            {{ authStore.user?.username?.charAt(0).toUpperCase() || 'U' }}
          </div>
          <div>
            <p class="text-sm font-medium">{{ authStore.user?.username || 'User' }}</p>
            <p class="text-xs text-gray-400">{{ authStore.isAdmin ? 'Admin' : 'User' }}</p>
          </div>
        </div>
        <button
          @click="handleLogout"
          class="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          aria-label="Log out"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
        </button>
      </div>
      <p class="text-xs text-gray-500">SLM Admin v1.0.0</p>
    </div>
  </aside>
</template>

<style scoped>
/* Issue #741: Navigation badge for Code Sync updates */
.nav-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: #f59e0b; /* amber-500 / warning */
  color: white;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
</style>
