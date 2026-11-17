<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss
-->
<script setup lang="ts">
/**
 * What the fleet page shows in place of a node grid. A read that failed outright says so; only a
 * read that succeeded and found nothing says "no nodes registered" (#21735 review).
 */
import { useFleetStore } from '@/stores/fleet'

const emit = defineEmits<{ add: [] }>()
const fleetStore = useFleetStore()
</script>

<template>
  <div v-if="fleetStore.nodesError" class="card p-12 text-center text-red-700" role="alert" data-testid="fleet-load-error">
    {{ $t('fleetOverview.loadFailed', { message: fleetStore.nodesError }) }}
  </div>
  <div v-else class="card p-12 text-center">
    <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
    </svg>
    <h3 class="text-lg font-medium text-gray-900 mb-2">{{ $t('fleetOverview.noNodesRegistered') }}</h3>
    <p class="text-gray-500 mb-4">{{ $t('fleetOverview.addANodeTo') }}</p>
    <button @click="emit('add')" class="btn btn-primary">{{ $t('fleetOverview.addFirstNode') }}</button>
  </div>
</template>
