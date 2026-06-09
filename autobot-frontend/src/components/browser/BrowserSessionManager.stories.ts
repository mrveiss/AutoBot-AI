// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta, StoryObj } from '@storybook/vue3';
import BrowserSessionManager from './BrowserSessionManager.vue';
import { getConfig } from '@/config/ssot-config';
const config = getConfig();

const meta = {
  title: 'Components/Browser/BrowserSessionManager',
  component: BrowserSessionManager,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof BrowserSessionManager>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

/**
 * BrowserSessionManager is a self-contained component that fetches live
 * browser session data from the AutoBot backend via useBrowserAutomation().
 * It has no props — all state is managed internally.
 *
 * In a real environment the component renders a full session dashboard with stats cards,
 * sortable session cards, and a create-session modal.
 */
export const Default: Story = {
  render: () => ({
    template: `
      <div style="padding: 20px; background: #f5f5f5; border-radius: 8px; font-family: sans-serif;">
        <p style="margin: 0 0 8px; font-weight: 600; color: #374151;">
          BrowserSessionManager
        </p>
        <p style="margin: 0; color: #6b7280; font-size: 14px;">
          Requires backend API connection (${config.vm.main}:${config.port.backend}).
          Renders session stats, sortable session cards, pause/resume/delete actions,
          and a create-session modal when connected.
        </p>
      </div>
    `,
  }),
};
