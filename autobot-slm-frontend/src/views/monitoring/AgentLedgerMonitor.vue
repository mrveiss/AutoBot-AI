<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  AgentLedgerMonitor -- SLM > Monitoring > Agent ledger, admin only (#18391 AC2,
  mockup SlmAgentLedger). The same ledger as the Company OS view, across every
  company: shared-resource contention, every claim, conflicts, dev-loop history
  per issue and the ledger's activity. What the SLM cannot read (presence,
  AI-stack agents, live sessions, peer messages, idle subscriptions) and the
  known gaps #16950 / #16962 are said in plain language, never shown as empty.

  The one human action is "Ask holder to release": the same yield request an
  agent sends; silence means hold. No force-release, no delete, by design.
-->
<template>
  <div class="flex flex-col gap-4 p-4 text-(--aui-color-text)" data-testid="slm-agent-ledger">
    <header class="flex flex-wrap items-baseline gap-3">
      <h2 class="m-0 text-xl font-semibold">{{ t('monitoring.agentLedger.title') }}</h2>
      <p class="m-0 text-(--aui-color-text-muted)">{{ t('monitoring.agentLedger.subtitle') }}</p>
      <BaseButton class="ms-auto" variant="secondary" size="sm" @click="ledger.refresh()">{{ t('monitoring.agentLedger.refresh') }}</BaseButton>
    </header>

    <LedgerBlindSpots :sources="ledger.sources.value" />

    <div class="flex gap-2 border-b border-(--aui-color-border)" role="tablist" :aria-label="t('monitoring.agentLedger.tabsAria')">
      <button
        v-for="(tab, i) in tabs" :id="`slm-ledger-tab-${tab.id}`" :key="tab.id" ref="tabEls" type="button" role="tab"
        :aria-controls="`slm-ledger-panel-${tab.id}`" :aria-selected="active === tab.id" :tabindex="active === tab.id ? 0 : -1"
        class="px-3 py-2 text-(--aui-color-text-muted) aria-selected:text-(--aui-color-text) aria-selected:border-b-2 aria-selected:border-(--aui-color-primary)"
        :data-testid="`slm-ledger-tab-${tab.id}`" @click="active = tab.id" @keydown="onTabKey($event, i)"
      >{{ tab.label }}</button>
    </div>

    <section :id="`slm-ledger-panel-${active}`" role="tabpanel" :aria-labelledby="`slm-ledger-tab-${active}`" tabindex="0">
      <template v-if="active === 'contention'">
        <p class="m-0 mb-3 text-(--aui-color-text-muted)">{{ t('monitoring.agentLedger.silenceMeansHold') }}</p>
        <LedgerSectionState :section="ledger.contention.value" :empty="t('monitoring.agentLedger.empty.contention')" :labels="labels">
          <div class="flex flex-col gap-3">
            <BaseCard v-for="(r, ri) in ledger.contention.value.rows" :key="r.scope" data-testid="slm-ledger-resource">
              <h3 class="m-0 mb-2 flex items-center gap-2 text-sm">
                <code>{{ r.scope }}</code>
                <BaseBadge :variant="r.contended ? 'warning' : 'neutral'" size="sm">{{ t('monitoring.agentLedger.waiting', { n: r.waiters.length }) }}</BaseBadge>
              </h3>
              <div v-for="(h, hi) in r.holders" :key="h.task_id" class="flex flex-wrap items-center gap-2">
                <span>{{ t('monitoring.agentLedger.heldBy', { agent: h.agent_id, company: companyOf(h.company_id) }) }}</span>
                <BaseButton
                  class="ms-auto" variant="secondary" size="sm" data-testid="slm-ledger-ask"
                  :aria-label="t('monitoring.agentLedger.askAria', { scope: r.scope })" :aria-describedby="`slm-ledger-ask-${ri}-${hi}`"
                  :loading="asks[askKey(r.scope, h.task_id)] === 'sending'" @click="ask(r.scope, h.task_id)"
                >{{ t('monitoring.agentLedger.ask') }}</BaseButton>
                <span :id="`slm-ledger-ask-${ri}-${hi}`" class="w-full text-sm text-(--aui-color-text-muted)" role="status" data-testid="slm-ledger-ask-status">
                  {{ askText(asks[askKey(r.scope, h.task_id)]) }}
                </span>
              </div>
              <ol v-if="r.waiters.length" class="m-0 mt-2 ps-5" :aria-label="t('monitoring.agentLedger.waitlistAria')">
                <li v-for="w in r.waiters" :key="w.task_id">{{ w.agent_id }} — {{ w.intent }}</li>
              </ol>
            </BaseCard>
          </div>
        </LedgerSectionState>
      </template>

      <LedgerSectionState v-else-if="active === 'claims'" :section="ledger.claims.value" :empty="t('monitoring.agentLedger.empty.claims')" :labels="labels">
        <table class="w-full border-collapse [&_th]:p-2 [&_td]:p-2 [&_th]:text-start [&_tr]:border-b [&_tr]:border-(--aui-color-border)" data-testid="slm-ledger-claims">
          <thead><tr><th v-for="c in CLAIM_COLUMNS" :key="c">{{ t(`monitoring.agentLedger.col.${c}`) }}</th></tr></thead>
          <tbody>
            <tr v-for="c in ledger.claims.value.rows" :key="`${c.scope}:${c.task_id}`">
              <td><code>{{ c.scope }}</code></td><td>{{ c.agent_id }}</td><td>{{ companyOf(c.company_id) }}</td><td>{{ c.mode }}</td>
              <td>{{ c.intent }}</td><td><time :datetime="c.expires_at">{{ c.expires_at }}</time></td><td>{{ c.renewals }}</td>
            </tr>
          </tbody>
        </table>
      </LedgerSectionState>

      <LedgerSectionState v-else-if="active === 'conflicts'" :section="ledger.conflicts.value" :empty="t('monitoring.agentLedger.empty.conflicts')" :labels="labels">
        <ul class="m-0 ps-5" data-testid="slm-ledger-conflicts">
          <li v-for="(c, i) in ledger.conflicts.value.rows" :key="`${c.at}:${c.kind}:${i}`">
            <time :datetime="c.at">{{ c.at }}</time> — {{ t(`monitoring.agentLedger.conflict.${c.kind}`) }}
            <code v-if="c.scope">{{ c.scope }}</code> {{ c.agent_id ?? '' }}
          </li>
        </ul>
      </LedgerSectionState>

      <LedgerDevLoop v-else-if="active === 'devLoop'" :issues="ledger.devLoopIssues.value" :labels="labels" />

      <LedgerSectionState v-else :section="ledger.activity.value" :empty="t('monitoring.agentLedger.empty.activity')" :labels="labels">
        <ul class="m-0 ps-5">
          <li v-for="(e, i) in ledger.activity.value.rows" :key="i">
            <time :datetime="e.at">{{ e.at }}</time> — {{ e.type }} <code v-if="e.scope">{{ e.scope }}</code> {{ e.agent_id ?? '' }}
          </li>
        </ul>
      </LedgerSectionState>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseCard, LedgerSectionState, type LedgerAskOutcome, type LedgerStateLabels } from '@autobot/ui'
