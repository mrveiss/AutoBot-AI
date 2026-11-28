// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform

export interface VncHost {
  id: string
  name: string
  host: string
  port: number
  description?: string
  /** noVNC client page URL, derived by the host app from config or the endpoint API (no literals here). */
  url: string
  /** The endpoint's websocket URL, as the API returned it; what a real connect opens. */
  websocketUrl?: string
  /** True when the client page may be embedded in an iframe; otherwise it opens in a new tab. */
  embeddable?: boolean
}
