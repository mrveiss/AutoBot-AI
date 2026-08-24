// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Tests for the canonical risk-level normalization helper (#14955).
 *
 * The producer vocabulary asserted here is
 * `autobot-backend/models/command_execution.py::RiskLevel` — uppercase
 * `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`, confirmed serialized as-is by
 * `CommandExecution.to_dict()` and `api/agent_terminal.py`'s command
 * status response. `MODERATE`/`DANGEROUS`/`FORBIDDEN` are members of the
 * separate `CommandRisk` enum, which is converted to the vocabulary above
 * at the backend boundary (`services/agent_terminal/utils.py::
 * map_risk_to_level`) and never reaches this call site — they must not
 * resolve to a severity here.
 */

import { describe, it, expect } from 'vitest'
import { getRiskSeverity } from '@/utils/riskLevel'

describe('getRiskSeverity', () => {
  it('maps every producer-emitted RiskLevel value to its severity bucket', () => {
    expect(getRiskSeverity('LOW')).toBe('low')
    expect(getRiskSeverity('MEDIUM')).toBe('medium')
    expect(getRiskSeverity('HIGH')).toBe('high')
    expect(getRiskSeverity('CRITICAL')).toBe('critical')
  })

  it('is case-insensitive, since some call sites lowercase before rendering', () => {
    expect(getRiskSeverity('critical')).toBe('critical')
    expect(getRiskSeverity('Medium')).toBe('medium')
  })

  it('does not resolve vocabulary from the unrelated CommandRisk enum', () => {
    expect(getRiskSeverity('MODERATE')).toBeNull()
    expect(getRiskSeverity('DANGEROUS')).toBeNull()
    expect(getRiskSeverity('FORBIDDEN')).toBeNull()
    expect(getRiskSeverity('SAFE')).toBeNull()
  })

  it('returns null for missing input', () => {
    expect(getRiskSeverity(undefined)).toBeNull()
    expect(getRiskSeverity(null)).toBeNull()
    expect(getRiskSeverity('')).toBeNull()
  })
})
