// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { Meta, StoryObj } from '@storybook/vue3';
import ManPageSearchPanel from './ManPageSearchPanel.vue';

const meta = {
  title: 'Components/ManPage/ManPageSearchPanel',
  component: ManPageSearchPanel,
  tags: ['autodocs'],
  argTypes: {
    show: {
      control: 'boolean',
      description: 'Whether the panel is visible',
    },
    query: {
      control: 'text',
      description: 'Current search query (v-model)',
    },
    lastQuery: {
      control: 'text',
      description: 'Last executed search query (shown in results heading)',
    },
    results: {
      control: 'object',
      description: 'Array of search results, or null before first search',
    },
    loading: {
      control: 'boolean',
      description: 'Disable search button while loading',
    },
  },
} as Meta<typeof ManPageSearchPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Hidden: Story = {
  args: {
    show: false,
    query: '',
    lastQuery: '',
    results: null,
    loading: false,
  },
};

export const EmptyQuery: Story = {
  args: {
    show: true,
    query: '',
    lastQuery: '',
    results: null,
    loading: false,
  },
};

export const WithResults: Story = {
  args: {
    show: true,
    query: 'network interface',
    lastQuery: 'network interface',
    results: [
      {
        command: 'ip',
        purpose: 'Show and manipulate routing, network devices, interfaces and tunnels.',
        relevance_score: 0.92,
        source: 'man8',
        machine_id: 'autobot-node-01',
      },
      {
        command: 'ifconfig',
        purpose: 'Configure a network interface.',
        relevance_score: 0.85,
        source: 'man8',
        machine_id: 'autobot-node-01',
      },
      {
        command: 'netstat',
        purpose: 'Print network connections, routing tables, interface statistics.',
        relevance_score: 0.78,
        source: 'man8',
        machine_id: 'autobot-node-01',
      },
    ],
    loading: false,
  },
};

export const NoResults: Story = {
  args: {
    show: true,
    query: 'xyzzy_unknown',
    lastQuery: 'xyzzy_unknown',
    results: [],
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    show: true,
    query: 'file permissions',
    lastQuery: 'file permissions',
    results: null,
    loading: true,
  },
};
