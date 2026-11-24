<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatComposerToggles -- the composer's option chips (#18243): Use Knowledge (#249), Overseer (#690) and
  extended Thinking (GH#8993) with its token-budget steps. Overseer and Thinking are advanced controls
  (`.adv`, as in the Chat mockup). The state is owned by the caller; this renders and emits.
-->
<template>
  <div class="contents">
    <ChatComposerChip
      :label="$t('chat.input.useKnowledge')"
      :tip="$t('chat.composer.knowledgeTip')"
      :pressed="knowledge"
      :disabled="disabled"
      data-testid="toggle-knowledge"
      @update:pressed="emit('update:knowledge', $event)"
    />
    <ChatComposerChip
      adv
      :label="$t('chat.input.overseerLabel')"
      :tip="$t('chat.header.overseerTip')"
      :pressed="overseer"
      data-testid="toggle-overseer"
      @update:pressed="emit('toggle-overseer')"
    />
    <ChatComposerChip
      adv
      :label="$t('chat.composer.thinkingLabel')"
      :tip="thinking ? $t('chat.input.thinkingOn') : $t('chat.composer.thinkingTip')"
      :pressed="thinking"
      data-testid="toggle-thinking"
      @update:pressed="emit('toggle-thinking')"
    />
    <div v-if="thinking" class="adv inline-flex items-center gap-1" role="group" :aria-label="$t('chat.input.thinkingBudget')">
      <BaseChip
        v-for="step in BUDGET_STEPS"
        :key="step"
        size="sm"
        :pressed="budget === step"
        :title="$t('chat.composer.budgetTokens', { label: BUDGET_STEP_LABELS[step] })"
        data-testid="budget-step"
        @update:pressed="emit('set-budget', step)"
      >
        {{ BUDGET_STEP_LABELS[step] }}
      </BaseChip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BaseChip } from '@autobot/ui'
import ChatComposerChip from './ChatComposerChip.vue'
import { BUDGET_STEPS, BUDGET_STEP_LABELS } from '@/composables/useThinkingMode'

defineProps<{
  knowledge: boolean
  overseer: boolean
  thinking: boolean
  budget: number
  disabled?: boolean
}>()
const emit = defineEmits<{
  'update:knowledge': [value: boolean]
  'toggle-overseer': []
  'toggle-thinking': []
  'set-budget': [tokens: number]
}>()
</script>
