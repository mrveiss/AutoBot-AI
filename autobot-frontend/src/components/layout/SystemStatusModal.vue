<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  SystemStatusModal — the system-health panel (#18240). It replaces the
  hand-rolled overlay that lived in App.vue with the kit's BaseModal (focus
  trap, Esc, scroll lock, aria-modal) and reads the shell's one shared
  useSystemStatus instance, so it shows exactly what the header dot shows.
-->
<template>
  <BaseModal v-model="showSystemStatus" :title="$t('nav.systemStatus')" :close-label="$t('common.close')" size="sm">
    <div class="space-y-4" data-testid="system-status-modal">
      <div class="flex items-center rounded-lg border p-3" :class="panelTone[statusTone]">
        <span class="me-3 h-3 w-3 shrink-0 rounded-full" :class="dotTone[statusTone]" aria-hidden="true"></span>
        <div>
          <p class="font-medium text-autobot-text-primary">{{ getSystemStatusText() }}</p>
          <p class="text-sm text-autobot-text-secondary">{{ getSystemStatusDescription() }}</p>
        </div>
      </div>

      <div class="space-y-2">
        <h4 class="font-medium text-autobot-text-primary">{{ $t('nav.services') }}</h4>
        <ul class="space-y-2">
          <li
            v-for="service in systemServices"
            :key="service.name"
            class="flex items-center justify-between rounded border border-autobot-border p-2"
          >
            <span class="flex items-center text-sm font-medium text-autobot-text-primary">
              <span class="me-2 h-2 w-2 rounded-full" :class="dotTone[toneOf(service.status)]" aria-hidden="true"></span>
              {{ service.name }}
            </span>
            <span class="text-xs" :class="textTone[toneOf(service.status)]">{{ service.statusText }}</span>
          </li>
        </ul>
      </div>
    </div>

    <template #actions>
      <button
        type="button"
        class="rounded-md border border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm font-medium text-autobot-text-primary hover:bg-autobot-bg-tertiary focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary"
        @click="refreshSystemStatus"
      >
        {{ $t('common.refresh') }}
      </button>
      <button
        type="button"
        class="rounded-md bg-autobot-primary px-4 py-2 text-sm font-medium text-autobot-text-inverse hover:bg-autobot-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary"
        @click="showSystemStatus = false"
      >
        {{ $t('common.close') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { BaseModal } from '@autobot/ui'
import type { ServiceHealthStatus } from '@/composables/useSystemStatus'
import { useInjectedSystemStatus, type StatusTone } from '@/composables/systemStatusContext'

const {
  showSystemStatus,
  statusTone,
  systemServices,
  getSystemStatusText,
  getSystemStatusDescription,
  refreshSystemStatus,
} = useInjectedSystemStatus()

const panelTone: Record<StatusTone, string> = {
  success: 'border-autobot-success bg-autobot-success-bg',
  warning: 'border-autobot-warning bg-autobot-warning-bg',
  error: 'border-autobot-error bg-autobot-error-bg',
}
const dotTone: Record<StatusTone, string> = {
  success: 'bg-autobot-success',
  warning: 'bg-autobot-warning',
  error: 'bg-autobot-error',
}
const textTone: Record<StatusTone, string> = {
  success: 'text-autobot-success',
  warning: 'text-autobot-warning',
  error: 'text-autobot-error',
}
const TONE_OF: Record<ServiceHealthStatus, StatusTone> = { healthy: 'success', warning: 'warning', error: 'error' }
const toneOf = (status: ServiceHealthStatus): StatusTone => TONE_OF[status]
</script>
