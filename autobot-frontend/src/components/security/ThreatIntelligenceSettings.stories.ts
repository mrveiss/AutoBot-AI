// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import ThreatIntelligenceSettings from './ThreatIntelligenceSettings.vue';

const meta = {
  title: 'Components/Security/ThreatIntelligenceSettings',
  component: ThreatIntelligenceSettings,
  argTypes: {},
} as Meta<typeof ThreatIntelligenceSettings>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { ThreatIntelligenceSettings },
    template: '<ThreatIntelligenceSettings />',
  }),
};

export const InSettingsPanel: Story = {
  render: () => ({
    components: { ThreatIntelligenceSettings },
    template: `
      <div style="max-width: 900px; padding: 1.5rem; background: #f9fafb; border-radius: 8px;">
        <ThreatIntelligenceSettings />
      </div>
    `,
  }),
};

export const Narrow: Story = {
  render: () => ({
    components: { ThreatIntelligenceSettings },
    template: `
      <div style="max-width: 600px;">
        <ThreatIntelligenceSettings />
      </div>
    `,
  }),
};
