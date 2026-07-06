// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import DocumentationSearchSidebar from './DocumentationSearchSidebar.vue';

const meta = {
  title: 'Components/Chat/DocumentationSearchSidebar',
  component: DocumentationSearchSidebar,
  tags: ['autodocs'],
  argTypes: {
    initiallyOpen: {
      control: 'boolean',
      description: 'Whether the sidebar starts expanded',
    },
  },
} as Meta<typeof DocumentationSearchSidebar>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<Record<string, unknown>>;

export const Open: Story = {
  args: {
    initiallyOpen: true,
  },
  render: (args: Record<string, unknown>) => ({
    components: { DocumentationSearchSidebar },
    setup() { return { args }; },
    template: `<div style="height:700px; width:360px; overflow:hidden;"><DocumentationSearchSidebar v-bind="args" /></div>`,
  }),
};

export const Collapsed: Story = {
  args: {
    initiallyOpen: false,
  },
  render: (args: Record<string, unknown>) => ({
    components: { DocumentationSearchSidebar },
    setup() { return { args }; },
    template: `<div style="height:700px; width:360px; overflow:hidden;"><DocumentationSearchSidebar v-bind="args" /></div>`,
  }),
};
