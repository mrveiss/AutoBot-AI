<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatComposerSendButton -- the composer's Send button (#18243): the kit primary button with the Refined
  arrow, a loading state while a send is in flight, and the queued-message count badge. The queue count has no
  producer yet (nothing queues chat messages); the badge is kept wired to this prop, default 0.
-->
<template>
  <BaseButton
    variant="primary"
    class="min-h-11 min-w-11 px-3 sm:min-h-9 sm:min-w-9"
    :class="{ 'animate-pulse motion-reduce:animate-none': queueLength > 0 }"
    :disabled="!canSend"
    :loading="sending"
    :aria-label="label"
    @click="emit('send')"
  >
    <span v-if="!sending && queueLength > 0" class="relative inline-flex" data-testid="send-queue">
      <Icon name="paper-plane" />
      <span class="absolute -end-1 -top-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--aui-color-error-solid)] text-xs font-semibold text-[var(--aui-color-error-contrast)]" data-testid="send-queue-count">{{ queueLength }}</span>
    </span>
    <Icon v-else-if="!sending" name="paper-plane" aria-hidden="true" />
  </BaseButton>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

const props = withDefaults(defineProps<{ canSend: boolean; sending: boolean; queueLength?: number }>(), { queueLength: 0 })
const emit = defineEmits<{ send: [] }>()

const { t } = useI18n()
const label = computed(() => {
  if (props.sending) return t('chat.input.sending')
  return props.canSend ? t('chat.input.sendMessage') : t('chat.input.enterMessage')
})
</script>
