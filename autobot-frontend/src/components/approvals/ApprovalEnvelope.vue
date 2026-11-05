<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ApprovalEnvelope — the one frame for "a person must decide" (#13421). Every approval
  surface shares the title, the risk tier (RiskBadge, the single vocabulary of #13422) and
  the approve / reject pair; what is being approved (a workflow plan, an experiment, a
  command, a capability) stays bespoke and goes in the default slot.

  The envelope decides nothing: it emits `approve` / `reject` and the owner calls its own
  API. `deciding` disables both buttons while that call is in flight, so a decision cannot
  be sent twice. `approveLabel` / `rejectLabel` default to the generic verbs; a surface
  whose action is more specific ("Approve and run") passes its own.
-->
<script setup lang="ts">
import { BaseButton, BaseCard, RiskBadge } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import type { RiskTier } from '@/types/riskTier'

withDefaults(
  defineProps<{
    title: string
    /** The record's risk tier, when it carries one as a whole. */
    risk?: RiskTier
    icon?: IconName
    approveLabel?: string
    rejectLabel?: string
    deciding?: boolean
  }>(),
  {
    risk: undefined,
    icon: undefined,
    approveLabel: undefined,
    rejectLabel: undefined,
    deciding: false,
  },
)

defineEmits<{
  approve: []
  reject: []
}>()

const { t } = useI18n()
</script>

<template>
  <BaseCard variant="bordered" :title="title">
    <template v-if="icon || risk" #actions>
      <Icon v-if="icon" :name="icon" />
      <RiskBadge v-if="risk" :tier="risk" :label="t(`common.riskTier.${risk}`)" />
    </template>
    <slot />
    <template #footer>
      <div class="flex justify-end gap-3">
        <BaseButton variant="success" size="sm" :disabled="deciding" @click="$emit('approve')">
          {{ approveLabel ?? t('approvals.envelope.approve') }}
        </BaseButton>
        <BaseButton variant="error" size="sm" :disabled="deciding" @click="$emit('reject')">
          {{ rejectLabel ?? t('approvals.envelope.reject') }}
        </BaseButton>
      </div>
    </template>
  </BaseCard>
</template>
