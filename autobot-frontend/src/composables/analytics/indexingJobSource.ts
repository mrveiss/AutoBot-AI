// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * One indexing job runs at a time across all sources, so the current job may be another source's
 * (#20491). A job that names no source, or a page with none selected, cannot be told apart.
 */
export function jobBelongsToSource(jobSourceId?: string | null, selectedId?: string): boolean {
  return !jobSourceId || !selectedId || jobSourceId === selectedId
}
