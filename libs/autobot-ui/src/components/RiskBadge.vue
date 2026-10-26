<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  RiskBadge — the one badge for a risk tier (#13422). Both apps used to restyle
  low/medium/high/critical per view (`.risk-badge`, `.risk-pill`, a local
  `levelClass()`), so "high" could look different on two screens.

  `tier` is the four-rung RiskTier ladder the backend sends as `risk_tier`
  (autobot_shared/risk_tier.py); the kit holds no text, so the translated tier
  name comes in as `label`. The label is always shown, so a tier is never told
  by colour alone. Colours are the --aui-risk-* tokens, which alias the theme's
  status colours; `critical` is the solid fill, so it differs from `high` in
  more than hue.
-->
<script setup lang="ts">
import { computed } from 'vue'
import BaseBadge from './BaseBadge.vue'
import type { BadgeSize, BadgeVariant } from './BaseBadge.vue'
import type { RiskTier } from '../types/riskTier'

const props = withDefaults(
  defineProps<{
    tier: RiskTier
    /** The translated tier name; the kit ships no strings. */
    label: string
    size?: BadgeSize
  }>(),
  { size: 'sm' },
)

const VARIANT: Record<RiskTier, BadgeVariant> = {
  low: 'success',
  medium: 'warning',
  high: 'error',
  critical: 'error',
}

const variant = computed(() => VARIANT[props.tier])
const tone = computed(() => (props.tier === 'critical' ? 'solid' : 'subtle'))
</script>

<template>
  <BaseBadge
    :class="['aui-risk-badge', `aui-risk-badge--${tier}`]"
    :variant="variant"
    :tone="tone"
    :size="size"
    :label="label"
    :data-risk-tier="tier"
  />
</template>

<style scoped>
/* Two classes, so the tier tokens win over BaseBadge's variant colours on the same element. */
.aui-badge.aui-risk-badge--low {
  --aui-badge-color: var(--aui-risk-low);
  --aui-badge-contrast: var(--aui-risk-low-contrast);
}
.aui-badge.aui-risk-badge--medium {
  --aui-badge-color: var(--aui-risk-medium);
  --aui-badge-contrast: var(--aui-risk-medium-contrast);
}
.aui-badge.aui-risk-badge--high {
  --aui-badge-color: var(--aui-risk-high);
  --aui-badge-contrast: var(--aui-risk-high-contrast);
}
.aui-badge.aui-risk-badge--critical {
  --aui-badge-color: var(--aui-risk-critical);
  --aui-badge-contrast: var(--aui-risk-critical-contrast);
}
</style>
