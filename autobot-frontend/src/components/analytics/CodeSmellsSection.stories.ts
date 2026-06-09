// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import CodeSmellsSection from './CodeSmellsSection.vue';

const sampleSmells = [
  {
    severity: 'high',
    description: 'Function is too long (150 lines)',
    file_path: 'autobot-backend/chat/handler.py',
    line_number: 42,
    suggestion: 'Extract into smaller functions',
    smell_type: 'long_function',
  },
  {
    severity: 'medium',
    description: 'God class with 25 methods',
    file_path: 'autobot-backend/agents/manager.py',
    line_number: 10,
    suggestion: 'Split into focused classes',
    smell_type: 'god_class',
  },
  {
    severity: 'low',
    description: 'Magic number used directly',
    file_path: 'autobot-backend/config.py',
    line_number: 88,
    suggestion: 'Use named constant',
    smell_type: 'magic_number',
  },
];

const meta = {
  title: 'Components/Analytics/CodeSmellsSection',
  component: CodeSmellsSection,
  tags: ['autodocs'],
  argTypes: {
    smells: { control: 'object' },
    codeHealthScore: { control: 'object' },
  },
} as Meta<typeof CodeSmellsSection>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    smells: sampleSmells,
    codeHealthScore: { grade: 'B', health_score: 78 },
  },
};

export const Empty: Story = {
  args: {
    smells: [],
    codeHealthScore: null,
  },
};

export const HighScore: Story = {
  args: {
    smells: sampleSmells.slice(0, 1),
    codeHealthScore: { grade: 'A', health_score: 92 },
  },
};

export const LowScore: Story = {
  args: {
    smells: [...sampleSmells, ...sampleSmells, ...sampleSmells],
    codeHealthScore: { grade: 'D', health_score: 38 },
  },
};
