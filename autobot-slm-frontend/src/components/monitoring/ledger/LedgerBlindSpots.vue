<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  LedgerBlindSpots (#18391 AC2): what the SLM agent ledger cannot see right now,
  said in plain language so an absent source never reads as "none": any store or
  live-state snapshot `GET /monitoring/agent-ledger/sources` reports unreachable
  (#18632: live state is now read from the user backend's snapshot, so it is
  missing only while that snapshot is), and the known gaps #16950 / #16962.
-->
<template>
  <aside class="flex flex-col gap-2 p-3 rounded border border-(--aui-color-border) bg-(--aui-color-surface-sunken)" data-testid="slm-ledger-blind-spots">
    <h3 class="m-0 text-sm font-semibold">{{ t('monitoring.agentLedger.notes.title') }}</h3>
    <p v-for="s in down" :key="s" class="m-0 text-sm" role="alert" data-testid="slm-ledger-down">
      {{ t('monitoring.agentLedger.notes.storeDown', { source: s }) }}
    </p>
    <p v-if="sources.state === 'unavailable' || sources.state === 'error'" class="m-0 text-sm" role="alert" data-testid="slm-ledger-sources-unknown">
      {{ t('monitoring.agentLedger.notes.sourcesUnknown') }}
    </p>
    <p class="m-0 text-sm" data-testid="slm-ledger-gap-16950">{{ t('monitoring.agentLedger.notes.peerIdentity') }}</p>
    <p class="m-0 text-sm" data-testid="slm-ledger-gap-16962">{{ t('monitoring.agentLedger.notes.busAuth') }}</p>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LedgerSection } from '@autobot/ui'
import type { LedgerSourceStatus } from '@/composables/useSlmAgentLedger'

const props = defineProps<{ sources: LedgerSection<LedgerSourceStatus> }>()
const { t, te } = useI18n()

function sourceName(source: string): string {
  const key = `monitoring.agentLedger.source.${source}`
  return te(key) ? t(key) : source
}

const down = computed(() => props.sources.rows.filter((s) => !s.reachable).map((s) => sourceName(s.source)))
</script>
