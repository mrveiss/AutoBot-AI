<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Update Notification Component (Issue #741 - Phase 6)
 *
 * Top-bar notification banner that appears when nodes need code updates.
 * Provides quick access to the Code Sync page and can be dismissed.
 */

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCodeSync } from '@/composables/useCodeSync'

const router = useRouter()
const codeSync = useCodeSync()

// Dismissal state (persisted per session via localStorage)
const DISMISS_KEY = 'slm_update_notification_dismissed'
const DISMISS_VERSION_KEY = 'slm_update_notification_dismissed_version'

const isDismissed = ref(false)

// Show notification if: there are outdated nodes AND not dismissed for this version
const shouldShow = computed(() => {
  if (isDismissed.value) return false
  if (!codeSync.hasOutdatedNodes.value) return false
  return true
})

// Check if user previously dismissed this version
onMounted(() => {
  const dismissed = localStorage.getItem(DISMISS_KEY)
  const dismissedVersion = localStorage.getItem(DISMISS_VERSION_KEY)

  // If a new version is available, reset the dismissal
  if (dismissed === 'true' && dismissedVersion === codeSync.latestVersion.value) {
    isDismissed.value = true
  } else if (codeSync.latestVersion.value !== dismissedVersion) {
    // New version detected, show notification again
    isDismissed.value = false
    localStorage.removeItem(DISMISS_KEY)
  }
})

function dismiss(): void {
  isDismissed.value = true
  localStorage.setItem(DISMISS_KEY, 'true')
  localStorage.setItem(DISMISS_VERSION_KEY, codeSync.latestVersion.value || '')
}

function goToCodeSync(): void {
  router.push('/code-sync')
}
</script>

<template>
  <Transition
    enter-active-class="transition duration-300 ease-out"
    enter-from-class="transform -translate-y-full opacity-0"
    enter-to-class="transform translate-y-0 opacity-100"
    leave-active-class="transition duration-200 ease-in"
    leave-from-class="transform translate-y-0 opacity-100"
    leave-to-class="transform -translate-y-full opacity-0"
  >
    <div
      v-if="shouldShow"
      class="update-notification"
    >
      <div class="flex items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <!-- Warning icon -->
          <div class="flex-shrink-0">
            <svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <!-- Message -->
          <p class="text-sm font-medium text-amber-800">
            <span class="font-semibold">{{ codeSync.outdatedCount.value }}</span>
            {{ codeSync.outdatedCount.value === 1 ? 'node needs' : 'nodes need' }}
            code updates
            <span v-if="codeSync.latestVersionShort.value" class="text-amber-600">
              (latest: {{ codeSync.latestVersionShort.value }})
            </span>
          </p>
        </div>

        <div class="flex items-center gap-2">
          <!-- View Updates button -->
          <button
            @click="goToCodeSync"
            class="px-3 py-1.5 text-sm font-medium text-amber-800 bg-amber-200 hover:bg-amber-300 rounded-md transition-colors"
          >
            View Updates
          </button>
          <!-- Dismiss button -->
          <button
            @click="dismiss"
            class="p-1.5 text-amber-600 hover:text-amber-800 hover:bg-amber-200 rounded-md transition-colors"
            title="Dismiss"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.update-notification {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-bottom: 1px solid #f59e0b;
  padding: 0.75rem 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
</style>
