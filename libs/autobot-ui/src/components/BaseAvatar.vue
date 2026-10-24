<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  BaseAvatar — a person's initials in a circle, with an optional presence dot (#14780 group 2).
  Replaces eight hand-rolled avatars in the user app (collaboration, secrets sharing, the
  Company OS boards), which used three different initials rules (see utils/initials.ts).
  Named by `name` (role=img) unless `decorative`, for when the name is shown beside it.
    props : name, size (xs | sm | md | lg), variant (neutral | primary), status, ring,
            decorative
-->
<script setup lang="ts">
import { computed } from 'vue'
import { initialsOf } from '../utils/initials'

export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg'
export type AvatarVariant = 'neutral' | 'primary'
export type AvatarStatus = 'online' | 'away' | 'offline'

const props = withDefaults(
  defineProps<{
    name: string
    size?: AvatarSize
    variant?: AvatarVariant
    status?: AvatarStatus
    ring?: boolean
    decorative?: boolean
  }>(),
  { size: 'md', variant: 'neutral', status: undefined, ring: false, decorative: false },
)

const initials = computed(() => initialsOf(props.name))
</script>

<template>
  <span
    class="aui-avatar"
    :class="[`aui-avatar--${size}`, `aui-avatar--${variant}`, { 'aui-avatar--ring': ring }]"
    :role="decorative ? undefined : 'img'"
    :aria-label="decorative ? undefined : name"
    :aria-hidden="decorative ? 'true' : undefined"
    :title="name"
  >
    <span class="aui-avatar__initials" aria-hidden="true">{{ initials }}</span>
    <span v-if="status" class="aui-avatar__status" :class="`aui-avatar__status--${status}`" :data-status="status" />
  </span>
</template>

<style scoped>
.aui-avatar {
  --aui-avatar-size: 2rem;
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: var(--aui-avatar-size);
  height: var(--aui-avatar-size);
  border-radius: var(--aui-radius-full);
  font-size: calc(var(--aui-avatar-size) * 0.375);
  font-weight: var(--aui-font-weight-semibold);
  line-height: 1;
  cursor: default;
  user-select: none;
}

.aui-avatar--xs { --aui-avatar-size: 1.5rem; }
.aui-avatar--sm { --aui-avatar-size: 1.75rem; }
.aui-avatar--md { --aui-avatar-size: 2rem; }
.aui-avatar--lg { --aui-avatar-size: 2.5rem; }

.aui-avatar--neutral {
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
}

.aui-avatar--primary {
  background: var(--aui-color-primary);
  color: var(--aui-color-text-inverse);
}

.aui-avatar--ring {
  box-shadow: 0 0 0 2px var(--aui-color-surface);
}

.aui-avatar__status {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: calc(var(--aui-avatar-size) * 0.32);
  height: calc(var(--aui-avatar-size) * 0.32);
  border: 2px solid var(--aui-color-surface);
  border-radius: var(--aui-radius-full);
}

.aui-avatar__status--online { background: var(--aui-color-success); }
.aui-avatar__status--away { background: var(--aui-color-warning); }
.aui-avatar__status--offline { background: var(--aui-color-border-strong); }
</style>
