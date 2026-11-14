<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  #17982: a cached result older than the source's last sync is shown, not hidden, and this says
  it predates that sync. `kind` names which result the panel shows. Renders nothing for a
  result that is current, or one loaded by a full scan.
-->
<template>
  <BaseAlert
    v-if="stale?.flags[kind]"
    variant="warning"
    size="compact"
    bordered
    :message="t('analytics.codebase.staleResult.message')"
    data-testid="stale-result-notice"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BaseAlert } from '@autobot/ui'
import { injectStaleResults, type StaleResultKind } from '@/composables/analytics/useStaleResults'

defineProps<{ kind: StaleResultKind }>()

const { t } = useI18n()
const stale = injectStaleResults()
</script>
