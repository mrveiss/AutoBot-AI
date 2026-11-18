<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  EmptyState — thin adapter over the kit's EmptyState (#14776). The kit owns
  the markup and styling; this file only maps the app's call-site props onto
  it: `message` -> the kit `description`, and `icon` (an Icon.vue registry
  name) -> the kit `icon` slot, so the ~48 existing call sites stay untouched.
-->
<template>
  <KitEmptyState :title="title" :description="message" :compact="compact">
    <template v-if="icon" #icon>
      <Icon :name="icon" size="xl" />
    </template>
    <template v-if="$slots.actions" #actions>
      <slot name="actions" />
    </template>
  </KitEmptyState>
</template>

<script setup lang="ts">
import { EmptyState as KitEmptyState } from '@autobot/ui'
import Icon, { type IconName } from './Icon.vue'

interface Props {
  /** Icon name from Icon.vue registry */
  icon?: IconName
  /** Title text */
  title?: string
  /** Message text (the kit's `description`) */
  message?: string
  /** Compact mode (smaller spacing) */
  compact?: boolean
}

withDefaults(defineProps<Props>(), {
  icon: 'inbox',
  compact: false
})
</script>
