// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Scheduler Toggles API Client
 *
 * Type-safe access to the scheduler operator-toggle admin API.
 * Issue #12820: let an operator turn background jobs on or off without a redeploy.
 *
 * Base-URL resolution, auth-token injection, 401 handling and org-context headers all
 * live on the shared apiClient singleton (#12152); this is a thin typed wrapper. Its
 * methods return parsed JSON and throw on failure — callers handle the error.
 */

import apiClient from '@/utils/ApiClient';
import { getApiBase } from '@/config/ssot-config';

/** One background job's registry metadata plus its resolved state. */
export interface SchedulerState {
  name: string;
  /** What the job actually does right now: the override if set, else the default. */
  enabled: boolean;
  /** Declared default — what applies when no operator override exists. */
  default_enabled: boolean;
  /** True when an operator override is stored, i.e. `enabled` may differ from the default. */
  override_active: boolean;
  interval_seconds: number | string;
  owner_file: string;
  runtime: string;
  description: string;
  /** Set when the job deliberately does not run; cites a tracking issue. */
  inert_reason: string | null;
}

export interface SchedulerListResponse {
  schedulers: SchedulerState[];
}

export interface SchedulerToggleResult {
  name: string;
  enabled: boolean;
  override_active: boolean;
}

/**
 * Every registered scheduler with its effective state.
 * GET /api/admin/schedulers
 */
export async function listSchedulers(): Promise<SchedulerListResponse> {
  return apiClient.get<SchedulerListResponse>(`${getApiBase()}/admin/schedulers`);
}

/**
 * Override a scheduler's state. Takes effect on the job's next cycle.
 * PUT /api/admin/schedulers/{name}
 */
export async function setScheduler(name: string, enabled: boolean): Promise<SchedulerToggleResult> {
  return apiClient.put<SchedulerToggleResult>(
    `${getApiBase()}/admin/schedulers/${encodeURIComponent(name)}`,
    { enabled }
  );
}

/**
 * Clear the override so the scheduler reverts to its registry default.
 * DELETE /api/admin/schedulers/{name}
 */
export async function resetScheduler(name: string): Promise<SchedulerToggleResult> {
  return apiClient.delete<SchedulerToggleResult>(
    `${getApiBase()}/admin/schedulers/${encodeURIComponent(name)}`
  );
}

export default { listSchedulers, setScheduler, resetScheduler };
