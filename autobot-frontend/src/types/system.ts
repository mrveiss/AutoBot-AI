// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// System Status Types: the one home of the notification shapes (#16253). The store and
// SystemStatusNotification import these; there are no other copies.
export type SystemSeverity = 'info' | 'warning' | 'error' | 'success';

export interface SystemStatusDetails {
  status: string;
  lastCheck: number;
  consecutiveFailures?: number;
  error?: string;
  timestamp: number;
}

/** A system notification as the store keeps it and SystemStatusNotification shows it (#16253). */
export interface SystemNotification {
  id: string;
  severity: SystemSeverity;
  title: string;
  message: string;
  visible: boolean;
  statusDetails?: SystemStatusDetails;
  timestamp: number;
}
