<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Code Sync Badge Component (Issue #741)
 *
 * Displays a notification badge when nodes have pending code updates.
 * Can be used in the top bar or as a standalone notification indicator.
 */
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCodeSync } from '@/composables/useCodeSync'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const codeSync = useCodeSync()
const authStore = useAuthStore()

// Polling interval for status updates (1 minute)
const POLL_INTERVAL = 60000
let pollTimer: ReturnType<typeof setInterval> | null = null

/**
 * Navigate to the Code Sync management page.
 */
function navigateToCodeSync(): void {
  router.push('/code-sync')
}

/**
 * Refresh code sync status from backend.
 */
async function refresh(): Promise<void> {
  await codeSync.fetchStatus()
}

onMounted(async () => {
  if (!authStore.isAuthenticated) return
  await refresh()
  pollTimer = setInterval(refresh, POLL_INTERVAL)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<template>
  <button
    class="code-sync-badge"
    :class="{ 'has-updates': codeSync.hasOutdatedNodes.value }"
    @click="navigateToCodeSync"
    :title="
      codeSync.hasOutdatedNodes.value
        ? `${codeSync.outdatedCount.value} nodes need updates`
        : 'All nodes up to date'
    "
  >
    <!-- Download/sync icon -->
    <svg
      class="w-5 h-5"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
      />
    </svg>
    <span v-if="codeSync.hasOutdatedNodes.value" class="badge-count">
      {{ codeSync.outdatedCount.value }}
    </span>
  </button>
</template>

<style scoped>
.code-sync-badge {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  color: #9ca3af; /* text-gray-400 */
  transition: all 0.2s ease;
}

.code-sync-badge:hover {
  background: rgba(55, 65, 81, 0.5); /* gray-700 with opacity */
  color: #ffffff;
}

.code-sync-badge.has-updates {
  color: #f59e0b; /* amber-500 / warning */
}

.code-sync-badge.has-updates:hover {
  color: #fbbf24; /* amber-400 */
}

.badge-count {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: #f59e0b; /* amber-500 / warning */
  color: white;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
</style>
