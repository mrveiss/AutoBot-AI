<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VectorizationStatusBadge — whether a knowledge document is searchable yet (#18244):
  Vectorized (ok), Pending (warn), Failed (bad), Unknown (idle), on the kit's one badge, with a
  tooltip that says what the state means. The icon-only form (`showLabel` off) keeps its name
  in an accessible label.
-->
<template>
  <BaseTooltip :text="tooltipText" placement="left">
    <template #default="{ describedby }">
      <BaseBadge
        class="vectorization-badge cursor-default gap-1"
        :class="`status-${status}`"
        :variant="VARIANT[status] ?? 'neutral'"
        :size="compact ? 'xs' : 'sm'"
        tabindex="0"
        :aria-describedby="describedby"
      >
        <Icon :name="ICON[status] ?? 'question-circle'" aria-hidden="true" />
        <span v-if="showLabel" class="badge-label">{{ labelText }}</span>
        <span v-else class="sr-only">{{ labelText }}</span>
      </BaseBadge>
    </template>
  </BaseTooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseTooltip, type BadgeVariant } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'

const props = withDefaults(
  defineProps<{
    status: 'vectorized' | 'pending' | 'failed' | 'unknown'
    showLabel?: boolean
    compact?: boolean
  }>(),
  { showLabel: false, compact: false },
)

const { t } = useI18n()

const VARIANT: Record<string, BadgeVariant> = {
  vectorized: 'success',
  pending: 'warning',
  failed: 'error',
  unknown: 'neutral',
}
const ICON: Record<string, IconName> = {
  vectorized: 'check-circle',
  pending: 'spinner',
  failed: 'times-circle',
  unknown: 'question-circle',
}

const labelText = computed(() => {
  switch (props.status) {
    case 'vectorized': return t('knowledge.vectorization.statusVectorized')
    case 'pending': return t('knowledge.vectorization.statusPending')
    case 'failed': return t('knowledge.vectorization.statusFailed')
    default: return t('knowledge.vectorization.statusUnknown')
  }
})

const tooltipText = computed(() => {
  switch (props.status) {
    case 'vectorized': return t('knowledge.vectorization.tooltipVectorized')
    case 'pending': return t('knowledge.vectorization.tooltipPending')
    case 'failed': return t('knowledge.vectorization.tooltipFailed')
    default: return t('knowledge.vectorization.tooltipUnknown')
  }
})
</script>
