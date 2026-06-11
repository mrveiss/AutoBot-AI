// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Unit tests for the shared LLC status mappings (#9909).
 */

import { describe, it, expect } from 'vitest'
import {
  agentStatusColor,
  companyStatusColor,
  runStatusToAgentStatus,
  runStatusToRunDisplayStatus,
} from '../llcStatus'

describe('agentStatusColor', () => {
  it.each([
    ['active', 'bg-green-500'],
    ['idle', 'bg-yellow-400'],
    ['error', 'bg-red-500'],
    ['paused', 'bg-gray-400'],
    ['unknown', 'bg-gray-400'],
  ])('maps %s → %s', (status, expected) => {
    expect(agentStatusColor(status)).toBe(expected)
  })
})

describe('companyStatusColor', () => {
  it.each([
    ['active', 'bg-green-500'],
    ['paused', 'bg-yellow-400'],
    ['inactive', 'bg-gray-400'],
    ['unknown', 'bg-gray-400'],
  ])('maps %s → %s', (status, expected) => {
    expect(companyStatusColor(status)).toBe(expected)
  })

  it('differs from agentStatusColor for paused (yellow vs gray)', () => {
    expect(companyStatusColor('paused')).toBe('bg-yellow-400')
    expect(agentStatusColor('paused')).toBe('bg-gray-400')
  })
})

describe('runStatusToAgentStatus', () => {
  it.each([
    ['running', 'active'],
    ['failed', 'error'],
    ['timeout', 'error'],
    ['interrupted', 'error'],
    ['completed', 'idle'],
    [null, 'idle'],
  ])('maps %s → %s', (raw, expected) => {
    expect(runStatusToAgentStatus(raw as string | null)).toBe(expected)
  })
})

describe('runStatusToRunDisplayStatus', () => {
  it.each([
    ['completed', 'done'],
    ['running', 'running'],
    ['failed', 'failed'],
    ['timeout', 'failed'],
    ['anything-else', 'failed'],
  ])('maps %s → %s', (raw, expected) => {
    expect(runStatusToRunDisplayStatus(raw)).toBe(expected)
  })
})
