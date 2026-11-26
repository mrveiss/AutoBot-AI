<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatComposerChip -- one composer toggle (#18243): the kit toggle chip (#21995) inside a tooltip,
  with the Refined check mark so the state is never colour alone. The label and tooltip text are
  supplied, translated, by the caller; `adv` hides the chip in Minimal mode.
-->
<template>
  <BaseTooltip :text="tip" placement="top" :class="{ adv }">
    <template #default="{ describedby }">
      <BaseChip :pressed="pressed" :disabled="disabled" :aria-describedby="describedby" @update:pressed="emit('update:pressed', $event)">
        <template #icon><Icon :name="pressed ? 'check' : 'circle'" size="xs" :stroke-width="pressed ? 4 : 2" /></template>
        {{ label }}
      </BaseChip>
    </template>
  </BaseTooltip>
</template>

<script setup lang="ts">
import { BaseChip, BaseTooltip } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

withDefaults(
  defineProps<{ label: string; tip: string; pressed: boolean; disabled?: boolean; adv?: boolean }>(),
  { disabled: false, adv: false },
)
const emit = defineEmits<{ 'update:pressed': [value: boolean] }>()
</script>
