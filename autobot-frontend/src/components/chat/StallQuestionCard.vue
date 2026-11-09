<template>
  <div class="flex flex-col gap-2 rounded-lg border border-amber-600 px-4 py-3" :class="{ 'opacity-80': answered }" role="group" :aria-label="$t('chat.stallQuestion.title')">
    <div class="flex items-center gap-2 font-semibold">
      <Icon name="question-circle" />
      <span>{{ $t('chat.stallQuestion.title') }}</span>
    </div>
    <p>{{ message.content }}</p>
    <p v-if="answered">
      {{ answerText ? $t('chat.stallQuestion.answered', { answer: answerText }) : $t('chat.stallQuestion.stopped') }}
    </p>
    <form v-else @submit.prevent="send(draft.trim())">
      <BaseInput v-model="draft" :label="$t('chat.stallQuestion.answerLabel')" :placeholder="$t('chat.stallQuestion.placeholder')" />
      <div class="mt-2 flex gap-2">
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
