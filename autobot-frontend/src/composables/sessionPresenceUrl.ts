// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { getApiBase } from '@/config/ssot-config'
import { withCompanyScope } from '@/utils/buildAuthenticatedWsUrl'

/**
 * The presence WebSocket URL for a session, naming the selected company (#21997).
 * #16457: the token travels via the Sec-WebSocket-Protocol subprotocol, not the URL.
 */
export function presenceWsUrl(sessionId: string): string {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return withCompanyScope(`${wsProtocol}//${window.location.host}${getApiBase()}/ws/sessions/${sessionId}/presence`)
}
