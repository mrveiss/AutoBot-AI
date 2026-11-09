<template>
  <div class="stall-question" :class="{ 'stall-question--answered': answered }" role="group" :aria-label="$t('chat.stallQuestion.title')">
    <div class="stall-question__header">
      <Icon name="question-circle" />
      <span class="stall-question__title">{{ $t('chat.stallQuestion.title') }}</span>
    </div>
    <p class="stall-question__text">{{ message.content }}</p>
    <p v-if="answered" class="stall-question__answer">
      {{ answerText ? $t('chat.stallQuestion.answered', { answer: answerText }) : $t('chat.stallQuestion.stopped') }}
    </p>
    <form v-else class="stall-question__form" @submit.prevent="send(draft.trim())">
      <BaseInput v-model="draft" :label="$t('chat.stallQuestion.answerLabel')" :placeholder="$t('chat.stallQuestion.placeholder')" />
      <div class="stall-question__actions">
        <BaseButton type="submit" variant="primary" size="sm" :disabled="busy || !draft.trim()">
          {{ $t('chat.stallQuestion.send') }}
        </BaseButton>
        <BaseButton variant="outline" size="sm" :disabled="busy" @click="send('')">
          {{ $t('chat.stallQuestion.stop') }}
        </BaseButton>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** The question a stalled chat turn asks its person (#21022); an empty answer means "stop here". */
import { computed, ref } from 'vue'
import { BaseButton, BaseInput } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useStallAnswer } from '@/composables/useGraphApproval'
import { useChatStore, type ChatMessage } from '@/stores/useChatStore'

const props = defineProps<{ message: ChatMessage }>()

const store = useChatStore()
const answerStallQuestion = useStallAnswer()
const draft = ref('')
const answered = computed(() => props.message.metadata?.answered === true)
const answerText = computed(() => String(props.message.metadata?.answer_text ?? ''))
const busy = computed(() => store.isTyping)

async function send(text: string): Promise<void> {
  await answerStallQuestion(props.message, text)
}
</script>

<style scoped>
.stall-question {
  border: 1px solid var(--color-warning, #d97706);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.stall-question--answered {
  opacity: 0.8;
}
.stall-question__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
}
.stall-question__actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
