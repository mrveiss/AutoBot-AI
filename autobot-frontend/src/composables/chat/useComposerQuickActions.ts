// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The composer's insert-into-draft helpers, moved out of ChatInput.vue (#18243): the overflow
 * menu's quick actions (#1569), emoji at the caret, an MCP prompt template (MVA-2167) and a
 * translation result (#1328).
 */
import { computed, nextTick, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/useChatStore'
import type { IconName } from '@/components/ui/Icon.vue'

export interface QuickAction {
  id: string
  label: string
  icon: IconName
  description: string
}

export interface TranslationResult {
  originalText: string
  translatedText: string
  targetLanguage: string
}

/** The text a quick action starts the draft with; Translate opens its panel instead. */
export const QUICK_ACTION_TEXT_KEYS: Record<string, string> = {
  help: 'chat.input.quickActionText.help',
  summarize: 'chat.input.quickActionText.summarize',
  explain: 'chat.input.quickActionText.explain',
}

export function useComposerQuickActions(messageText: Ref<string>, messageInput: Ref<HTMLTextAreaElement | undefined>) {
  const { t } = useI18n()
  const store = useChatStore()
  const showTranslatePanel = ref(false)

  const quickActions = computed<QuickAction[]>(() => [
    { id: 'help', label: t('chat.input.help'), icon: 'question-circle', description: t('chat.input.helpDesc') },
    { id: 'summarize', label: t('chat.input.summarize'), icon: 'compress', description: t('chat.input.summarizeDesc') },
    { id: 'translate', label: t('agent.translate'), icon: 'language', description: t('chat.input.translateDesc') },
    { id: 'explain', label: t('chat.input.explain'), icon: 'lightbulb', description: t('chat.input.explainDesc') },
  ])

  function runQuickAction(id: string): void {
    if (id === 'translate') {
      showTranslatePanel.value = !showTranslatePanel.value
      return
    }
    const text = QUICK_ACTION_TEXT_KEYS[id] ? t(QUICK_ACTION_TEXT_KEYS[id]) : ''
    messageText.value = text
    nextTick(() => {
      messageInput.value?.focus()
      messageInput.value?.setSelectionRange(text.length, text.length)
    })
  }

  /** Insert at the caret (replacing the selection) and put the caret after it. */
  function insertAtCaret(insert: string): void {
    const textarea = messageInput.value
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    messageText.value = messageText.value.slice(0, start) + insert + messageText.value.slice(end)
    nextTick(() => {
      textarea.setSelectionRange(start + insert.length, start + insert.length)
      textarea.focus()
    })
  }

  function handlePromptInsert(text: string): void {
    messageText.value = text
    nextTick(() => messageInput.value?.focus())
  }

  function handleTranslationResult(payload: TranslationResult): void {
    showTranslatePanel.value = false
    store.addMessage({
      content: `**${payload.targetLanguage}:**\n${payload.translatedText}`,
      sender: 'assistant',
      status: 'sent',
      type: 'message',
    })
  }

  return { quickActions, showTranslatePanel, runQuickAction, insertAtCaret, handlePromptInsert, handleTranslationResult }
}
