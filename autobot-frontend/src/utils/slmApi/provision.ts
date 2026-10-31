// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `slmApi` provisioning read (#19834, #7096): GET `/setup/provision-status`.
 * The contract leaves the 200 body undeclared (`unknown`), so its shape is stated here, once.
 */
import { slmRequestAs } from './transport'

export interface ProvisionStatusResult {
  status: string
  lines: string[]
  total_lines: number
  error: string | null
  elapsed_seconds?: number
}

export async function getProvisionStatus(sinceLine: number = 0): Promise<ProvisionStatusResult> {
  return slmRequestAs<ProvisionStatusResult, '/api/setup/provision-status', 'get'>(
    'get',
    '/api/setup/provision-status',
    { query: { since_line: sinceLine } },
  )
}
