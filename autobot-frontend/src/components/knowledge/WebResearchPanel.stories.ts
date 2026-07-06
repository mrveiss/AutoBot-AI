// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// Storybook story for WebResearchPanel (MVA-344)

import type { Meta } from '@storybook/vue3'
import WebResearchPanel from './WebResearchPanel.vue'

const meta = {
  title: 'Components/Knowledge/WebResearchPanel',
  component: WebResearchPanel,
  parameters: {
    docs: {
      description: {
        component:
          '4-tab web research panel at /knowledge/web-research. Tabs: Fetch Page, Crawl Site, Find Pages, Get Data.',
      },
    },
  },
} as Meta<typeof WebResearchPanel>

export default meta

// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Story = import('@storybook/vue3').StoryObj<Record<string, unknown>>

export const Default: Story = {
  render: () => ({
    components: { WebResearchPanel },
    template: `
      <div style="height: 600px; background: var(--bg-primary, #0d0d0d); display: flex; flex-direction: column;">
        <WebResearchPanel />
      </div>
    `,
  }),
}

export const FetchPageTab: Story = {
  name: 'Fetch Page tab',
  render: () => ({
    components: { WebResearchPanel },
    template: `
      <div style="height: 600px; background: var(--bg-primary, #0d0d0d); display: flex; flex-direction: column;">
        <WebResearchPanel />
      </div>
    `,
  }),
}

export const InLightBackground: Story = {
  render: () => ({
    components: { WebResearchPanel },
    template: `
      <div style="height: 600px; background: #ffffff; display: flex; flex-direction: column;">
        <WebResearchPanel />
      </div>
    `,
  }),
}
