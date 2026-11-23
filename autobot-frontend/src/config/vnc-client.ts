// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * noVNC client URL and probe settings for the chat Desktop (#22144).
 *
 * The live websockify runs --ssl-only, so the scheme defaults to https; the port
 * default is the SSOT `vnc.desktop.port`. Nothing here is a literal at a call site.
 */

import { getEnvPositiveInt } from '@autobot/ui'
import { getConfig } from '@/config/ssot-config'

/** Path of the noVNC client page on a websockify host. */
export const VNC_CLIENT_PATH: string = import.meta.env.VITE_VNC_CLIENT_PATH || '/vnc.html'

/** Scheme noVNC is served on; websockify is --ssl-only. */
export const VNC_CLIENT_SCHEME: string = import.meta.env.VITE_VNC_CLIENT_SCHEME || 'https'

/** Query string that makes the embedded client connect on load. */
export const VNC_CLIENT_QUERY: string = import.meta.env.VITE_VNC_CLIENT_QUERY || 'autoconnect=true'

/** How long a reachability probe of a VNC host may take (ms). */
export const VNC_PROBE_TIMEOUT_MS: number = getEnvPositiveInt(import.meta.env, 'VITE_VNC_PROBE_TIMEOUT_MS', 5000)

export interface VncClientHost {
  host: string
  vnc_port?: number | null
}

/** noVNC web port for a host: its own port when set, else the SSOT desktop port. */
export function getVncClientPort(h: VncClientHost): number {
  return h.vnc_port || getConfig().vnc.desktop.port
}

/** Base URL (scheme, host, port) of a host's noVNC server. */
export function buildVncBaseUrl(h: VncClientHost): string {
  return `${VNC_CLIENT_SCHEME}://${h.host}:${getVncClientPort(h)}`
}

/** Full noVNC client URL for a host, autoconnecting. */
export function buildVncClientUrl(h: VncClientHost): string {
  return `${buildVncBaseUrl(h)}${VNC_CLIENT_PATH}?${VNC_CLIENT_QUERY}`
}
