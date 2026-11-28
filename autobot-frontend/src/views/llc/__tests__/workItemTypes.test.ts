// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21032: the label mapping of the type and priority pickers resolves to real `llc.enums` strings.

import { describe, it, expect } from 'vitest'
import en from '@/i18n/locales/en.json'
import { PRIORITIES, WORK_ITEM_TYPES } from '../workItemTypes'

function resolve(key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en)
}

describe('workItemTypes label mapping', () => {
  it.each([...WORK_ITEM_TYPES, ...PRIORITIES])('maps $value to an existing English label', ({ value, labelKey }) => {
    const label = resolve(labelKey)
    expect(typeof label).toBe('string')
    expect((label as string).length).toBeGreaterThan(0)
    expect(labelKey.endsWith(`.${value}`)).toBe(true)
  })

  it('offers each closed-union member exactly once', () => {
    expect(WORK_ITEM_TYPES.map(t => t.value).sort()).toEqual(
      ['bug', 'epic', 'feature', 'pbi', 'risk', 'spike', 'subtask', 'task'],
    )
    expect(PRIORITIES.map(p => p.value).sort()).toEqual(['critical', 'high', 'low', 'medium'])
  })

  it('has an llc.enums label for every offered value and none left over', () => {
    const types = Object.keys(resolve('llc.enums.workItemType') as object).sort()
    const priorities = Object.keys(resolve('llc.enums.priority') as object).sort()
    expect(types).toEqual(WORK_ITEM_TYPES.map(t => t.value).sort())
    expect(priorities).toEqual(PRIORITIES.map(p => p.value).sort())
  })
})
