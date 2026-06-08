// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TerminalSettings from './TerminalSettings.vue';

const meta = {
  title: 'Components/Terminal/TerminalSettings',
  component: TerminalSettings,
  tags: ['autodocs'],
  // TerminalSettings manages its own state from localStorage — no external props.
  argTypes: {},
} as Meta<typeof TerminalSettings>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { TerminalSettings },
    template: `
      <div style="width: 400px; padding: 16px; background: #111827;">
        <TerminalSettings />
      </div>
    `,
  }),
};

export const InPanel: Story = {
  render: () => ({
    components: { TerminalSettings },
    template: `
      <div style="width: 320px; padding: 12px; background: #111827; border-radius: 8px; border: 1px solid #374151;">
        <TerminalSettings />
      </div>
    `,
  }),
};

export const WideLayout: Story = {
  render: () => ({
    components: { TerminalSettings },
    template: `
      <div style="width: 600px; padding: 24px; background: #111827;">
        <TerminalSettings />
      </div>
    `,
  }),
};

export const DarkBackground: Story = {
  render: () => ({
    components: { TerminalSettings },
    template: `
      <div style="width: 400px; padding: 16px; background: #000000;">
        <TerminalSettings />
      </div>
    `,
  }),
};
