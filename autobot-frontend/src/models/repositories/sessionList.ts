// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

import apiClient from '@/utils/ApiClient'
import { orgScope } from '@/utils/orgContext'
import {
  toSessionDate,
  withUnassigned,
  type ChatListEntry,
  type ChatListReply,
} from './sessionDates'

/** Minimal session shape returned by the backend list endpoint */
interface BackendSessionEntry {
  id?: string
  chatId?: string
  title?: string
  name?: string
  createdAt?: string
  createdTime?: string
  updatedAt?: string
  lastModified?: string
  companyId?: string
}

/** The request headers that scope the list to a company via X-Organization-Id (#16905). */
function listHeaders(companyId?: unknown) {
  return typeof companyId === 'string' && companyId ? orgScope(companyId).headers : undefined
}

/**
 * Fetch the chat list and map it to the store's shape. The list is `{ sessions }` or
 * `{ data: { sessions } }`; `companyId` scopes it (#16905).
 *
 * NOTE: the mapped objects use the store's camelCase/Date shape
 * (createdAt/updatedAt/isActive) rather than the declared `ChatSession`
 * wire type — masked while axios typed `.data` as `any` (#12363 Phase 2).
 */
export async function fetchChatList(companyId?: unknown): Promise<ChatListEntry[]> {
  const reply = (await apiClient.call('get', '/api/chat/sessions', {
    headers: listHeaders(companyId),
  })) as ChatListReply<BackendSessionEntry>
  const body = reply.data ?? reply
  const sessions = withUnassigned(body?.sessions || [], body?.unassigned || [])
  return sessions.map((session) => ({
    id: session.id || session.chatId,
    title: session.title || session.name || `Chat ${session.id?.slice(0, 8)}`,
    messages: [], // Sessions list doesn't include messages - loaded separately
    createdAt: toSessionDate(session.createdAt, session.createdTime),
    updatedAt: toSessionDate(session.updatedAt, session.lastModified),
    isActive: false, // Will be set by store when session is selected
    unassigned: session.unassigned,
    companyId: session.companyId,
  })) as unknown as ChatListEntry[]
}
