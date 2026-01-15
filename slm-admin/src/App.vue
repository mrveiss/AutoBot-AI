<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import Sidebar from '@/components/common/Sidebar.vue'
import { useFleetStore } from '@/stores/fleet'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'

const fleetStore = useFleetStore()
const ws = useSlmWebSocket()

onMounted(async () => {
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
})
</script>

<template>
  <div class="flex min-h-screen bg-gray-100">
    <Sidebar />
    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>
  </div>
</template>
