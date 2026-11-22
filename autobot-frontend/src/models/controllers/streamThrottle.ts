// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { ChatMessage, ChatMessageDisplayType } from '@/types/api'
import { extractStreamingPreview } from './streamFormat'

type Timer = ReturnType<typeof setTimeout>

interface PendingUpdate {
  sessionId?: string
  messageId: string
  content: string
  type: ChatMessageDisplayType | string | undefined
  metadata: Record<string, unknown>
}

export interface StreamThrottleSink {
  updateMessage(messageId: string, updates: Partial<ChatMessage>, sessionId?: string): void
  setPreview(preview: string): void
  /** True when `sessionId` is unknown or is the chat currently open. */
  isOpenChat(sessionId: string | undefined): boolean
}

/**
 * Issue #1312: throttles streaming store writes (~12fps) and preview extraction (200ms), split out of
 * ChatController. #21357: updates are buffered per `sessionId:messageId` so interleaved streams each keep
 * theirs, and the preview timer is owned by one chat so another chat's pending timer cannot swallow its request.
 */
export class StreamThrottle {
  static readonly FLUSH_INTERVAL_MS = 80
  static readonly PREVIEW_INTERVAL_MS = 200

  private pending = new Map<string, PendingUpdate>()
  private flushTimer: Timer | null = null
  private previewTimer: Timer | null = null
  private previewOwner: string | undefined

  constructor(private readonly sink: StreamThrottleSink) {}

  schedule(update: PendingUpdate): void {
    this.pending.set(`${update.sessionId ?? ''}:${update.messageId}`, update)
    if (this.flushTimer) return
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null
      this.flush()
    }, StreamThrottle.FLUSH_INTERVAL_MS)
  }

  flush(): void {
    const updates = [...this.pending.values()]
    this.pending.clear()
    for (const { sessionId, messageId, content, type, metadata } of updates) {
      this.sink.updateMessage(messageId, { content, type, metadata: metadata as ChatMessage['metadata'] }, sessionId)
    }
  }

  schedulePreview(content: string, messageType: string | undefined, sessionId: string | undefined): void {
    if (this.previewTimer) {
      if (this.previewOwner === sessionId) return // already scheduled for this chat
      clearTimeout(this.previewTimer) // another chat's timer must not swallow this chat's request
    }
    this.previewOwner = sessionId
    this.previewTimer = setTimeout(() => {
      this.previewTimer = null
      const preview = extractStreamingPreview(content, messageType)
      if (preview && this.sink.isOpenChat(sessionId)) this.sink.setPreview(preview)
    }, StreamThrottle.PREVIEW_INTERVAL_MS)
  }

  /** End of a stream: flush what is buffered; drop the preview timer unless another stream still needs it. */
  finish(otherStreamsActive: boolean): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer)
      this.flushTimer = null
    }
    this.flush()
    if (this.previewTimer && !otherStreamsActive) {
      clearTimeout(this.previewTimer)
      this.previewTimer = null
    }
  }
}
