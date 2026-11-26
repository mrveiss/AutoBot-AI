// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * noVNC client URL and connect-probe settings for the fleet noVNC tool (#22144).
 *
 * The URL scheme and authority come from the websocket_url the SLM API returns
 * for a fleet endpoint; only the client page path and query are configured here.
 */

import { getEnvPositiveInt } from '@autobot/ui'

/** Path of the noVNC client page on a websockify host. */
export const VNC_CLIENT_PATH: string = import.meta.env.VITE_VNC_CLIENT_PATH || '/vnc.html'

/** Query string that makes the embedded client connect and fit on load. */
export const VNC_CLIENT_QUERY: string = import.meta.env.VITE_VNC_CLIENT_QUERY || 'autoconnect=true&resize=scale'

/** How long a connect probe waits for the endpoint's websocket to open (ms). */
export const VNC_CONNECT_TIMEOUT_MS: number = getEnvPositiveInt(import.meta.env, 'VITE_VNC_CONNECT_TIMEOUT_MS', 8000)

const WS_TO_HTTP: Record<string, string> = { 'wss:': 'https:', 'ws:': 'http:' }

/** noVNC client page URL on the same host as an endpoint's websocket URL. */
export function vncClientUrlFromWebsocket(websocketUrl: string): string {
  const ws = new URL(websocketUrl)
  const scheme = WS_TO_HTTP[ws.protocol]
  if (!scheme) throw new Error(`Unsupported VNC websocket scheme: ${ws.protocol}`)
  return `${scheme}//${ws.host}${VNC_CLIENT_PATH}?${VNC_CLIENT_QUERY}`
}

/** Open the endpoint's websocket for real; resolves once it is open, rejects on error or timeout. */
export function probeVncWebsocket(
  websocketUrl: string,
  timeoutMs: number = VNC_CONNECT_TIMEOUT_MS,
  factory: (url: string) => WebSocket = (url) => new WebSocket(url),
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const socket = factory(websocketUrl)
    const timer = setTimeout(() => { socket.close(); reject(new Error('timeout')) }, timeoutMs)
    socket.onopen = () => { clearTimeout(timer); socket.close(); resolve() }
    socket.onerror = () => { clearTimeout(timer); reject(new Error('connection failed')) }
  })
}
