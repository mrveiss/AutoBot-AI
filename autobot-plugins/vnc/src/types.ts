// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform

export interface VncHost {
  id: string
  name: string
  host: string
  port: number
  description?: string
  /** If true, an nginx proxy exists for this host so it can be embedded. Default: id === 'main' */
  proxied?: boolean
}
