// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Frontend probe-name constants — single source of truth (Issue #6917).
 *
 * These values mirror `KnownProbes` in `autobot-backend/api/system_health.py`.
 * When adding a new probe, update BOTH files and keep the string values in sync.
 *
 * Usage:
 *   import { PROBE_NAMES } from '@/types/probe-names'
 *   probeName: PROBE_NAMES.BATCH_JOBS
 */

export const PROBE_NAMES = {
  BATCH_JOBS: 'batch_jobs',
  LONG_RUNNING: 'long_running',
  KNOWLEDGE: 'knowledge',
  ERROR_RESILIENCE: 'error_resilience',
  INTELLIGENT_AGENT: 'intelligent_agent',
  CONTENT_REACH: 'content_reach',
} as const

export type ProbeName = (typeof PROBE_NAMES)[keyof typeof PROBE_NAMES]
