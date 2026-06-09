// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import TerminalOutput from './TerminalOutput.vue';

const commandLines = [
  { content: '$ git status', type: 'command', timestamp: new Date() },
  { content: 'On branch Dev_new_gui', type: 'output', timestamp: new Date() },
  { content: 'Your branch is up to date with \'origin/Dev_new_gui\'.', type: 'output', timestamp: new Date() },
  { content: '', type: 'output', timestamp: new Date() },
  { content: 'nothing to commit, working tree clean', type: 'success', timestamp: new Date() },
];

const mixedLines = [
  { content: '$ npm run build', type: 'command', timestamp: new Date() },
  { content: '> autobot-frontend@1.0.0 build', type: 'output', timestamp: new Date() },
  { content: '> vite build', type: 'output', timestamp: new Date() },
  { content: 'vite v5.0.0 building for production...', type: 'output', timestamp: new Date() },
  { content: '✓ 1234 modules transformed.', type: 'success', timestamp: new Date() },
  { content: 'dist/index.html                  1.23 kB', type: 'output', timestamp: new Date() },
  { content: 'Build completed in 12.3s', type: 'success', timestamp: new Date() },
];

const errorLines = [
  { content: '$ npm run type-check', type: 'command', timestamp: new Date() },
  { content: '> vue-tsc --noEmit', type: 'output', timestamp: new Date() },
  { content: 'error TS2345: Argument of type \'string\' is not assignable to parameter of type \'number\'.', type: 'error', timestamp: new Date() },
  { content: '  src/components/terminal/Terminal.vue:42:15', type: 'error', timestamp: new Date() },
  { content: 'Found 1 error.', type: 'error', timestamp: new Date() },
];

const warningLines = [
  { content: '$ docker build .', type: 'command', timestamp: new Date() },
  { content: 'Sending build context to Docker daemon', type: 'output', timestamp: new Date() },
  { content: 'WARNING: The requested image\'s platform does not match the detected host platform.', type: 'warning', timestamp: new Date() },
  { content: 'Step 1/8 : FROM node:20-alpine', type: 'output', timestamp: new Date() },
  { content: 'Successfully built a1b2c3d4e5f6', type: 'success', timestamp: new Date() },
];

const meta = {
  title: 'Components/Terminal/TerminalOutput',
  component: TerminalOutput,
  tags: ['autodocs'],
  argTypes: {
    outputLines: {
      control: 'object',
      description: 'Array of output lines to display in the terminal',
    },
  },
} as Meta<typeof TerminalOutput>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const CommandOutput: Story = {
  args: {
    outputLines: commandLines,
  },
  render: (args: Record<string, unknown>) => ({
    components: { TerminalOutput },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 300px; background: #1e1e1e; overflow: auto;">
        <TerminalOutput v-bind="args" />
      </div>
    `,
  }),
};

export const BuildOutput: Story = {
  args: {
    outputLines: mixedLines,
  },
  render: (args: Record<string, unknown>) => ({
    components: { TerminalOutput },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 300px; background: #1e1e1e; overflow: auto;">
        <TerminalOutput v-bind="args" />
      </div>
    `,
  }),
};

export const ErrorOutput: Story = {
  args: {
    outputLines: errorLines,
  },
  render: (args: Record<string, unknown>) => ({
    components: { TerminalOutput },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 250px; background: #1e1e1e; overflow: auto;">
        <TerminalOutput v-bind="args" />
      </div>
    `,
  }),
};

export const WithWarnings: Story = {
  args: {
    outputLines: warningLines,
  },
  render: (args: Record<string, unknown>) => ({
    components: { TerminalOutput },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 250px; background: #1e1e1e; overflow: auto;">
        <TerminalOutput v-bind="args" />
      </div>
    `,
  }),
};

export const Empty: Story = {
  args: {
    outputLines: [],
  },
  render: (args: Record<string, unknown>) => ({
    components: { TerminalOutput },
    setup: () => ({ args }),
    template: `
      <div style="width: 800px; height: 200px; background: #1e1e1e; overflow: auto;">
        <TerminalOutput v-bind="args" />
      </div>
    `,
  }),
};
