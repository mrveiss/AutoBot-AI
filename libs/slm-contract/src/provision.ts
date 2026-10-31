// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM contract types: fleet provisioning (#7096). The vocabulary of the provision store, declared
 * once here so the SLM app's store and the main app's store (#19834) share it.
 */

export type ProvisionStatus = 'idle' | 'running' | 'completed' | 'failed'

export interface ProvisionLogEntry {
  type: 'info' | 'task' | 'success' | 'error' | 'warning' | 'phase'
  message: string
}
