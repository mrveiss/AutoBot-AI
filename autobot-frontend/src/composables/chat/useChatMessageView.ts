// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Presentation helpers for one chat message row (#18243, step 5a batch 2).
 * Pure functions moved out of ChatMessages.vue unchanged: class names, sender icon,
 * sender name and the typed-message badge. The component supplies `t`.
 */
import type { IconName } from '@/components/ui/Icon.vue'
import type { ChatMessage } from '@/stores/useChatStore'

type Translate = (key: string) => string

export interface MessageTypeBadge {
  label: string
  icon: IconName
  type: string
}

/** Types that never get a `type-*` class (#680: streaming types must not pick a wrong badge). */
const NO_TYPE_CLASS = ['response', 'message', 'default', 'llm_response', 'llm_response_chunk']

const TYPE_ICONS: Record<string, IconName> = {
  thought: 'brain',
  planning: 'list',
  debug: 'bug',
  utility: 'wrench',
  sources: 'book-open',
  command_approval_request: 'shield-alt',
  terminal_output: 'terminal',
  terminal_command: 'terminal',
  overseer_plan: 'sitemap',
  overseer_step: 'tasks',
  llm_response: 'robot',
  llm_response_chunk: 'robot',
}

const SENDER_ICONS: Record<string, IconName> = {
  user: 'user',
  assistant: 'robot',
  system: 'cog',
  error: 'exclamation-triangle',
  thought: 'brain',
  'tool-code': 'code',
  'tool-output': 'terminal',
}

/** The message's own type, falling back to the backend's `metadata.display_type`. */
export function messageTypeOf(message: ChatMessage): string | undefined {
  return message.type || (message.metadata?.display_type as string | undefined) || undefined
}

export function getMessageWrapperClass(message: ChatMessage): string {
  const classes = ['message', `${message.sender}-message`]
  const messageType = messageTypeOf(message)
  if (messageType && !NO_TYPE_CLASS.includes(String(messageType))) classes.push(`type-${messageType}`)
  if (message.status === 'error') classes.push('error')
  if (message.status === 'sending') classes.push('sending')
  return classes.join(' ')
}

export function getContentClass(message: ChatMessage): string {
  const classes = ['message-content']
  if (message.sender === 'user') classes.push('user-content')
  if (message.sender === 'assistant') classes.push('assistant-content')
  if (message.sender === 'system') classes.push('system-content')
  return classes.join(' ')
}

/** Type-specific icons take precedence over sender icons. */
export function getSenderIcon(sender: string, messageType?: string): IconName {
  if (messageType && TYPE_ICONS[messageType]) return TYPE_ICONS[messageType]
  return SENDER_ICONS[sender] || 'comment'
}

export function getSenderName(sender: string, t: Translate): string {
  const names: Record<string, string> = {
    user: t('chat.messages.senderYou'),
    assistant: t('chat.messages.aiAssistant'),
    system: t('chat.messages.senderSystem'),
    error: t('common.error'),
    thought: t('chat.messages.senderThought'),
    'tool-code': t('chat.messages.senderCodeExecution'),
    'tool-output': t('chat.messages.senderOutput'),
  }
  return names[sender] || sender
}

const BADGES: Record<string, { key: string; icon: IconName }> = {
  thought: { key: 'badgeThought', icon: 'brain' },
  planning: { key: 'badgePlanning', icon: 'list' },
  debug: { key: 'badgeDebug', icon: 'bug' },
  utility: { key: 'badgeUtility', icon: 'wrench' },
  sources: { key: 'badgeSources', icon: 'book-open' },
}

/** Issue #1310: visible badge for typed messages so they are clearly distinguishable. */
export function getMessageTypeBadge(message: ChatMessage, t: Translate): MessageTypeBadge | null {
  const msgType = messageTypeOf(message)
  const badge = msgType ? BADGES[String(msgType)] : undefined
  if (!badge) return null
  return { label: t(`chat.messages.${badge.key}`), icon: badge.icon, type: String(msgType) }
}
