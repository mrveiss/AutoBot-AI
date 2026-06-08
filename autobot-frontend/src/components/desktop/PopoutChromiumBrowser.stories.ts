// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3';
import PopoutChromiumBrowser from './PopoutChromiumBrowser.vue';

const meta = {
  title: 'Components/Desktop/PopoutChromiumBrowser',
  component: PopoutChromiumBrowser,
  tags: ['autodocs'],
  argTypes: {
    sessionId: {
      control: 'text',
      description:
        'Browser session identifier. Pass "manual-browser" to show the launch-session ' +
        'empty state; any other non-empty value triggers Playwright session initialization.',
    },
    initialUrl: {
      control: 'text',
      description: 'Starting URL loaded into the address bar on mount.',
    },
    canResize: {
      control: 'boolean',
      description: 'Enables ResizeObserver for responsive layout adjustments.',
    },
    autoPopout: {
      control: 'boolean',
      description: 'When true the browser pops out of the panel automatically on mount.',
    },
  },
  parameters: {
    docs: {
      description: {
        component:
          'Headed Chromium browser panel backed by Playwright automation. Renders a VNC ' +
          'iframe for live browser display, an address bar with navigation controls, a ' +
          'Playwright automation panel (web search, frontend tests, test messages), and a ' +
          'developer tools console overlay.',
      },
    },
    layout: 'fullscreen',
  },
} as Meta<typeof PopoutChromiumBrowser>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<any>;

/**
 * Manual browser mode — sessionId = "manual-browser" shows the empty state with a
 * "Launch Session" button and no VNC iframe.
 */
export const ManualBrowserMode: Story = {
  args: {
    sessionId: 'manual-browser',
    initialUrl: 'about:blank',
    canResize: true,
    autoPopout: false,
  },
  render: (args: any) => ({
    components: { PopoutChromiumBrowser },
    setup() { return { args } },
    template: `<div style="height:600px"><PopoutChromiumBrowser v-bind="args" @close="() => {}" /></div>`,
  }),
};

/**
 * Active session — triggers Playwright connection flow. In Storybook (no backend) the
 * component will reach the error state showing the retry button.
 */
export const ActiveSession: Story = {
  args: {
    sessionId: 'session-abc12345',
    initialUrl: 'https://example.com',
    canResize: true,
    autoPopout: false,
  },
  render: (args: any) => ({
    components: { PopoutChromiumBrowser },
    setup() { return { args } },
    template: `<div style="height:600px"><PopoutChromiumBrowser v-bind="args" @close="() => {}" /></div>`,
  }),
};

/**
 * HTTPS secure URL — the lock icon in the address bar should be visible.
 */
export const SecureUrl: Story = {
  args: {
    sessionId: 'session-secure',
    initialUrl: 'https://anthropic.com',
    canResize: true,
    autoPopout: false,
  },
  render: (args: any) => ({
    components: { PopoutChromiumBrowser },
    setup() { return { args } },
    template: `<div style="height:600px"><PopoutChromiumBrowser v-bind="args" @close="() => {}" /></div>`,
  }),
};

/**
 * Non-resizable variant — ResizeObserver is disabled; layout is fixed.
 */
export const NonResizable: Story = {
  args: {
    sessionId: 'session-fixed',
    initialUrl: 'about:blank',
    canResize: false,
    autoPopout: false,
  },
  render: (args: any) => ({
    components: { PopoutChromiumBrowser },
    setup() { return { args } },
    template: `<div style="height:500px;width:800px"><PopoutChromiumBrowser v-bind="args" @close="() => {}" /></div>`,
  }),
};

/**
 * Compact embedding — demonstrates the browser at a smaller container size used in
 * split-pane research layouts.
 */
export const CompactEmbedded: Story = {
  args: {
    sessionId: 'manual-browser',
    initialUrl: 'about:blank',
    canResize: false,
    autoPopout: false,
  },
  render: (args: any) => ({
    components: { PopoutChromiumBrowser },
    setup() { return { args } },
    template: `<div style="height:400px;width:640px"><PopoutChromiumBrowser v-bind="args" @close="() => {}" /></div>`,
  }),
};
