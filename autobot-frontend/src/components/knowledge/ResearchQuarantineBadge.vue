<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ResearchQuarantineBadge — marks a knowledge row the server flagged as research-quarantined
  (#19163). The flag is the server's: admin reads of the quarantine are audited and labelled,
  and this surfaces the label so an admin never mistakes an unverified research fact for a trusted one.
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BaseBadge } from '@autobot/ui'

const { t } = useI18n()
</script>

<template>
  <BaseBadge variant="warning" size="xs" :label="t('knowledge.chroma.quarantined')" />
</template>
