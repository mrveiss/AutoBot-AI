<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BrandMark — the AutoBot robot-head mark on its brand tile (#18240, #15469).
  The one canonical logo for both apps; replaces the hand-made "AB" / "S"
  tiles and the Vue-scaffold logo. Token-only: tile and stroke come from
  --aui-brand-bg / --aui-brand-fg. The kit holds no text: pass `label` to
  expose the mark to assistive tech (role="img"), omit it for a decorative
  mark that sits next to a visible name. Geometry is mirrored by
  src/assets/brand/mark.svg (standalone, for favicons).
-->
<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** Tile edge in px. */
    size?: number
    /** Accessible name — the app's translated string. Omit for decorative. */
    label?: string
  }>(),
  { size: 40, label: undefined },
)

const tileStyle = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
</script>

<template>
  <span
    class="aui-brand-mark"
    :style="tileStyle"
    :role="label ? 'img' : undefined"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
  >
    <svg viewBox="0 0 48 48" width="60%" height="60%" aria-hidden="true" focusable="false">
      <rect x="10" y="16" width="28" height="22" rx="5" />
      <circle cx="19" cy="27" r="3" class="aui-brand-mark__eye" />
      <circle cx="29" cy="27" r="3" class="aui-brand-mark__eye" />
      <path d="M24 16v-6" />
      <circle cx="24" cy="8" r="3" />
    </svg>
  </span>
</template>

<style scoped>
.aui-brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  border-radius: var(--aui-radius-md);
  background: var(--aui-brand-bg);
}

.aui-brand-mark svg {
  fill: none;
  stroke: var(--aui-brand-fg);
  stroke-width: 2.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.aui-brand-mark .aui-brand-mark__eye {
  fill: var(--aui-brand-bg);
}
</style>
