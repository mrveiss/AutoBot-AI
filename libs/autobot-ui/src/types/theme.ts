// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * One installed theme, as `GET /api/themes` describes it. Both apps read this list -- the main
 * app directly, the SLM through its proxy -- so the shape is declared once, here (#14908).
 */
export interface InstalledTheme {
  id: string
  name: string
  author: string
  version: string
  supports: string[]
}
