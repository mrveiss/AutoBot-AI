// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta } from '@storybook/vue3';
import DesktopContextPanel from './DesktopContextPanel.vue';

const meta = {
  title: 'Components/Desktop/DesktopContextPanel',
  component: DesktopContextPanel,
  tags: ['autodocs'],
  argTypes: {},
  parameters: {
    docs: {
      description: {
        component:
          'Displays live desktop context information: system metrics (CPU, memory, uptime), ' +
          'desktop state (resolution, active window, window count), and top running processes. ' +
          'Data is polled from /vnc/desktop/context every 5 seconds with a manual refresh button.',
      },
    },
  },
} as Meta<typeof DesktopContextPanel>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<Record<string, unknown>>;

/**
 * Default render — composable starts with context = null so the loading skeleton is shown.
 */
export const Default: Story = {
  render: () => ({
    components: { DesktopContextPanel },
    template: `<div style="width:320px"><DesktopContextPanel /></div>`,
  }),
};

/**
 * Narrow sidebar width, mirroring how the panel appears in the desktop slide-out.
 */
export const NarrowSidebar: Story = {
  render: () => ({
    components: { DesktopContextPanel },
    template: `<div style="width:240px"><DesktopContextPanel /></div>`,
  }),
};

/**
 * Wider layout — useful for full-page settings or inspection dashboards.
 */
export const WideLayout: Story = {
  render: () => ({
    components: { DesktopContextPanel },
    template: `<div style="width:480px"><DesktopContextPanel /></div>`,
  }),
};

/**
 * Two panels side-by-side to verify they lay out independently.
 */
export const SideBySide: Story = {
  render: () => ({
    components: { DesktopContextPanel },
    template: `
      <div style="display:flex;gap:16px">
        <div style="width:300px"><DesktopContextPanel /></div>
        <div style="width:300px"><DesktopContextPanel /></div>
      </div>
    `,
  }),
};

/**
 * Dark background — matches the desktop overlay context.
 */
export const DarkBackground: Story = {
  render: () => ({
    components: { DesktopContextPanel },
    template: `
      <div style="width:320px;background:#111827;padding:16px;border-radius:8px">
        <DesktopContextPanel />
      </div>
    `,
  }),
};
