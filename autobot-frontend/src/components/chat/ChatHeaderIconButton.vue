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
        class="min-w-11 min-h-11 sm:min-w-8 sm:min-h-8"
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
import { onBeforeUnmount, ref, watch } from 'vue'
import { BaseButton, BaseTooltip } from '@autobot/ui'
import Icon, { type IconName } from '@/components/ui/Icon.vue'

// pressed / expanded default to undefined, not false: Vue casts an absent Boolean prop to false, which
// would put aria-pressed="false" and aria-expanded="false" on buttons that are neither toggles nor disclosures.
withDefaults(
  defineProps<{
    label: string
    icon: IconName
    iconClass?: string
    pressed?: boolean
    expanded?: boolean
    controls?: string
    adv?: boolean
  }>(),
  { iconClass: undefined, pressed: undefined, expanded: undefined, controls: undefined, adv: false },
)
const emit = defineEmits<{ click: []; el: [element: HTMLElement | null] }>()

const button = ref<{ $el: HTMLElement } | null>(null)
watch(button, (instance) => emit('el', instance?.$el ?? null), { flush: 'post' })
// Vue stops this setup watcher before it unmounts the child, so the ref going null never reaches it:
// report the removal explicitly, or the parent keeps a detached element as its focus target.
onBeforeUnmount(() => emit('el', null))
</script>
