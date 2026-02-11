<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Main App Component
 *
 * Issue #741: Added UpdateNotification for code sync alerts.
 * Issue #754: Added SkipLink, ARIA landmarks, high contrast init.
 */

import { onMounted, watch, computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import Sidebar from '@/components/common/Sidebar.vue'
import SkipLink from '@/components/common/SkipLink.vue'
import UpdateNotification from '@/components/UpdateNotification.vue'
import { useFleetStore } from '@/stores/fleet'
import { useAuthStore } from '@/stores/auth'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { useHighContrast } from '@/composables/useAccessibility'

const route = useRoute()
const fleetStore = useFleetStore()
const authStore = useAuthStore()
const ws = useSlmWebSocket()
const highContrast = useHighContrast()

const isLoginPage = computed(() => route.name === 'login')

// Watch for authentication changes
watch(
  () => authStore.isAuthenticated,
  async (isAuthenticated) => {
    if (isAuthenticated) {
      await initializeApp()
    } else {
      ws.disconnect()
    }
  }
)

async function initializeApp(): Promise<void> {
  // Load initial fleet data
  await fleetStore.fetchNodes()

  // Connect WebSocket for real-time updates
  ws.connect()
  ws.subscribeAll()

  // Handle real-time health updates
  ws.onHealthUpdate((nodeId, health) => {
    fleetStore.updateNodeHealth(nodeId, health)
  })

  ws.onNodeStatus((nodeId, status) => {
    fleetStore.updateNodeStatus(nodeId, status)
  })
}

onMounted(async () => {
  // Issue #754: Initialize high contrast preference from localStorage
  highContrast.init()

  if (authStore.isAuthenticated) {
    await initializeApp()
  }
})
</script>

<template>
  <!-- Issue #754: Skip link for keyboard navigation -->
  <SkipLink />

  <!-- Login page - no sidebar -->
  <template v-if="isLoginPage">
    <RouterView />
  </template>

  <!-- Authenticated pages - with sidebar -->
  <template v-else>
    <div class="flex min-h-screen bg-gray-100">
      <Sidebar />
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- Issue #741: Top-bar notification for code updates -->
        <UpdateNotification />
        <main
          id="main-content"
          class="flex-1 overflow-auto"
          aria-label="Main content"
        >
          <RouterView />
        </main>
      </div>
    </div>
  </template>
</template>
