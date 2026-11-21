<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatHeaderIconButton -- one icon-only button of the chat header (#18243): a kit ghost
  BaseButton inside a BaseTooltip. `label` is both the accessible name and the tooltip, so an
  icon-only control can never ship without either. `pressed` is a toggle (aria-pressed, styled by
  the kit); `expanded` + `controls` name a disclosure panel. `adv` hides it in Minimal mode.
  Emits `el` with the button element (and null on unmount) for focus return after a panel closes.
-->
<template>
  <BaseTooltip :text="label" placement="bottom" :class="{ adv }">
    <template #default="{ describedby }">
      <BaseButton
        ref="button"
        variant="ghost"
        size="sm"
        class="chat-header-btn"
        :aria-label="label"
        :aria-describedby="describedby"
        :aria-pressed="pressed"
        :aria-expanded="expanded"
        :aria-controls="controls"
        @click="emit('click')"
      >
        <Icon :name="icon" :class="iconClass" />
      </BaseButton>
    </template>
  </BaseTooltip>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { BaseButton, BaseTooltip } from '@autobot/ui'
import Icon, { type IconName } from '@/components/ui/Icon.vue'

defineProps<{
  label: string
  icon: IconName
  iconClass?: string
  pressed?: boolean
  expanded?: boolean
  controls?: string
  adv?: boolean
}>()
const emit = defineEmits<{ click: []; el: [element: HTMLElement | null] }>()

const button = ref<{ $el: HTMLElement } | null>(null)
watch(button, (instance) => emit('el', instance?.$el ?? null), { flush: 'post' })
</script>

<style scoped>
/* A 44px touch target on mobile (#1804), the kit's compact size from sm up. */
.chat-header-btn {
  min-inline-size: 2.75rem;
  min-block-size: 2.75rem;
}

@media (min-width: 640px) {
  .chat-header-btn {
    min-inline-size: 2rem;
    min-block-size: 2rem;
  }
}
</style>
