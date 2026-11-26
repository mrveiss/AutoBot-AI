// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { getApiBase, getBackendWsUrl } from '@/config/ssot-config'
import { withCompanyScope } from '@/utils/orgContext'

/**
 * The presence WebSocket URL for a session, naming the selected company (#21997).
 * #16457: the token travels via the Sec-WebSocket-Protocol subprotocol, not the URL.
 */
export function presenceWsUrl(sessionId: string): string {
  return withCompanyScope(`${getBackendWsUrl()}${getApiBase()}/ws/sessions/${sessionId}/presence`)
}
