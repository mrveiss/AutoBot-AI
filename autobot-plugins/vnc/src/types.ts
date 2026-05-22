// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

export interface VncHost {
  id: string
  name: string
  host: string
  port: number
  description?: string
  /** If true, an nginx proxy exists for this host so it can be embedded. Default: id === 'main' */
  proxied?: boolean
}
