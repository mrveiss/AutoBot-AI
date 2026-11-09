// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Advanced Control WebSocket URL builders (#583, #12363).
 *
 * A socket is not an HTTP call, so these stay plain functions beside the typed client.
 */

import { getApiBase, getBackendWsUrl } from '@/config/ssot-config'

/** WebSocket URL for real-time system monitoring. */
export function getMonitoringWebSocketUrl(): string {
  // #19821: same-origin through the proxy, as every other backend socket (getBackendWsUrl).
  return `${getBackendWsUrl()}${getApiBase()}/advanced-control/ws/monitoring`
}

/**
 * WebSocket URL for desktop streaming control of one session.
 *
 * No caller yet (the deleted AdvancedControlApiClient method had none either); wiring it into the
 * desktop streaming UI is tracked in #21077. Do not delete.
 */
export function getDesktopWebSocketUrl(sessionId: string): string {
  return `${getBackendWsUrl()}${getApiBase()}/advanced-control/ws/desktop/${encodeURIComponent(sessionId)}`
}
