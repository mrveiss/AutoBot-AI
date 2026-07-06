// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import AgentSettingsPanel from './AgentSettingsPanel.vue';

const meta = {
  title: 'Components/Agents/AgentSettingsPanel',
  component: AgentSettingsPanel,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Runtime agent configuration panel. Self-contained — fetches and persists settings ' +
          'via ApiClient (/api/settings). Requires a running AutoBot backend to load or save data. ' +
          'In Storybook the panel renders immediately with its built-in defaults when the API call ' +
          'fails (the loading spinner resolves to the form).',
      },
    },
  },
} as Meta<typeof AgentSettingsPanel>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
 
type Story = { render?: () => unknown; decorators?: unknown[]; parameters?: unknown };

/** Default view — panel loads with built-in defaults (API call fails gracefully in Storybook). */
export const Default: Story = {
  render: () => ({
    components: { AgentSettingsPanel },
    template: '<AgentSettingsPanel />',
  }),
};

/** Panel in a constrained-width container, matching typical settings tab usage. */
export const NarrowContainer: Story = {
  render: () => ({
    components: { AgentSettingsPanel },
    template: `
      <div style="max-width: 600px; padding: 1rem;">
        <AgentSettingsPanel />
      </div>
    `,
  }),
};

/** Panel in a full-width layout, matching the desktop settings page. */
export const WideContainer: Story = {
  render: () => ({
    components: { AgentSettingsPanel },
    template: `
      <div style="max-width: 1200px; padding: 1.5rem;">
        <AgentSettingsPanel />
      </div>
    `,
  }),
};
