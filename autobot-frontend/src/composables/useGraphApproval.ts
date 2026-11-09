// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Approval cards that come from the chat graph's own interrupt (#20195).
 *
 * The graph pauses at `request_approval` and streams a `command_approval_request` whose metadata carries the
 * `calls` the person is being asked about. That pause is answered ONLY by `POST /chats/{id}/resume`; the
 * terminal approval route (`/agent-terminal/sessions/{id}/approve`, `useCommandApproval`) cannot reach the
 * graph. So a card with `metadata.calls` posts its decision to resume and feeds the SSE reply through the chat
 * controller's one stream consumer, into the same chat. Terminal cards keep their path unchanged.
 */

import { getApiBase } from '@/config/ssot-config'
import { useChatController } from '@/models/controllers'
import { useChatStore, type ChatMessage } from '@/stores/useChatStore'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('GraphApproval')

type Metadata = ChatMessage['metadata'] | undefined

/** True for a card raised by the graph interrupt (it names the calls asked about); false for a terminal card. */
export function isGraphApproval(metadata: Metadata): boolean {
  return Array.isArray((metadata as Record<string, unknown> | undefined)?.calls)
}

type TerminalApprove = (
  terminalSessionId: string,
  approved: boolean,
  comment?: string,
  commandId?: string,
  onUpdate?: (sessionId: string, status: string, comment?: string) => void,
  commandInfo?: { command: string; risk_level: string }
) => Promise<unknown> | unknown

/** What a paused chat graph is resumed with: an approval decision, or the answer to a stall question (#21022). */
export type ResumeBody = { approved: boolean; reason: string } | { answer: string }

/** The one POST to `/chats/{id}/resume`, whose SSE reply the chat controller's stream consumer renders. */
function useResumePost() {
  const store = useChatStore()
  const controller = useChatController()

  return async function postResume(message: ChatMessage, body: ResumeBody): Promise<void> {
    const chatId = String((message.metadata as Record<string, unknown>)?.session_id || store.currentSessionId || '')
    store.setTyping(true)
    try {
      const response = await fetchWithAuth(`${getApiBase()}/chats/${encodeURIComponent(chatId)}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!response.ok) throw new Error(`resume failed: ${response.status}`)
      await controller.handleStreamingResponse(response)
    } catch (error) {
      logger.error('Resuming the chat failed:', error)
      throw error
    } finally {
      store.setTyping(false)
    }
  }
}

/** Answer the question a stalled turn asked; an empty answer stops the turn (#21022). */
export function useStallAnswer() {
  const store = useChatStore()
  const postResume = useResumePost()
  return async function answerStallQuestion(message: ChatMessage, answer: string): Promise<void> {
    store.updateMessageMetadata(message.id, { answered: true, answer_text: answer })
    await postResume(message, { answer })
  }
}

export function useApprovalRouting(terminalApprove: TerminalApprove) {
  const store = useChatStore()
  const postResume = useResumePost()

  const findPending = (sessionId: string) =>
    store.currentMessages.find(
      (msg) => msg.metadata?.terminal_session_id === sessionId && msg.metadata?.requires_approval === true
    )

  async function resumeGraph(message: ChatMessage, approved: boolean, comment?: string): Promise<void> {
    store.updateMessageMetadata(message.id, { approval_status: approved ? 'approved' : 'denied', approval_comment: comment })
    store.setPendingApproval(false)
    await postResume(message, { approved, reason: comment || '' })
  }

  /** Same signature as the terminal approve; a graph card goes to resume, any other card to the terminal route. */
  return (
    terminalSessionId: string,
    approved: boolean,
    comment?: string,
    commandId?: string,
    commandInfo?: { command: string; risk_level: string }
  ) => {
    const pending = findPending(terminalSessionId)
    if (pending && isGraphApproval(pending.metadata)) return resumeGraph(pending, approved, comment)
    const onUpdate = (sessionId: string, status: string, updateComment?: string) => {
      const target = findPending(sessionId)
      if (target?.metadata) {
        target.metadata.approval_status = status
        target.metadata.approval_comment = updateComment
      } else {
        logger.warn('Could not find message to update approval status')
      }
    }
    return terminalApprove(terminalSessionId, approved, comment, commandId, onUpdate, commandInfo)
  }
}
