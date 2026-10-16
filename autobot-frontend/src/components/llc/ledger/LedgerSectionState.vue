<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  LedgerSectionState (#18391 AC3): one ledger section's state, said the same
  way everywhere. "Couldn't read the ledger" (a typed 503, naming the store)
  never reads like "no claims" (an empty list that was actually read). The
  default slot renders only when the section is ready and has rows.
-->
<template>
  <p v-if="section.state === 'loading'" class="m-0 p-4 text-autobot-text-secondary" role="status" data-testid="ledger-loading">
    {{ t('llc.ledger.state.loading') }}
  </p>
  <div v-else-if="section.state === 'unavailable'" class="flex flex-col gap-1 p-4 rounded border border-autobot-warning bg-autobot-bg-secondary text-autobot-text-primary" role="alert" data-testid="ledger-unavailable">
    <strong>{{ t('llc.ledger.state.unavailableTitle') }}</strong>
    <span>{{ t('llc.ledger.state.unavailableBody', { source: section.source || '—' }) }}</span>
  </div>
  <div v-else-if="section.state === 'error'" class="flex flex-col gap-1 p-4 rounded border border-autobot-warning bg-autobot-bg-secondary text-autobot-text-primary" role="alert" data-testid="ledger-error">
    <strong>{{ t('llc.ledger.state.errorTitle') }}</strong>
  </div>
  <EmptyState v-else-if="section.rows.length === 0" :title="empty" data-testid="ledger-empty" />
  <slot v-else />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { EmptyState } from '@autobot/ui'
import type { LedgerSection } from '@/composables/useAgentLedger'

defineProps<{ section: LedgerSection<unknown>; empty: string }>()
const { t } = useI18n()
</script>
