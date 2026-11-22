<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  AgentLedgerView -- Company OS > Overview > Agent ledger (#18391, mockup
  AgentLedger). Read-only: who is working on what in this company, the claims
  they hold, who waits behind them, and what happened recently. Each section
  says "couldn't read the ledger" apart from "nothing here" (AC3).

  The one human action, "Ask holder to release", is the same yield request an
  agent sends (#18599); silence means hold, so its result is "request sent --
  the holder decides", never a release. No force-release and no delete, by design.
-->
<template>
  <div class="flex flex-col gap-4 p-4" data-testid="agent-ledger">
    <header class="flex flex-wrap items-baseline gap-3">
      <h1 class="m-0 text-xl text-autobot-text-primary">{{ t('llc.ledger.title') }}</h1>
      <p class="m-0 text-autobot-text-secondary">{{ t('llc.ledger.subtitle') }}</p>
      <button type="button" class="ms-auto px-3 py-1 rounded border border-autobot-border text-autobot-text-primary" @click="ledger.refresh()">{{ t('common.refresh') }}</button>
    </header>

    <div class="flex gap-2 border-b border-autobot-border" role="tablist" :aria-label="t('llc.ledger.tabsAria')">
      <button
        v-for="(tab, i) in tabs" :id="`ledger-tab-${tab.id}`" :key="tab.id" ref="tabEls" type="button" role="tab"
        :aria-controls="`ledger-panel-${tab.id}`" :tabindex="active === tab.id ? 0 : -1" @keydown="onTabKey($event, i)"
        class="px-3 py-2 text-autobot-text-secondary aria-selected:text-autobot-text-primary aria-selected:border-b-2 aria-selected:border-autobot-primary"
        :aria-selected="active === tab.id" :data-testid="`ledger-tab-${tab.id}`" @click="active = tab.id"
      >{{ tab.label }}</button>
    </div>

    <section v-if="active === 'now'" id="ledger-panel-now" role="tabpanel" aria-labelledby="ledger-tab-now" tabindex="0">
      <LedgerSectionState :section="ledger.presence.value" :empty="t('llc.ledger.empty.presence')">
        <BaseTable :columns="presenceColumns" :rows="presenceRows" size="compact" :aria-label="t('llc.ledger.col.agent')">
          <template #cell-task="{ row }">
            <span data-testid="ledger-current-task" class="inline-block max-w-xs truncate align-bottom" :title="row.task ? String(row.task) : undefined">{{ row.task }}</span>
          </template>
        </BaseTable>
      </LedgerSectionState>
      <h2 class="mt-3 mb-0 text-base text-autobot-text-primary">{{ t('llc.ledger.peerMessages') }}</h2>
      <LedgerSectionState :section="ledger.peerMessages.value" :empty="t('llc.ledger.empty.peerMessages')">
        <ul class="m-0 ps-4">
          <li v-for="m in ledger.peerMessages.value.rows" :key="`${m.recipient_kind}:${m.recipient_name}`">
            {{ t('llc.ledger.pendingFor', { name: m.recipient_name, n: m.pending }) }}
            <span class="text-autobot-text-secondary">{{ t('llc.ledger.sentBy', { names: m.senders.join(', ') }) }}</span>
          </li>
        </ul>
      </LedgerSectionState>
      <h2 class="mt-3 mb-0 text-base text-autobot-text-primary">{{ t('llc.ledger.idleSubscribers') }}</h2>
      <LedgerSectionState :section="ledger.idleSubscribers.value" :empty="t('llc.ledger.empty.idleSubscribers')">
        <ul class="m-0 ps-4">
          <li v-for="s in ledger.idleSubscribers.value.rows" :key="`${s.subscriber}:${s.target_name}`">
            {{ t('llc.ledger.waitsForIdle', { who: s.subscriber, target: s.target_name }) }}
          </li>
        </ul>
      </LedgerSectionState>
    </section>

    <section v-else-if="active === 'claims'" id="ledger-panel-claims" role="tabpanel" aria-labelledby="ledger-tab-claims" tabindex="0">
      <LedgerSectionState :section="ledger.claims.value" :empty="t('llc.ledger.empty.claims')">
        <BaseTable :columns="claimColumns" :rows="claimRows" size="compact" data-testid="ledger-claims" :aria-label="t('llc.ledger.col.scope')" />
      </LedgerSectionState>
    </section>

    <section v-else-if="active === 'contention'" id="ledger-panel-contention" role="tabpanel" aria-labelledby="ledger-tab-contention" tabindex="0">
      <p class="m-0 text-autobot-text-secondary">{{ t('llc.ledger.silenceMeansHold') }}</p>
      <LedgerSectionState :section="ledger.contention.value" :empty="t('llc.ledger.empty.contention')">
        <article v-for="(s, i) in ledger.contention.value.rows" :key="s.scope" class="p-3 rounded border border-autobot-border" data-testid="ledger-scope">
          <h3 class="m-0 mb-2 text-sm"><code>{{ s.scope }}</code></h3>
          <div v-for="(h, hi) in s.holders" :key="h.task_id" class="flex flex-wrap items-center gap-2">
            <span>{{ t('llc.ledger.heldBy', { agent: h.agent_id }) }}</span>
            <button type="button" class="ms-auto px-3 py-1 rounded border border-autobot-border text-autobot-text-primary"
              data-testid="ledger-ask" :aria-label="t('llc.ledger.askAria', { scope: s.scope })"
              :aria-describedby="`ledger-ask-status-${i}-${hi}`" :disabled="asks[askKey(s.scope, h.task_id)] === 'sending'"
              @click="ask(s.scope, h.task_id)"
            >{{ t('llc.ledger.ask') }}</button>
            <span :id="`ledger-ask-status-${i}-${hi}`" class="w-full text-sm text-autobot-text-secondary" role="status" data-testid="ledger-ask-status">
              {{ askText(asks[askKey(s.scope, h.task_id)]) }}
            </span>
          </div>
          <ol :aria-label="t('llc.ledger.waitlistAria')">
            <li v-for="w in s.waiters" :key="w.task_id">{{ w.agent_id }} — {{ w.intent }}</li>
          </ol>
        </article>
      </LedgerSectionState>
    </section>

    <section v-else id="ledger-panel-activity" role="tabpanel" aria-labelledby="ledger-tab-activity" tabindex="0">
      <h2 class="mt-3 mb-0 text-base text-autobot-text-primary">{{ t('llc.ledger.conflicts') }}</h2>
      <LedgerSectionState :section="ledger.conflicts.value" :empty="t('llc.ledger.empty.conflicts')">
        <ul class="m-0 ps-4">
          <li v-for="c in ledger.conflicts.value.rows" :key="`${c.at}:${c.kind}:${c.scope}`">
            {{ c.at }} — {{ t(`llc.ledger.conflict.${c.kind}`) }} <code v-if="c.scope">{{ c.scope }}</code>
          </li>
        </ul>
      </LedgerSectionState>
      <h2 class="mt-3 mb-0 text-base text-autobot-text-primary">{{ t('llc.ledger.recent') }}</h2>
      <LedgerSectionState :section="ledger.activity.value" :empty="t('llc.ledger.empty.activity')">
        <ul class="m-0 ps-4">
          <li v-for="(e, i) in ledger.activity.value.rows" :key="i">{{ e.at }} — {{ e.type }} <code v-if="e.scope">{{ e.scope }}</code> {{ e.agent_id ?? '' }}</li>
        </ul>
      </LedgerSectionState>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseTable, type BaseTableColumn } from '@autobot/ui'
