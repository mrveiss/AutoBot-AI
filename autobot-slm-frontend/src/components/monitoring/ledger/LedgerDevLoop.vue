<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  LedgerDevLoop (#18391 AC2): the dev loop's action history for one issue,
  newest first, including refused and skipped attempts. The issue list comes
  from the ledger; one issue's actions are read when it is chosen.
-->
<template>
  <div class="flex flex-col gap-3">
    <LedgerSectionState :section="issues" :empty="t('monitoring.agentLedger.empty.devLoop')" :labels="labels">
      <label class="flex items-center gap-2">
        <span>{{ t('monitoring.agentLedger.devLoop.issue') }}</span>
        <select v-model="issue" class="px-2 py-1 rounded border border-(--aui-color-border) bg-(--aui-color-surface)" data-testid="slm-ledger-devloop-issue">
          <option :value="null" disabled>{{ t('monitoring.agentLedger.devLoop.choose') }}</option>
          <option v-for="n in issues.rows" :key="n" :value="n">#{{ n }}</option>
        </select>
      </label>
    </LedgerSectionState>
    <LedgerSectionState v-if="history" :section="history" :empty="t('monitoring.agentLedger.empty.devLoopActions')" :labels="labels">
      <table class="w-full border-collapse [&_th]:p-2 [&_td]:p-2 [&_th]:text-start [&_tr]:border-b [&_tr]:border-(--aui-color-border)" data-testid="slm-ledger-devloop-actions">
        <thead><tr><th v-for="c in COLUMNS" :key="c">{{ t(`monitoring.agentLedger.devLoop.col.${c}`) }}</th></tr></thead>
        <tbody>
          <tr v-for="(a, i) in history.rows" :key="`${a.at}:${i}`">
            <td><time :datetime="a.at">{{ a.at }}</time></td><td>{{ a.intent }}</td><td>{{ a.outcome }}</td>
            <td>{{ a.estimated_tokens }}</td><td>{{ a.reason }}</td>
          </tr>
        </tbody>
      </table>
    </LedgerSectionState>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LedgerSectionState, loadingLedgerSection, type LedgerSection, type LedgerStateLabels } from '@autobot/ui'
import { readDevLoopHistory, type DevLoopActionRow } from '@/composables/useSlmAgentLedger'

defineProps<{ issues: LedgerSection<number>; labels: LedgerStateLabels }>()
const { t } = useI18n()

const COLUMNS = ['at', 'intent', 'outcome', 'tokens', 'reason'] as const
const issue = ref<number | null>(null)
const history = ref<LedgerSection<DevLoopActionRow> | null>(null)

watch(issue, async (n) => {
  if (n === null) return
  history.value = loadingLedgerSection()
  const read = await readDevLoopHistory(n)
  if (issue.value === n) history.value = read
})
</script>
