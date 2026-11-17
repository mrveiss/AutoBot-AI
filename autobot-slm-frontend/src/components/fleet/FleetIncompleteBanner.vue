<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss
-->
<script setup lang="ts">
/**
 * Persistent counterpart of the shell's dismissible incomplete-list toast (#21584): shown for as long
 * as the node list on screen is not the whole fleet.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFleetStore } from '@/stores/fleet'

const { t } = useI18n()
const fleetStore = useFleetStore()

const message = computed(() => {
  const inc = fleetStore.incomplete
  if (!inc) return null
  return t('fleetOverview.incompleteList', {
    loaded: inc.read,
    total: inc.total ?? t('fleetOverview.incompleteTotalUnknown'),
    message: inc.reason,
  })
})
</script>

<template>
  <div v-if="message" class="card p-4 mb-4 text-sm text-yellow-800 bg-yellow-50" role="alert" data-testid="fleet-incomplete-notice">
    {{ message }}
  </div>
</template>
