<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  LedgerSectionState (#18391 AC3): the Company OS ledger's wording for the kit's
  one section-state block (@autobot/ui), which says "couldn't read the ledger"
  (a typed 503, naming the store) apart from "no claims" (an empty list that was
  actually read). The default slot renders only when the section has rows.
-->
<template>
  <KitLedgerSectionState :section="section" :empty="empty" :labels="labels">
    <slot />
  </KitLedgerSectionState>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LedgerSectionState as KitLedgerSectionState, type LedgerSection, type LedgerStateLabels } from '@autobot/ui'

defineProps<{ section: LedgerSection<unknown>; empty: string }>()
const { t } = useI18n()

const labels = computed<LedgerStateLabels>(() => ({
  loading: t('llc.ledger.state.loading'),
  unavailableTitle: t('llc.ledger.state.unavailableTitle'),
  unavailableBody: (source: string) => t('llc.ledger.state.unavailableBody', { source }),
  errorTitle: t('llc.ledger.state.errorTitle'),
}))
</script>
