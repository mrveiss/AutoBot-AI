<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { onMounted, watch, computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import Sidebar from '@/components/common/Sidebar.vue'
import { useFleetStore } from '@/stores/fleet'
import { useAuthStore } from '@/stores/auth'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'

const route = useRoute()
const fleetStore = useFleetStore()
const authStore = useAuthStore()
const ws = useSlmWebSocket()

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
  if (authStore.isAuthenticated) {
    await initializeApp()
  }
})
</script>

<template>
  <!-- Login page - no sidebar -->
  <template v-if="isLoginPage">
    <RouterView />
  </template>

  <!-- Authenticated pages - with sidebar -->
  <template v-else>
    <div class="flex min-h-screen bg-gray-100">
      <Sidebar />
      <main class="flex-1 overflow-auto">
        <RouterView />
      </main>
    </div>
  </template>
</template>
