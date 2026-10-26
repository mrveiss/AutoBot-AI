// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// RiskBadge (#13422): one look per tier, the label always shown, and critical told
// apart from high by more than colour.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RiskBadge from '../RiskBadge.vue'
import { RISK_TIERS } from '../../types/riskTier'

describe('RiskBadge', () => {
  it.each(RISK_TIERS)('renders the %s tier with its label and tier class', (tier) => {
    const w = mount(RiskBadge, { props: { tier, label: `L-${tier}` } })
    expect(w.text()).toBe(`L-${tier}`)
    expect(w.classes()).toContain(`aui-risk-badge--${tier}`)
    expect(w.attributes('data-risk-tier')).toBe(tier)
  })

  it('maps the tiers onto the semantic badge variants', () => {
    const variant = (tier: (typeof RISK_TIERS)[number]) =>
      mount(RiskBadge, { props: { tier, label: tier } }).classes().find((c) => /^aui-badge--(success|warning|error)$/.test(c))
    expect(RISK_TIERS.map(variant)).toEqual(['aui-badge--success', 'aui-badge--warning', 'aui-badge--error', 'aui-badge--error'])
  })

  it('fills critical solid and high subtle, so they differ beyond hue', () => {
    expect(mount(RiskBadge, { props: { tier: 'critical', label: 'c' } }).classes()).toContain('aui-badge--solid')
    expect(mount(RiskBadge, { props: { tier: 'high', label: 'h' } }).classes()).toContain('aui-badge--subtle')
  })
})
