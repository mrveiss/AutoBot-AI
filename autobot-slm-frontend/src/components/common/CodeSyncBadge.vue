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
import { onMounted } from 'vue'
import { usePollingJob } from '@autobot/ui'
import { useRouter } from 'vue-router'
import { useCodeSync } from '@/composables/useCodeSync'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const codeSync = useCodeSync()
const authStore = useAuthStore()

// Polling interval for status updates (1 minute)
const POLL_INTERVAL = 60000

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

// #19482: usePollingJob for scope disposal. No consecutiveErrorLimit and no paused
// alert: this is a 60s status poll in the app chrome, where a banner would be the
// wrong surface, so it keeps polling through failures as before.
const statusPoller = usePollingJob(refresh, { intervalMs: POLL_INTERVAL, maxAttempts: Infinity })

onMounted(() => {
  if (!authStore.isAuthenticated) return
  statusPoller.start('')
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
  color: var(--text-muted);
  transition: all 0.2s ease;
}

.code-sync-badge:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.code-sync-badge.has-updates {
  color: var(--color-warning);
}

.code-sync-badge.has-updates:hover {
  color: var(--color-warning-hover);
}

.badge-count {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: var(--color-warning);
  color: var(--text-on-warning);
  border-radius: 8px;
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
</style>
