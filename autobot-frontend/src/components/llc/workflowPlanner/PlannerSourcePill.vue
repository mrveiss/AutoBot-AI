<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerSourcePill (#19938): where a measured number came from. "You said" is the owner's own
  estimate; email and calendar are numbers checked against timestamps. The pill never shows a
  checked state for an estimate, so a guess cannot pass for evidence.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge } from '@autobot/ui'
import type { MetricSource } from '@/composables/llc/workflowPlanTypes'

const props = defineProps<{ source: MetricSource }>()
const { t } = useI18n()

const checked = computed(() => props.source !== 'self_reported')
</script>

<template>
  <BaseBadge
    :variant="checked ? 'success' : 'neutral'"
    tone="subtle"
    size="sm"
    :data-testid="`source-pill-${source}`"
    :label="t(`llc.workflowPlanner.source.${source}`)"
  />
</template>
