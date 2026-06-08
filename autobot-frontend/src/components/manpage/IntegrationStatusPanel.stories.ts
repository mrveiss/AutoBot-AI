// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { Meta, StoryObj } from '@storybook/vue3';
import IntegrationStatusPanel from './IntegrationStatusPanel.vue';

const meta = {
  title: 'Components/ManPage/IntegrationStatusPanel',
  component: IntegrationStatusPanel,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'object',
      description: 'Integration status object',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading spinner',
    },
  },
} as Meta<typeof IntegrationStatusPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const NotIntegrated: Story = {
  args: {
    status: { status: 'not_integrated' },
    loading: false,
  },
};

export const ErrorState: Story = {
  args: {
    status: { status: 'error', message: 'Connection to knowledge base failed.' },
    loading: false,
  },
};

export const Integrated: Story = {
  args: {
    status: {
      status: 'integrated',
      successful: 142,
      processed: 150,
      current_man_page_files: 142,
      total_available_tools: 98,
      integration_date: '2025-05-10T14:30:00Z',
      available_commands: ['ls', 'grep', 'awk', 'sed', 'curl', 'ssh', 'git', 'docker'],
    },
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    status: null,
    loading: true,
  },
};

export const IntegratedNoCommands: Story = {
  args: {
    status: {
      status: 'integrated',
      successful: 10,
      processed: 10,
      current_man_page_files: 10,
      total_available_tools: 5,
      integration_date: '2025-05-01T08:00:00Z',
    },
    loading: false,
  },
};
