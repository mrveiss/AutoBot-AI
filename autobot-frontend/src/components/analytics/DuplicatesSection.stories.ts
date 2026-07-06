// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import DuplicatesSection from './DuplicatesSection.vue';

const sampleDuplicates = [
  {
    similarity: 95,
    lines: 42,
    file1: 'autobot-backend/agents/agent_a.py',
    file2: 'autobot-backend/agents/agent_b.py',
  },
  {
    similarity: 82,
    lines: 18,
    file1: 'autobot-frontend/src/utils/format.ts',
    file2: 'autobot-frontend/src/utils/helpers.ts',
  },
  {
    similarity: 68,
    lines: 9,
    file1: 'autobot-backend/api/routes_v1.py',
    file2: 'autobot-backend/api/routes_v2.py',
  },
];

const meta = {
  title: 'Components/Analytics/DuplicatesSection',
  component: DuplicatesSection,
  tags: ['autodocs'],
  argTypes: {
    duplicates: { control: 'object' },
    loading: { control: 'boolean' },
  },
} as Meta<typeof DuplicatesSection>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    duplicates: sampleDuplicates,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    duplicates: [],
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    duplicates: [],
    loading: false,
  },
};

export const HighSimilarity: Story = {
  args: {
    duplicates: sampleDuplicates.filter(d => d.similarity >= 90),
    loading: false,
  },
};
