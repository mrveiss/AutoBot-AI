<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  GH#12741: analytics panels cap result lists. A count with nothing to press ("Showing 30 of
  1947") is a label, not a control, so this is the ONE notice every capped list uses and it has
  two honest modes:

  - Default: the panel holds the whole list. A "Show N more" button emits `show-more`; the
    panel grows its visible limit (`useShowMore` from @autobot/ui), so `shown` rises and the
    count stays accurate until everything is visible.
  - `server-limited`: the SERVER capped the list, so the missing rows are not in the payload and
    no amount of expanding reaches them. There is no button; it says so instead of offering one
    that stops short.

  Renders nothing when the list is complete.
-->
<template>
  <div v-if="isTruncated" class="truncation-notice" role="status">
    <span v-if="serverLimited" data-testid="truncation-server-limited">
      {{ $t('analytics.truncation.serverLimited', counts) }}
    </span>
    <template v-else>
      <span data-testid="truncation-count">{{ $t('analytics.truncation.showingOf', counts) }}</span>
      <BaseButton
        variant="link"
        size="sm"
        data-testid="truncation-show-more"
        @click="emit('show-more')"
      >
        {{ $t('analytics.truncation.showMore', { count: nextCount.toLocaleString() }) }}
      </BaseButton>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BaseButton } from '@autobot/ui'

const props = withDefaults(defineProps<{
  /** How many items the panel actually rendered. */
  shown: number
  /** How many exist in total before truncation. */
  total: number
  /** How many more one press reveals (the panel's page size). */
  step?: number
  /** The server capped this list; the rest cannot be loaded here, so no button. */
  serverLimited?: boolean
}>(), { step: 20, serverLimited: false })

const emit = defineEmits<{ 'show-more': [] }>()

const isTruncated = computed(() => props.total > props.shown)
// Locale-formatted, so "1947" reads "1,947" as the section counts it did before.
const counts = computed(() => ({ shown: props.shown.toLocaleString(), total: props.total.toLocaleString() }))
const nextCount = computed(() => Math.min(props.step, props.total - props.shown))
</script>

<style scoped>
.truncation-notice {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  margin: var(--space-2, 0.5rem) 0 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
}
</style>
