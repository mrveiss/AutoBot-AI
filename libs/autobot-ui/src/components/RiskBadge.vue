<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  RiskBadge — the one badge for a risk tier (#13422). Both apps used to restyle
  low/medium/high/critical per view (`.risk-badge`, `.risk-pill`, a local
  `levelClass()`), so "high" could look different on two screens.

  `tier` is the four-rung RiskTier ladder the backend sends as `risk_tier`
  (autobot_shared/risk_tier.py); the kit holds no text, so the translated tier
  name comes in as `label`. The label is always shown, so a tier is never told
  by colour alone. Colours and label ink are the --aui-risk-* / --aui-risk-*-ink tokens, which alias the theme's
  status colours. `critical` is the outline tone with a heavier border and
  weight, so it differs from `high` in more than hue.

  Contrast: the label ink is 40% tier colour, 60% theme text, over the tier
  colour at 15% on the surface. That holds >= 4.5:1 in dark, light, contrast,
  mono and both ember schemes (the 70% mix BaseBadge uses fell to 3.2-3.8:1 for
  low/medium in light, contrast, mono and ember-light). Critical is the outline
  tone, not a solid fill, so it differs from `high` in more than hue. A solid
  error fill would paint --color-error-solid (white label ink 4.5:1 or better
  in every theme, #19872), never --color-error, which is 3.76:1 under white.
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
const tone = computed(() => (props.tier === 'critical' ? 'outline' : 'subtle'))
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
.aui-badge.aui-risk-badge--critical {
  border-width: 2px;
  font-weight: var(--aui-font-weight-semibold);
}
/* Two classes, so the tier tokens win over BaseBadge's variant colours on the same element. */
.aui-badge.aui-risk-badge--low {
  --aui-badge-color: var(--aui-risk-low);
  --aui-badge-contrast: var(--aui-risk-low-contrast);
  color: var(--aui-risk-low-ink);
}
.aui-badge.aui-risk-badge--medium {
  --aui-badge-color: var(--aui-risk-medium);
  --aui-badge-contrast: var(--aui-risk-medium-contrast);
  color: var(--aui-risk-medium-ink);
}
.aui-badge.aui-risk-badge--high {
  --aui-badge-color: var(--aui-risk-high);
  --aui-badge-contrast: var(--aui-risk-high-contrast);
  color: var(--aui-risk-high-ink);
}
.aui-badge.aui-risk-badge--critical {
  --aui-badge-color: var(--aui-risk-critical);
  --aui-badge-contrast: var(--aui-risk-critical-contrast);
  color: var(--aui-risk-critical-ink);
}
</style>
