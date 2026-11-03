<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- #20519: shows an agent that cannot run, with the server's reason. Renders nothing when it can. -->
<template>
  <BaseBadge v-if="agent.can_run === false" variant="warning" size="sm" :title="agent.cannot_run_reason ?? undefined">
    {{ $t('llc.agent.cannotRun') }}
  </BaseBadge>
</template>

<script setup lang="ts">
import { BaseBadge } from '@autobot/ui'
import type { LabelledAgent } from '@/composables/llc/agentLabels'

defineProps<{ agent: LabelledAgent }>()
</script>
