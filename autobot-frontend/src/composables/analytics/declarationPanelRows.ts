// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Declaration } from './analyticsTypes'

/**
 * The declarations panel's rows, derived from the loaded declarations. The
 * section export reads the same loaded list (#20492), so the two cannot hold
 * different data.
 */
export function toDeclarationPanelRows(declarations: readonly Declaration[]) {
  return declarations.map((d) => ({
    name: d.name,
    file_path: d.file_path,
    line_number: d.line_number ?? d.line ?? 0,
    is_exported: d.is_exported ?? false,
    declaration_type: d.type,
  }))
}
