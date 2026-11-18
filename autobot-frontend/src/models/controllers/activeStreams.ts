// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** Chats with a response stream in flight (#21357): a count per chat, so typing state follows the chat. */
export class ActiveStreams {
  private counts = new Map<string, number>()

  begin(sessionId: string | undefined): void {
    if (sessionId) this.counts.set(sessionId, (this.counts.get(sessionId) ?? 0) + 1)
  }

  end(sessionId: string | undefined): void {
    if (!sessionId) return
    const left = (this.counts.get(sessionId) ?? 1) - 1
    if (left > 0) this.counts.set(sessionId, left)
    else this.counts.delete(sessionId)
  }

  has(sessionId: string): boolean {
    return this.counts.has(sessionId)
  }

  /** Streams in flight across every chat. */
  get total(): number {
    let n = 0
    for (const c of this.counts.values()) n += c
    return n
  }
}
