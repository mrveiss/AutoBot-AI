// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Type definitions for ClearNotifications utility
 */

export function clearAllSystemNotifications(): Promise<boolean>;
export function resetHealthMonitor(): Promise<boolean>;

export interface ClearNotificationsModule {
  clearAllSystemNotifications: typeof clearAllSystemNotifications;
  resetHealthMonitor: typeof resetHealthMonitor;
}

declare const clearNotifications: ClearNotificationsModule;
export default clearNotifications;
