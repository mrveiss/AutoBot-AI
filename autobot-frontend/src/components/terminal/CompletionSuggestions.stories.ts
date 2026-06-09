// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CompletionSuggestions from './CompletionSuggestions.vue';

const commandItems = [
  { value: 'git status', type: 'command', description: 'Show working tree status' },
  { value: 'git commit', type: 'command', description: 'Record changes to repository' },
  { value: 'git push', type: 'command', description: 'Update remote refs' },
];

const pathItems = [
  { value: '/home/user/projects/', type: 'path', description: '' },
  { value: '/home/user/documents/', type: 'path', description: '' },
  { value: '/home/user/.config/', type: 'path', description: '' },
];

const mixedItems = [
  { value: 'ls', type: 'command', description: 'List directory contents' },
  { value: '/etc/hosts', type: 'path', description: '' },
  { value: 'apt-get install', type: 'history', description: 'Previously used' },
  { value: '--verbose', type: 'argument', description: 'Enable verbose output' },
  { value: 'cat', type: 'command', description: 'Concatenate and print files' },
];

const meta = {
  title: 'Components/Terminal/CompletionSuggestions',
  component: CompletionSuggestions,
  tags: ['autodocs'],
  argTypes: {
    items: {
      control: 'object',
      description: 'List of completion items to display',
    },
    selectedIndex: {
      control: { type: 'number', min: -1 },
      description: 'Index of the currently highlighted item',
    },
    visible: {
      control: 'boolean',
      description: 'Whether the suggestions dropdown is shown',
    },
  },
} as Meta<typeof CompletionSuggestions>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const CommandSuggestions: Story = {
  render: () => ({
    components: { CompletionSuggestions },
    template: `
      <div style="position: relative; height: 240px; background: #1e1e1e; padding-top: 200px;">
        <CompletionSuggestions
          :items="items"
          :selected-index="0"
          :visible="true"
        />
      </div>
    `,
    data: () => ({ items: commandItems }),
  }),
};

export const PathSuggestions: Story = {
  render: () => ({
    components: { CompletionSuggestions },
    template: `
      <div style="position: relative; height: 240px; background: #1e1e1e; padding-top: 200px;">
        <CompletionSuggestions
          :items="items"
          :selected-index="1"
          :visible="true"
        />
      </div>
    `,
    data: () => ({ items: pathItems }),
  }),
};

export const MixedTypes: Story = {
  render: () => ({
    components: { CompletionSuggestions },
    template: `
      <div style="position: relative; height: 280px; background: #1e1e1e; padding-top: 220px;">
        <CompletionSuggestions
          :items="items"
          :selected-index="2"
          :visible="true"
        />
      </div>
    `,
    data: () => ({ items: mixedItems }),
  }),
};

export const NoSelection: Story = {
  args: {
    items: commandItems,
    selectedIndex: -1,
    visible: true,
  },
  render: (args: Record<string, unknown>) => ({
    components: { CompletionSuggestions },
    setup: () => ({ args }),
    template: `
      <div style="position: relative; height: 240px; background: #1e1e1e; padding-top: 200px;">
        <CompletionSuggestions v-bind="args" />
      </div>
    `,
  }),
};

export const Hidden: Story = {
  args: {
    items: commandItems,
    selectedIndex: 0,
    visible: false,
  },
};
