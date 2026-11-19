// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// RiskBadge (#13422): every tier at every size. Each story is a visual-regression
// subject; check the ladder in each theme variant, not only the default.
import type { Meta, StoryObj } from '@storybook/vue3'
import RiskBadge from './RiskBadge.vue'
import { RISK_TIERS } from '../types/riskTier'

const meta = {
  title: 'Kit/RiskBadge',
  component: RiskBadge,
  argTypes: {
    tier: { control: 'select', options: [...RISK_TIERS] },
    size: { control: 'select', options: ['xs', 'sm', 'md', 'lg'] },
    label: { control: 'text' },
  },
  args: { tier: 'high', label: 'High', size: 'sm' },
} satisfies Meta<typeof RiskBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

/** The whole ladder side by side: the comparison an operator relies on. */
export const Ladder: Story = {
  render: () => ({
    components: { RiskBadge },
    setup: () => ({ tiers: RISK_TIERS }),
    template: `<div style="display:flex;gap:8px">
      <RiskBadge v-for="t in tiers" :key="t" :tier="t" :label="t.charAt(0).toUpperCase() + t.slice(1)" />
    </div>`,
  }),
}
