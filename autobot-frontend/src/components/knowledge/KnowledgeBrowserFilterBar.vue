<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeBrowserFilterBar — the row above the document tree (#18244): the one "Filtering by"
  chip (the category cards and the chip are the only category controls) and the Status button
  that refreshes every document's vectorization status.
-->
<template>
  <div class="kb-filter-bar">
    <BaseTooltip v-if="filterLabel" :text="$t('knowledge.browserFilter.removeFilter')" placement="top">
      <template #default="{ describedby }">
        <BaseButton
          variant="outline"
          size="sm"
          class="kb-filter-chip"
          :aria-label="$t('knowledge.browserFilter.removeFilterNamed', { category: filterLabel })"
          :aria-describedby="describedby"
          @click="$emit('clear-filter')"
        >
          {{ $t('knowledge.browser.filteringBy', { category: filterLabel }) }}
          <Icon name="times" aria-hidden="true" />
        </BaseButton>
      </template>
    </BaseTooltip>
    <BaseTooltip :text="$t('knowledge.browser.refreshVectorizationStatus')" placement="top">
      <template #default="{ describedby }">
        <BaseButton
          variant="outline"
          size="sm"
          class="kb-filter-status"
          :loading="refreshing"
          :disabled="refreshing"
          :aria-describedby="describedby"
          @click="$emit('refresh')"
        >
          {{ $t('knowledge.browser.status') }}
        </BaseButton>
      </template>
    </BaseTooltip>
  </div>
</template>

<script setup lang="ts">
import { BaseButton, BaseTooltip } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

defineProps<{
  /** Display name of the active category filter, or null when none. */
  filterLabel: string | null
  refreshing: boolean
}>()

defineEmits<{
  'clear-filter': []
  refresh: []
}>()
</script>

<style scoped>
.kb-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.kb-filter-chip {
  background: var(--surface2);
}

.kb-filter-status {
  margin-inline-start: auto;
}
</style>