import { askHolderToRelease, useSlmAgentLedger } from '@/composables/useSlmAgentLedger'
import LedgerBlindSpots from '@/components/monitoring/ledger/LedgerBlindSpots.vue'
import LedgerDevLoop from '@/components/monitoring/ledger/LedgerDevLoop.vue'

type TabId = 'contention' | 'claims' | 'conflicts' | 'devLoop' | 'activity'
type AskState = LedgerAskOutcome['state'] | 'sending'

const CLAIM_COLUMNS = ['scope', 'agent', 'company', 'mode', 'intent', 'expires', 'renewals'] as const
const ASK_TEXT_KEY = {
  sending: 'sending', sent: 'sent', 'too-soon': 'tooSoon', 'not-found': 'notFound', unavailable: 'unavailable', error: 'error',
} as const

const { t } = useI18n()
const ledger = useSlmAgentLedger()
const active = ref<TabId>('contention')
const tabEls = ref<HTMLButtonElement[]>([])

const labels = computed<LedgerStateLabels>(() => ({
  loading: t('monitoring.agentLedger.state.loading'),
  unavailableTitle: t('monitoring.agentLedger.state.unavailableTitle'),
  unavailableBody: (source: string) => t('monitoring.agentLedger.state.unavailableBody', { source }),
  errorTitle: t('monitoring.agentLedger.state.errorTitle'),
}))

/** Counts appear once a section is readable; an unread section never shows "(0)". */
const tabs = computed(() => {
  const count = (s: { state: string; rows: unknown[] }) => (s.state === 'ready' ? ` (${s.rows.length})` : '')
  const tab = (id: TabId, n = '') => ({ id, label: t(`monitoring.agentLedger.tabs.${id}`) + n })
  return [
    tab('contention', count(ledger.contention.value)),
    tab('claims', count(ledger.claims.value)),
    tab('conflicts', count(ledger.conflicts.value)),
    tab('devLoop'),
    tab('activity'),
  ]
})

function companyOf(companyId: string | null | undefined): string {
  return companyId ?? t('monitoring.agentLedger.installWide')
}

/** One request per holder, its outcome announced; asking never releases anything. */
const asks = reactive<Record<string, AskState>>({})
const askKey = (scope: string, taskId: string) => `${scope}\u0000${taskId}`

async function ask(scope: string, holderTaskId: string): Promise<void> {
  const key = askKey(scope, holderTaskId)
  asks[key] = 'sending'
  asks[key] = (await askHolderToRelease(scope, holderTaskId)).state
}

function askText(state: AskState | undefined): string {
  return state ? t(`monitoring.agentLedger.askState.${ASK_TEXT_KEY[state]}`) : ''
}

/** WAI-ARIA tabs: arrows move between tabs (wrapping), Home/End jump; focus follows selection. */
function onTabKey(event: KeyboardEvent, index: number): void {
  const count = tabs.value.length
  const target = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: count - 1 }[event.key]
  if (target === undefined) return
  event.preventDefault()
  const next = (target + count) % count
  active.value = tabs.value[next].id
  nextTick(() => tabEls.value[next]?.focus())
}

onMounted(() => ledger.refresh())
</script>
