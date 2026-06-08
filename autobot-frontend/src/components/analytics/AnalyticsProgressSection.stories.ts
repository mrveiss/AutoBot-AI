// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AnalyticsProgressSection from './AnalyticsProgressSection.vue';

const mockScanRunner = {
  running: { value: false },
  results: { value: [] },
  completedCount: { value: 0 },
  totalCount: { value: 0 },
  progress: { value: 0 },
};

const mockScanRunnerActive = {
  running: { value: true },
  results: {
    value: [
      { id: '1', label: 'Declarations', status: 'completed', durationMs: 120 },
      { id: '2', label: 'Duplicates', status: 'running', durationMs: null },
      { id: '3', label: 'Hardcodes', status: 'pending', durationMs: null },
    ],
  },
  completedCount: { value: 1 },
  totalCount: { value: 3 },
  progress: { value: 33 },
};

const meta = {
  title: 'Components/Analytics/AnalyticsProgressSection',
  component: AnalyticsProgressSection,
  tags: ['autodocs'],
  argTypes: {
    analyzing: { control: 'boolean' },
    analyzingCodeSmells: { control: 'boolean' },
    progressStatus: { control: 'text' },
    progressPercent: { control: { type: 'range', min: 0, max: 100 } },
    currentJobId: { control: 'text' },
  },
} as Meta<typeof AnalyticsProgressSection>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    analyzing: true,
    analyzingCodeSmells: false,
    progressStatus: 'Scanning files...',
    progressPercent: 45,
    currentJobId: 'job-abc12345',
    jobPhases: {
      phase_list: [
        { id: 'parse', name: 'Parse Files', status: 'completed' },
        { id: 'index', name: 'Index Content', status: 'running' },
        { id: 'store', name: 'Store Results', status: 'pending' },
      ],
    },
    jobBatches: { total_batches: 10, completed_batches: 4 },
    jobStats: {
      files_scanned: 120,
      problems_found: 8,
      functions_found: 340,
      classes_found: 45,
      items_stored: 1200,
    },
    scanRunner: mockScanRunner,
    codeSmellsProgressTitle: 'Analyzing code smells...',
  },
};

export const CodeSmellsOnly: Story = {
  args: {
    analyzing: false,
    analyzingCodeSmells: true,
    progressStatus: 'Detecting anti-patterns...',
    progressPercent: 0,
    currentJobId: null,
    jobPhases: null,
    jobBatches: null,
    jobStats: null,
    scanRunner: mockScanRunner,
    codeSmellsProgressTitle: 'Code Smell Analysis',
  },
};

export const ScanRunnerActive: Story = {
  args: {
    analyzing: false,
    analyzingCodeSmells: false,
    progressStatus: 'Ready',
    progressPercent: 0,
    currentJobId: null,
    jobPhases: null,
    jobBatches: null,
    jobStats: null,
    scanRunner: mockScanRunnerActive,
    codeSmellsProgressTitle: '',
  },
};

export const Completed: Story = {
  args: {
    analyzing: false,
    analyzingCodeSmells: false,
    progressStatus: 'Indexing completed successfully',
    progressPercent: 100,
    currentJobId: null,
    jobPhases: null,
    jobBatches: null,
    jobStats: null,
    scanRunner: mockScanRunner,
    codeSmellsProgressTitle: '',
  },
};
