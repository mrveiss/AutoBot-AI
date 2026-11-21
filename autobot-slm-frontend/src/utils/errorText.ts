// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** A caught value's message: the original error text, never a hard-coded English fallback. */
export const errorText = (err: unknown): string => (err instanceof Error ? err.message : String(err))
