// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3';
import DesktopInterface from './DesktopInterface.vue';
import type { SelectorHost } from '@/composables/useHostSelector';

const meta = {
  title: 'Components/Desktop/DesktopInterface',
  component: DesktopInterface,
  tags: ['autodocs'],
  argTypes: {
    host: {
      control: 'object',
      description:
        'Optional SelectorHost record. When provided the VNC URL is derived directly ' +
        'from host.host + host.vnc_port instead of loading from AppConfig.',
    },
  },
  parameters: {
    docs: {
      description: {
        component:
          'Full-featured desktop streaming interface wrapping an iframe VNC session. ' +
          'Includes connection controls (fullscreen, reconnect, open in new window), ' +
          'desktop action toolbar (screenshot, type text, Ctrl+Alt+Del, clipboard paste), ' +
          'and an optional collapsible DesktopContextPanel overlay.',
      },
    },
    layout: 'fullscreen',
  },
} as Meta<typeof DesktopInterface>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = import('@storybook/vue3').StoryObj<any>;

/**
 * Default — no host prop; the component attempts to load the VNC URL from AppConfig.
 * In Storybook (no backend), it will land in the error/config-failure state showing the
 * error UI and Reconnect button.
 */
export const Default: Story = {
  args: {
    host: null,
  },
  render: (args: any) => ({
    components: { DesktopInterface },
    setup() { return { args } },
    template: `<div style="height:600px"><DesktopInterface v-bind="args" /></div>`,
  }),
};

/**
 * With a host record injected — the component derives the VNC URL directly without
 * hitting AppConfig. The iframe will load (or show an error if the host is unreachable).
 * Replace host values with a real VM host when testing against a live environment.
 */
export const WithHostProp: Story = {
  args: {
    host: {
      host: 'desktop-vm.local',
      vnc_port: 6080,
      label: 'Frontend VM',
    } satisfies Partial<SelectorHost>,
  },
  render: (args: any) => ({
    components: { DesktopInterface },
    setup() { return { args } },
    template: `<div style="height:600px"><DesktopInterface v-bind="args" /></div>`,
  }),
};

/**
 * Compact height — shows how the layout adapts in a split-pane or panel context.
 */
export const CompactHeight: Story = {
  args: { host: null },
  render: (args: any) => ({
    components: { DesktopInterface },
    setup() { return { args } },
    template: `<div style="height:360px"><DesktopInterface v-bind="args" /></div>`,
  }),
};

/**
 * Tall layout — full page display.
 */
export const TallLayout: Story = {
  args: { host: null },
  render: (args: any) => ({
    components: { DesktopInterface },
    setup() { return { args } },
    template: `<div style="height:900px"><DesktopInterface v-bind="args" /></div>`,
  }),
};

/**
 * Custom VM host — demonstrates changing the target VM at runtime.
 * Replace host/port with actual values when using against a live environment.
 */
export const CustomVmHost: Story = {
  args: {
    host: {
      host: 'worker-vm.local',
      vnc_port: 6081,
      label: 'Worker VM',
    } satisfies Partial<SelectorHost>,
  },
  render: (args: any) => ({
    components: { DesktopInterface },
    setup() { return { args } },
    template: `<div style="height:600px"><DesktopInterface v-bind="args" /></div>`,
  }),
};
