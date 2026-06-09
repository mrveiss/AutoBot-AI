// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import ThreatIntelligenceDashboard from './ThreatIntelligenceDashboard.vue';

const meta = {
  title: 'Components/Security/ThreatIntelligenceDashboard',
  component: ThreatIntelligenceDashboard,
  argTypes: {},
} as Meta<typeof ThreatIntelligenceDashboard>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { ThreatIntelligenceDashboard },
    template: '<ThreatIntelligenceDashboard />',
  }),
};

export const InPanel: Story = {
  render: () => ({
    components: { ThreatIntelligenceDashboard },
    template: `
      <div style="max-width: 1200px; padding: 1rem;">
        <ThreatIntelligenceDashboard />
      </div>
    `,
  }),
};

export const Compact: Story = {
  render: () => ({
    components: { ThreatIntelligenceDashboard },
    template: `
      <div style="max-width: 800px; padding: 1rem;">
        <ThreatIntelligenceDashboard />
      </div>
    `,
  }),
};