import { askHolderToRelease, useAgentLedger, type AskOutcome } from '@/composables/useAgentLedger'
import { useUiMode } from '@/composables/useUiMode'
import LedgerSectionState from '@/components/llc/ledger/LedgerSectionState.vue'

type TabId = 'now' | 'claims' | 'contention' | 'activity'

const { t } = useI18n()
const { uiMode } = useUiMode()
const ledger = useAgentLedger()

// #17562: both ledger tables are the kit table. Row keys are the ones the old v-for used.
const presenceColumns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t('llc.ledger.col.agent') },
  { key: 'kind', label: t('llc.ledger.col.kind') },
  { key: 'status', label: t('llc.ledger.col.status') },
  { key: 'task', label: t('llc.ledger.col.task') },
  { key: 'detail', label: t('llc.ledger.col.detail') },
])
const presenceRows = computed(() =>
  ledger.presence.value.rows.map((a) => ({
    id: `${a.kind}:${a.name}`,
    name: a.name,
    kind: a.kind,
    status: a.busy ? t('llc.ledger.busy') : t('llc.ledger.idle'),
    task: a.current_task?.title ?? '',
    detail: a.detail ?? '',
  })),
)
const claimColumns = computed<BaseTableColumn[]>(() => [
  { key: 'scope', label: t('llc.ledger.col.scope'), monospace: true },
  { key: 'agent_id', label: t('llc.ledger.col.agent') },
  { key: 'mode', label: t('llc.ledger.col.mode') },
  { key: 'intent', label: t('llc.ledger.col.intent') },
  { key: 'expires_at', label: t('llc.ledger.col.expires') },
  { key: 'renewals', label: t('llc.ledger.col.renewals'), numeric: true },
])
const claimRows = computed(() => ledger.claims.value.rows.map((c) => ({ ...c, id: `${c.scope}:${c.task_id}` })))
const active = ref<TabId>('now')
const tabEls = ref<HTMLButtonElement[]>([])

/** #18391 AC4: one request per holder, its outcome announced; asking never releases anything. */
const asks = reactive<Record<string, AskOutcome['state'] | 'sending'>>({})
const askKey = (scope: string, taskId: string) => `${scope}\u0000${taskId}`

async function ask(scope: string, holderTaskId: string): Promise<void> {
  const key = askKey(scope, holderTaskId)
  asks[key] = 'sending'
  asks[key] = (await askHolderToRelease(scope, holderTaskId)).state
}

const ASK_TEXT_KEY = {
  sending: 'sending', sent: 'sent', 'too-soon': 'tooSoon', 'not-found': 'notFound', unavailable: 'unavailable', error: 'error',
} as const

function askText(state: AskOutcome['state'] | 'sending' | undefined): string {
  return state ? t(`llc.ledger.askState.${ASK_TEXT_KEY[state]}`) : ''
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

/** Activity is a Full-mode tab (mockup: `adv`); counts appear once a section is readable. */
const tabs = computed(() => {
  const count = (s: { state: string; rows: unknown[] }) => (s.state === 'ready' ? ` (${s.rows.length})` : '')
  const all: { id: TabId; label: string }[] = [
    { id: 'now', label: t('llc.ledger.tabs.now') },
    { id: 'claims', label: t('llc.ledger.tabs.claims') + count(ledger.claims.value) },
    { id: 'contention', label: t('llc.ledger.tabs.contention') + count(ledger.contention.value) },
    { id: 'activity', label: t('llc.ledger.tabs.activity') },
  ]
  return uiMode.value === 'full' ? all : all.filter((x) => x.id !== 'activity')
})

watch(uiMode, (mode) => {
  if (mode !== 'full' && active.value === 'activity') active.value = 'now'
})

onMounted(() => ledger.refresh())
</script>
