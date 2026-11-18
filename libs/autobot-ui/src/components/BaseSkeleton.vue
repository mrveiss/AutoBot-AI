<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseSkeleton — the one shimmering placeholder for content that has not arrived
  yet (#19906). Shape it with `shape`, `width`, `height`; `lines` stacks several
  text-line bars (the last one shorter). Token-only styling. Decorative: the
  loading region should carry `aria-busy` and a label of its own.
-->
<script setup lang="ts">
export type SkeletonShape = 'line' | 'block' | 'circle'

withDefaults(
  defineProps<{ shape?: SkeletonShape; lines?: number; width?: string; height?: string }>(),
  { shape: 'line', lines: 1 },
)
</script>

<template>
  <span class="aui-skeleton-group" aria-hidden="true">
    <span
      v-for="n in lines"
      :key="n"
      class="aui-skeleton"
      :class="`aui-skeleton--${shape}`"
      :style="{ width: lines > 1 && n === lines ? '60%' : width, height: height }"
    />
  </span>
</template>

<style scoped>
.aui-skeleton-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
}
.aui-skeleton {
  display: block;
  position: relative;
  overflow: hidden;
  background: var(--aui-color-surface-sunken);
}
.aui-skeleton--line { height: 1rem; border-radius: var(--aui-radius-sm); }
.aui-skeleton--block { height: 4rem; border-radius: var(--aui-radius-md); }
.aui-skeleton--circle { width: 2.5rem; height: 2.5rem; border-radius: var(--aui-radius-full); }

.aui-skeleton::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, var(--aui-color-surface-raised), transparent);
  animation: aui-skeleton-shimmer 1.6s infinite;
}

@keyframes aui-skeleton-shimmer {
  from { transform: translateX(-100%); }
  to { transform: translateX(100%); }
}

@media (prefers-reduced-motion: reduce) {
  .aui-skeleton::after {
    animation: none;
  }
}
</style>
