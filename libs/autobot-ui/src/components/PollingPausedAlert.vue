<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  PollingPausedAlert — the one "updates have stopped" notice for a usePollingJob
  poller that hit its consecutiveErrorLimit (#19482, owner decision 2026-10-25:
  pause, show it, offer Retry). Without it a stopped poller leaves the last numbers
  on screen as if they were live.

  It renders only while `poller.pausedOnErrors` is true, the state usePollingJob sets
  when its consecutiveErrorLimit stops it, so a deliberate stop() never shows it. The kit holds no text: `message` and
  `retryLabel` come translated from the app. Retry emits `retry`; the caller restarts
  its poller (usually `poller.start(...)`).
-->
<script setup lang="ts">
import type { Ref } from 'vue'
import BaseAlert from './BaseAlert.vue'
import BaseButton from './BaseButton.vue'

const props = defineProps<{
  /** The poller's state; only `pausedOnErrors` is read. */
  poller: { pausedOnErrors: Readonly<Ref<boolean>> }
  message: string
  retryLabel: string
}>()

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <BaseAlert v-if="props.poller.pausedOnErrors.value" variant="warning" :message="message" data-polling-paused>
    <template #actions>
      <BaseButton size="sm" variant="secondary" @click="emit('retry')">{{ retryLabel }}</BaseButton>
    </template>
  </BaseAlert>
</template>
