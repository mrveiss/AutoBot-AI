// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import NavOverflowMenu from './NavOverflowMenu.vue';

type SvgFillRule = 'evenodd' | 'nonzero' | 'inherit';

interface NavItem {
  to: string;
  labelKey: string;
  icon?: string;
  iconPaths?: string[];
  iconRule?: SvgFillRule;
  iconStroke?: boolean;
}

const sampleItems: NavItem[] = [
  {
    to: '/knowledge',
    labelKey: 'nav.knowledge',
    icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253',
    iconStroke: true,
  },
  {
    to: '/workflows',
    labelKey: 'nav.workflows',
    icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
    iconStroke: true,
  },
  {
    to: '/research',
    labelKey: 'nav.research',
    icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
    iconStroke: true,
  },
  {
    to: '/settings',
    labelKey: 'nav.settings',
    icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z',
    iconStroke: true,
  },
];

const meta = {
  title: 'Components/Layout/NavOverflowMenu',
  component: NavOverflowMenu,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'Overflow menu used in the primary navigation bar to host secondary nav items that do not fit at smaller viewport widths. Renders a "More" button that opens a teleported dropdown menu with router-links. Closes on outside click, Escape, or item click; repositions on resize.',
      },
    },
  },
  argTypes: {
    items: {
      control: 'object',
      description:
        'Array of NavItem entries. Each item provides `to`, `labelKey` (i18n key), and an SVG path (`icon` or `iconPaths`). Stroke vs filled is controlled by `iconStroke`.',
    },
  },
} as Meta<typeof NavOverflowMenu>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    items: sampleItems,
  },
  render: (args: Record<string, unknown>) => ({
    components: { NavOverflowMenu },
    setup() {
      return { args };
    },
    template: `
      <nav class="bg-autobot-bg-secondary border-b border-autobot-border px-6 py-3 flex items-center gap-3">
        <span class="font-bold mr-4">AutoBot</span>
        <button class="px-3 py-2 rounded-md text-sm font-medium text-autobot-text-primary">Chat</button>
        <button class="px-3 py-2 rounded-md text-sm font-medium text-autobot-text-primary">Agents</button>
        <NavOverflowMenu v-bind="args" />
      </nav>
    `,
  }),
};

export const SingleItem: Story = {
  args: {
    items: [sampleItems[0]],
  },
  parameters: {
    docs: {
      description: {
        story:
          'Edge case: only one overflow item. The "More" button still renders so layout remains stable.',
      },
    },
  },
  render: (args: Record<string, unknown>) => ({
    components: { NavOverflowMenu },
    setup() {
      return { args };
    },
    template: `
      <div class="p-6">
        <NavOverflowMenu v-bind="args" />
      </div>
    `,
  }),
};

export const ManyItems: Story = {
  args: {
    items: [
      ...sampleItems,
      { to: '/system', labelKey: 'nav.system', icon: 'M5 12H3l9-9 9 9h-2M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7M5 12l9-9 9 9', iconStroke: true },
      { to: '/terminal', labelKey: 'nav.terminal', icon: 'M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z', iconStroke: true },
      { to: '/desktop', labelKey: 'nav.desktop', icon: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z', iconStroke: true },
    ],
  },
  parameters: {
    docs: {
      description: {
        story:
          'Larger overflow set — the dropdown grows vertically to accommodate all items.',
      },
    },
  },
  render: (args: Record<string, unknown>) => ({
    components: { NavOverflowMenu },
    setup() {
      return { args };
    },
    template: `
      <div class="p-6">
        <NavOverflowMenu v-bind="args" />
      </div>
    `,
  }),
};

export const Empty: Story = {
  args: {
    items: [],
  },
  parameters: {
    docs: {
      description: {
        story:
          'Empty `items` array — the component renders nothing (the wrapper has `v-if="items.length > 0"`).',
      },
    },
  },
  render: (args: Record<string, unknown>) => ({
    components: { NavOverflowMenu },
    setup() {
      return { args };
    },
    template: `
      <div class="p-6 text-sm text-autobot-text-muted">
        <NavOverflowMenu v-bind="args" />
        <span>(no overflow items — component is hidden)</span>
      </div>
    `,
  }),
};
