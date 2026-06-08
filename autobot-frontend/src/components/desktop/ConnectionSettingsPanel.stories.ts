// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3';
import ConnectionSettingsPanel from './ConnectionSettingsPanel.vue';

const meta = {
  title: 'Components/Desktop/ConnectionSettingsPanel',
  component: ConnectionSettingsPanel,
  tags: ['autodocs'],
  argTypes: {},
  parameters: {
    docs: {
      description: {
        component:
          'Displays VNC connection settings including quality presets, auto-reconnect ' +
          'configuration, and live connection metrics. All data is fetched via ' +
          'useVncConnection and polled every 10 seconds.',
      },
    },
  },
} as Meta<typeof ConnectionSettingsPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<any>;

/**
 * Default state: the component mounts, loads settings and begins metrics polling.
 * In Storybook the composable will return its initial values (settings = null → loading state).
 */
export const Default: Story = {
  render: () => ({
    components: { ConnectionSettingsPanel },
    template: `<div style="width:320px"><ConnectionSettingsPanel /></div>`,
  }),
};

/**
 * Shows what the panel looks like while settings are still being fetched
 * (mocked by rendering the component in an isolated container where the
 * composable returns its initial null state).
 */
export const LoadingState: Story = {
  render: () => ({
    components: { ConnectionSettingsPanel },
    template: `
      <div style="width:320px">
        <p class="text-xs text-gray-400 mb-2">Loading state (composable returns null on first render)</p>
        <ConnectionSettingsPanel />
      </div>
    `,
  }),
};

/**
 * Demonstrates the panel at a narrow sidebar width.
 */
export const NarrowSidebar: Story = {
  render: () => ({
    components: { ConnectionSettingsPanel },
    template: `<div style="width:240px"><ConnectionSettingsPanel /></div>`,
  }),
};

/**
 * Demonstrates the panel at a wider layout (e.g. a settings drawer).
 */
export const WideLayout: Story = {
  render: () => ({
    components: { ConnectionSettingsPanel },
    template: `<div style="width:480px"><ConnectionSettingsPanel /></div>`,
  }),
};

/**
 * Shows the panel inside a dark-themed wrapper that mirrors the sidebar context.
 */
export const DarkSidebar: Story = {
  render: () => ({
    components: { ConnectionSettingsPanel },
    template: `
      <div style="width:320px;background:#1a1a2e;padding:16px;border-radius:8px">
        <ConnectionSettingsPanel />
      </div>
    `,
  }),
};
