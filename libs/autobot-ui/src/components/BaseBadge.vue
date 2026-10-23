<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseBadge — small status/label pill. Token-only styling; used by both apps
  for statuses, counts, and tags. See BaseButton.vue for the kit rules.

  The one badge for both apps (#14776): the main app's local fork is retired into
  this. `tone` picks the fill -- `subtle` (a tint with coloured text; the
  default, as the design system's badge matrix defines it), `solid` or
  `outline`. The kit holds no text, so a removable badge takes its translated
  `removeLabel` from the app.
-->
<script setup lang="ts">
import type { SemanticVariant } from '../types/semantic'

// BadgeVariant is the canonical semantic vocabulary (#10885); kept as an alias
// so existing `BadgeVariant` imports keep working without duplicating the union.
export type BadgeVariant = SemanticVariant
export type BadgeSize = 'xs' | 'sm' | 'md' | 'lg'
export type BadgeTone = 'solid' | 'subtle' | 'outline'

withDefaults(
  defineProps<{
    variant?: BadgeVariant
    size?: BadgeSize
    tone?: BadgeTone
    /** Text when no default slot is given. */
    label?: string
    /** Pill (full radius) by default; false gives the small radius. */
    rounded?: boolean
    monospace?: boolean
    /** Shows a remove button that emits `remove`. Pass `removeLabel` for its accessible name. */
    removable?: boolean
    removeLabel?: string
  }>(),
  {
    variant: 'neutral',
    size: 'md',
    tone: 'subtle',
    label: undefined,
    rounded: true,
    monospace: false,
    removable: false,
    removeLabel: undefined,
  },
)

const emit = defineEmits<{ remove: [] }>()

function onRemove(event: MouseEvent): void {
  event.stopPropagation()
  emit('remove')
}
</script>

<template>
  <span
    :class="[
      'aui-badge',
      `aui-badge--${variant}`,
      `aui-badge--${size}`,
      `aui-badge--${tone}`,
      { 'aui-badge--square': !rounded, 'aui-badge--mono': monospace },
    ]"
  >
    <slot name="icon" />
    <slot>{{ label }}</slot>
    <button
      v-if="removable"
      type="button"
      class="aui-badge__remove"
      :aria-label="removeLabel"
      @click="onRemove"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  </span>
</template>

<style scoped>
.aui-badge {
  --aui-badge-color: var(--aui-color-text-muted);
  --aui-badge-contrast: var(--aui-color-text);
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-1);
  border-radius: var(--aui-radius-full);
  font-family: var(--aui-font-sans);
  font-weight: var(--aui-font-weight-medium);
  line-height: 1;
  white-space: nowrap;
}

.aui-badge--square {
  border-radius: var(--aui-radius-sm);
}
.aui-badge--mono {
  font-family: var(--aui-font-mono);
}

.aui-badge--xs {
  padding: 0 var(--aui-space-1);
  font-size: var(--aui-text-xs);
}
.aui-badge--sm {
  padding: 0.125rem var(--aui-space-2);
  font-size: var(--aui-text-xs);
}
.aui-badge--md {
  padding: var(--aui-space-1) var(--aui-space-3);
  font-size: var(--aui-text-sm);
}
.aui-badge--lg {
  padding: var(--aui-space-2) var(--aui-space-4);
  font-size: var(--aui-text-base);
}

/* Each variant names its colour once; the tones below decide how it is used. */
.aui-badge--primary {
  --aui-badge-color: var(--aui-color-primary);
  --aui-badge-contrast: var(--aui-color-primary-contrast);
}
.aui-badge--success {
  --aui-badge-color: var(--aui-color-success);
  --aui-badge-contrast: var(--aui-color-success-contrast);
}
.aui-badge--warning {
  --aui-badge-color: var(--aui-color-warning);
  --aui-badge-contrast: var(--aui-color-warning-contrast);
}
.aui-badge--error {
  --aui-badge-color: var(--aui-color-error);
  --aui-badge-contrast: var(--aui-color-error-contrast);
}
.aui-badge--info {
  --aui-badge-color: var(--aui-color-info);
  --aui-badge-contrast: var(--aui-color-info-contrast);
}

.aui-badge--solid {
  background-color: var(--aui-badge-color);
  color: var(--aui-badge-contrast);
}
.aui-badge--solid.aui-badge--neutral {
  background-color: var(--aui-color-surface-sunken);
  color: var(--aui-color-text-muted);
}
/* Only the subtle and outline tones draw a border: solid stays border-less, as it always was. */
.aui-badge--subtle,
.aui-badge--outline {
  border: 1px solid transparent;
}
.aui-badge--subtle {
  background-color: color-mix(in srgb, var(--aui-badge-color) 15%, transparent);
  color: color-mix(in srgb, var(--aui-badge-color) 70%, var(--aui-color-text));
}
.aui-badge--subtle.aui-badge--neutral {
  background-color: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
  border-color: var(--aui-color-border);
}
.aui-badge--outline {
  background-color: transparent;
  color: color-mix(in srgb, var(--aui-badge-color) 70%, var(--aui-color-text));
  border-color: var(--aui-badge-color);
}
.aui-badge--outline.aui-badge--neutral {
  color: var(--aui-color-text);
  border-color: var(--aui-color-border);
}

.aui-badge__remove {
  display: inline-flex;
  margin-inline-start: var(--aui-space-1);
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  opacity: 0.7;
}
.aui-badge__remove:hover,
.aui-badge__remove:focus-visible {
  opacity: 1;
}
.aui-badge__remove svg {
  width: 0.75em;
  height: 0.75em;
}
</style>
