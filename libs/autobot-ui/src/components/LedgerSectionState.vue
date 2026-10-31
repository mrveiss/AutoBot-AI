<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  LedgerSectionState (#18391): one agent-ledger section's state, said the same
  way in both consoles. "Couldn't read the ledger" (a typed 503, naming the
  store) never reads like "no claims" (an empty list that was actually read).
  The default slot renders only when the section is ready and has rows.

  The kit hardcodes no user-facing text: apps pass their translated `labels`
  and the `empty` line.
-->
<script setup lang="ts">
import EmptyState from './EmptyState.vue'
import type { LedgerSection } from '../utils/ledger'

export interface LedgerStateLabels {
  loading: string
  unavailableTitle: string
  /** Names the store that did not answer. */
  unavailableBody: (source: string) => string
  errorTitle: string
}

defineProps<{
  section: LedgerSection<unknown>
  empty: string
  labels: LedgerStateLabels
}>()
</script>

<template>
  <p v-if="section.state === 'loading'" class="aui-ledger-state" role="status" data-testid="ledger-loading">
    {{ labels.loading }}
  </p>
  <div
    v-else-if="section.state === 'unavailable'"
    class="aui-ledger-state aui-ledger-state--alert"
    role="alert"
    data-testid="ledger-unavailable"
  >
    <strong>{{ labels.unavailableTitle }}</strong>
    <span>{{ labels.unavailableBody(section.source || '—') }}</span>
  </div>
  <div
    v-else-if="section.state === 'error'"
    class="aui-ledger-state aui-ledger-state--alert"
    role="alert"
    data-testid="ledger-error"
  >
    <strong>{{ labels.errorTitle }}</strong>
  </div>
  <EmptyState v-else-if="section.rows.length === 0" :title="empty" data-testid="ledger-empty" />
  <slot v-else />
</template>

<style scoped>
.aui-ledger-state {
  margin: 0;
  padding: var(--aui-space-4);
  font-family: var(--aui-font-sans);
  color: var(--aui-color-text-muted);
}

.aui-ledger-state--alert {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-1);
  border: 1px solid var(--aui-color-warning);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
}
</style>
