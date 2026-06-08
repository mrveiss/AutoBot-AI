// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AnalyticsHeaderControls from './AnalyticsHeaderControls.vue';

const meta = {
  title: 'Components/Analytics/AnalyticsHeaderControls',
  component: AnalyticsHeaderControls,
  tags: ['autodocs'],
  argTypes: {
    analyzing: { control: 'boolean' },
    rootPath: { control: 'text' },
    selectedSource: { control: 'object' },
    scanRunnerRunning: { control: 'boolean' },
    loadingApiEndpoints: { control: 'boolean' },
    analyzingCodeSmells: { control: 'boolean' },
    exportingReport: { control: 'boolean' },
    clearingCache: { control: 'boolean' },
  },
} as Meta<typeof AnalyticsHeaderControls>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    analyzing: false,
    rootPath: '/opt/autobot',
    selectedSource: null,
    scanRunnerRunning: false,
    loadingApiEndpoints: false,
    analyzingCodeSmells: false,
    exportingReport: false,
    clearingCache: false,
  },
};

export const Analyzing: Story = {
  args: {
    analyzing: true,
    rootPath: '/opt/autobot',
    selectedSource: null,
    scanRunnerRunning: false,
    loadingApiEndpoints: false,
    analyzingCodeSmells: false,
    exportingReport: false,
    clearingCache: false,
  },
};

export const ScanRunnerRunning: Story = {
  args: {
    analyzing: false,
    rootPath: '/opt/autobot',
    selectedSource: null,
    scanRunnerRunning: true,
    loadingApiEndpoints: false,
    analyzingCodeSmells: false,
    exportingReport: false,
    clearingCache: false,
  },
};

export const AllOperationsActive: Story = {
  args: {
    analyzing: false,
    rootPath: '/opt/autobot',
    selectedSource: null,
    scanRunnerRunning: true,
    loadingApiEndpoints: true,
    analyzingCodeSmells: true,
    exportingReport: false,
    clearingCache: false,
  },
};
