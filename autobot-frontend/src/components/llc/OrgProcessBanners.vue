<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #21242: what the process nodes of the org canvas can say when there are none. Three different
  facts that an empty canvas alone would all read as "nothing here":
    - the process-nodes request failed        -> unavailable (a loading problem, not an empty company)
    - the company has no workflows at all     -> nothing attachable
    - workflows exist, none attached to a role -> none attached
  Nothing is said before the process-nodes request has been tried, nor while the workflows list is
  unknown (the attach form states that failure itself): the two empties cannot be told apart then.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { WorkflowsState } from '@/composables/llc/useCompanyWorkflows'

const props = defineProps<{
  failed: boolean
  attempted: boolean
  /** How many process nodes the company has. */
  nodeCount: number
  workflowsState: WorkflowsState
  workflowCount: number
}>()
const { t } = useI18n()

type Banner = 'unavailable' | 'nothingAttachable' | 'noneAttached'
const banner = computed<Banner | null>(() => {
  if (props.failed) return 'unavailable'
  if (!props.attempted || props.nodeCount > 0) return null
  if (props.workflowsState !== 'ready') return null
  return props.workflowCount === 0 ? 'nothingAttachable' : 'noneAttached'
})
const TEXT_KEY: Record<Banner, string> = {
  unavailable: 'llc.orgChart.processNodesUnavailable',
  nothingAttachable: 'llc.orgChart.processNothingAttachable',
  noneAttached: 'llc.orgChart.processNoneAttached',
}
</script>

<template>
  <p
    v-if="banner"
    class="border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-xs text-autobot-text-muted"
    :role="banner === 'unavailable' ? 'alert' : 'status'"
    :data-testid="`canvas-processes-${banner}`"
  >
    {{ t(TEXT_KEY[banner]) }}
  </p>
</template>
