<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  GH#12741: analytics panels cap result lists with hardcoded slice(0, N) and
  rendered nothing to say so. If a scan found 100 orphaned endpoints the panel
  showed 30 and silently dropped 70 — the user had no signal that results were
  cut. This makes the truncation visible.

  Renders nothing when the list is complete, so panels showing everything stay
  uncluttered.
-->
<template>
  <p v-if="isTruncated" class="truncation-notice" role="status">
    {{ $t('analytics.truncation.showingOf', { shown, total }) }}
  </p>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  /** How many items the panel actually rendered. */
  shown: number
  /** How many exist in total before truncation. */
  total: number
}>()

const isTruncated = computed(() => props.total > props.shown)
</script>

<style scoped>
.truncation-notice {
  margin: var(--space-2, 0.5rem) 0 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
}
</style>
