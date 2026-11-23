// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { beforeEach, describe, expect, it } from 'vitest'
import { withCompanyScope } from '@/utils/buildAuthenticatedWsUrl'

const COMPANY = '11111111-1111-4111-8111-111111111111'

describe('withCompanyScope (#21997)', () => {
  beforeEach(() => localStorage.clear())

  it('leaves the URL alone when no company is selected', () => {
    expect(withCompanyScope('ws://h/api/ws/live')).toBe('ws://h/api/ws/live')
  })

  it('names the selected company in the query, since a browser socket cannot set a header', () => {
    localStorage.setItem('autobot-llc-company', JSON.stringify({ selectedCompanyId: COMPANY }))
    expect(withCompanyScope('ws://h/api/ws/live')).toBe(`ws://h/api/ws/live?company_id=${COMPANY}`)
    expect(withCompanyScope('ws://h/x?a=1')).toBe(`ws://h/x?a=1&company_id=${COMPANY}`)
  })

  it('does not overwrite a company the URL already names', () => {
    localStorage.setItem('autobot-llc-company', JSON.stringify({ selectedCompanyId: COMPANY }))
    expect(withCompanyScope('ws://h/x?company_id=other')).toBe('ws://h/x?company_id=other')
  })
})
