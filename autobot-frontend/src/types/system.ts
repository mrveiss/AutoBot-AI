// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// System Status Types
export type SystemSeverity = 'info' | 'warning' | 'error' | 'success';

export interface SystemStatusDetails {
  status: string;
  lastCheck: number;
  consecutiveFailures?: number;
  error?: string;
  timestamp: number;
}

export interface SystemAlert {
  id: string;
  severity: SystemSeverity;
  title: string;
  message: string;
  visible: boolean;
  statusDetails?: SystemStatusDetails;
  timestamp: number;
}

// #15401: this was a drifted copy of `types/api.ts`'s service-health row -- a
// narrower status union, number-only timestamps -- under a name that also
// collided with the SLM's `ServiceHealth`. It had no importers. The canonical row
// is `ServiceHealthEntry`, whose fields are a superset of this one's.
export type { ServiceHealthEntry } from './api'
