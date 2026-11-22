<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  LedgerLivePanel (#18632): who is working on what across every company, from
  the user backend's live-state snapshot -- Company OS agents, AI-stack agents
  and live sessions, then pending peer messages (counts and senders, never
  content) and idle waits. Each section says "couldn't read" apart from "none"
  through the kit's LedgerSectionState: a missing snapshot is a 503, not [].
-->
<template>
  <div class="flex flex-col gap-3">
    <LedgerSectionState :section="presence" :empty="t('monitoring.agentLedger.empty.presence')" :labels="labels">
      <table class="w-full border-collapse [&_th]:p-2 [&_td]:p-2 [&_th]:text-start [&_tr]:border-b [&_tr]:border-(--aui-color-border)" data-testid="slm-ledger-presence">
        <thead><tr><th v-for="c in COLUMNS" :key="c">{{ t(`monitoring.agentLedger.col.${c}`) }}</th></tr></thead>
        <tbody>
          <tr v-for="a in presence.rows" :key="`${a.kind}:${a.tenant_id}:${a.name}`">
            <td>{{ companyOf(a.tenant_id) }}</td><td>{{ a.name }}</td><td>{{ a.kind }}</td>
            <td>{{ a.busy ? t('monitoring.agentLedger.busy') : t('monitoring.agentLedger.idle') }}</td>
            <td class="max-w-xs truncate" :title="a.current_task?.title" data-testid="slm-ledger-current-task">{{ a.current_task?.title ?? '' }}</td>
            <td>{{ a.detail ?? '' }}</td>
          </tr>
        </tbody>
      </table>
    </LedgerSectionState>

    <h3 class="m-0 text-base">{{ t('monitoring.agentLedger.peerMessages') }}</h3>
    <LedgerSectionState :section="peerMessages" :empty="t('monitoring.agentLedger.empty.peerMessages')" :labels="labels">
      <ul class="m-0 ps-5" data-testid="slm-ledger-peer-messages">
        <li v-for="m in peerMessages.rows" :key="`${m.tenant_id}:${m.recipient_kind}:${m.recipient_name}`">
          {{ t('monitoring.agentLedger.pendingFor', { name: m.recipient_name, n: m.pending }) }} ({{ companyOf(m.tenant_id) }})
          <span class="text-(--aui-color-text-muted)">{{ t('monitoring.agentLedger.sentBy', { names: m.senders.join(', ') }) }}</span>
        </li>
      </ul>
    </LedgerSectionState>

    <h3 class="m-0 text-base">{{ t('monitoring.agentLedger.idleSubscribers') }}</h3>
    <LedgerSectionState :section="idleSubscribers" :empty="t('monitoring.agentLedger.empty.idleSubscribers')" :labels="labels">
      <ul class="m-0 ps-5" data-testid="slm-ledger-idle-subscribers">
        <li v-for="(s, i) in idleSubscribers.rows" :key="`${s.subscriber}:${s.target_name}:${i}`">
          {{ t('monitoring.agentLedger.waitsForIdle', { who: s.subscriber, target: s.target_name }) }} ({{ companyOf(s.tenant_id) }})
        </li>
      </ul>
    </LedgerSectionState>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LedgerSectionState, type LedgerSection, type LedgerStateLabels } from '@autobot/ui'
import type { IdleSubscriberRow, PeerMessageRow, PresenceRow } from '@/composables/useSlmAgentLedger'

defineProps<{
  presence: LedgerSection<PresenceRow>
  peerMessages: LedgerSection<PeerMessageRow>
  idleSubscribers: LedgerSection<IdleSubscriberRow>
  labels: LedgerStateLabels
}>()
const { t } = useI18n()

const COLUMNS = ['company', 'agent', 'kind', 'status', 'task', 'detail'] as const

function companyOf(tenantId: string | null | undefined): string {
  return tenantId ?? t('monitoring.agentLedger.installWide')
}
</script>
