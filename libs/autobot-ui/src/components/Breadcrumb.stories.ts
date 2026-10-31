// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import Breadcrumb from './Breadcrumb.vue'

const meta = {
  title: 'Kit/Breadcrumb',
  component: Breadcrumb,
} as Meta<typeof Breadcrumb>

export default meta
type Story = StoryObj<typeof meta>

export const ThreeLevels: Story = {
  args: {
    label: 'Breadcrumb',
    items: [
      { label: 'Portfolios', to: '#portfolios' },
      { label: 'Platform', to: '#platform' },
      { label: 'Release 2' },
    ],
  },
}

export const SingleLevel: Story = {
  args: { label: 'Breadcrumb', items: [{ label: 'Portfolios' }] },
}
