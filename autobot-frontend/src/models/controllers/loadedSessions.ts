// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { ChatSession } from '@/stores/useChatStore'

/** The store's import surface; the listed entries come from the repository. */
interface SessionImporter {
  importSession(session: ChatSession): void
}

/**
 * Put a loaded session list into the store. The store needs isActive (#9724). Dates are taken as the
 * repository mapped them (#20865): re-deriving them from snake_case fields it does not return produced
 * Invalid Date.
 */
export function importLoadedSessions(store: SessionImporter, sessions: Array<Partial<ChatSession>>): void {
  sessions.forEach(session => {
    store.importSession({ ...session, title: session.title ?? '', isActive: false } as ChatSession)
  })
}
