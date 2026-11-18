// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Org-scoped conversation review (#17832).
 *
 * Two existing, server-gated reads, typed from the generated contract (`paths`):
 *   - `GET /api/chat/sessions?scope=org`      the caller's own organization's sessions
 *   - `GET /api/chat/sessions/{session_id}`   one transcript, page by page
 * The server is the authority for both: the list refuses a caller without an
 * administrative role, a transcript is served only when the session's org matches
 * the caller's, and every transcript open is written to the audit trail by
 * `SessionOwnershipValidator`. This module adds no access of its own.
 */
import type { paths } from '@/types/generated/api'
import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'

type Body<P extends keyof paths> = paths[P] extends {
  get: { responses: { 200: { content: { 'application/json': infer J } } } }
}
  ? J
  : never

const SESSIONS_PATH = '/api/chat/sessions' as const
const SESSION_PATH = '/api/chat/sessions/{session_id}' as const

/** The contract path, rebased on the configured API base (the SSOT, never a literal). */
const url = (contractPath: string): string => `${getApiBase()}${contractPath.slice('/api'.length)}`

export type OrgSessionsResponse = Body<typeof SESSIONS_PATH>
export type TranscriptResponse = Body<typeof SESSION_PATH>
export type OrgSessionsData = NonNullable<OrgSessionsResponse['data']>
export type OrgSession = OrgSessionsData['sessions'][number]
export type TranscriptData = NonNullable<TranscriptResponse['data']>
export type TranscriptMessage = TranscriptData['messages'][number]

/** Messages per transcript page; the backend accepts a caller-chosen size. */
export const TRANSCRIPT_PAGE_SIZE = 50

export function useOrgConversationReview() {
  const api = useApiClient()

  async function listOrgSessions(): Promise<OrgSessionsData | null> {
    const body = (await api.get(`${url(SESSIONS_PATH)}?scope=org`)) as OrgSessionsResponse
    return body?.data ?? null
  }

  async function openTranscript(sessionId: string, page: number): Promise<TranscriptData | null> {
    const path = SESSION_PATH.replace('{session_id}', encodeURIComponent(sessionId))
    const query = `page=${page}&per_page=${TRANSCRIPT_PAGE_SIZE}`
    const body = (await api.get(`${url(path)}?${query}`)) as TranscriptResponse
    return body?.data ?? null
  }

  return { listOrgSessions, openTranscript }
}
