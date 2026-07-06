// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import ServiceMessageTimeline from './ServiceMessageTimeline.vue'

const meta = {
  title: 'Components/Visualizations/ServiceMessageTimeline',
  component: ServiceMessageTimeline,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof ServiceMessageTimeline>

export default meta
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>

export const Default: Story = {
  name: 'Default (All Messages)',
  args: {},
}

export const FilteredBySender: Story = {
  name: 'Filtered by Sender',
  render: () => ({
    components: { ServiceMessageTimeline },
    template: `
      <div style="height: 500px; background: var(--bg-primary, #1a1a2e); border-radius: 8px; overflow: hidden;">
        <ServiceMessageTimeline />
      </div>
    `,
  }),
}

export const Compact: Story = {
  name: 'Compact Container',
  render: () => ({
    components: { ServiceMessageTimeline },
    template: `
      <div style="height: 300px; background: var(--bg-primary, #1a1a2e); border-radius: 8px; overflow: hidden;">
        <ServiceMessageTimeline />
      </div>
    `,
  }),
}

export const FullHeight: Story = {
  name: 'Full Height Container',
  render: () => ({
    components: { ServiceMessageTimeline },
    template: `
      <div style="height: 700px; background: var(--bg-primary, #1a1a2e); border-radius: 8px; overflow: hidden;">
        <ServiceMessageTimeline />
      </div>
    `,
  }),
}

export const InPanel: Story = {
  name: 'Inside Dashboard Panel',
  render: () => ({
    components: { ServiceMessageTimeline },
    template: `
      <div style="display: flex; flex-direction: column; gap: 12px; padding: 16px; background: #0f172a; min-height: 500px;">
        <h2 style="color: #e0e0ff; font-size: 14px; margin: 0;">Service Message Audit Trail</h2>
        <div style="flex: 1; background: var(--bg-primary, #1a1a2e); border-radius: 8px; overflow: hidden; min-height: 440px;">
          <ServiceMessageTimeline />
        </div>
      </div>
    `,
  }),
}
