// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import AgentObservabilityPanel from './AgentObservabilityPanel.vue';

const meta = {
  title: 'Components/Workflow/AgentObservabilityPanel',
  component: AgentObservabilityPanel,
  tags: ['autodocs'],
  argTypes: {
    agentPerformance: {
      control: 'object',
      description: 'Record of agent performance data keyed by agent identifier',
    },
    agentCapabilities: {
      control: 'object',
      description: 'Record of agent capability data keyed by agent identifier',
    },
    loading: {
      control: 'boolean',
      description: 'Whether data is being loaded',
    },
  },
} as Meta<typeof AgentObservabilityPanel>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

const samplePerformance = {
  coordinator: {
    agent_name: 'Coordinator Agent',
    total_tasks: 42,
    successful_tasks: 39,
    failed_tasks: 3,
    average_duration: 12.5,
    reliability_score: 0.93,
  },
  researcher: {
    agent_name: 'Research Agent',
    total_tasks: 28,
    successful_tasks: 22,
    failed_tasks: 6,
    average_duration: 45.2,
    reliability_score: 0.79,
  },
  executor: {
    agent_name: 'Executor Agent',
    total_tasks: 15,
    successful_tasks: 8,
    failed_tasks: 7,
    average_duration: 8.1,
    reliability_score: 0.53,
  },
};

const sampleCapabilities = {
  coordinator: {
    agent: 'Coordinator Agent',
    capabilities: ['task-routing', 'priority-management', 'agent-coordination'],
    performance: { total_tasks: 42, reliability: 0.93 },
  },
  researcher: {
    agent: 'Research Agent',
    capabilities: ['web-search', 'document-analysis', 'summarization', 'fact-checking', 'citation'],
    performance: { total_tasks: 28, reliability: 0.79 },
  },
  executor: {
    agent: 'Executor Agent',
    capabilities: ['shell-commands', 'file-operations'],
    performance: { total_tasks: 15, reliability: 0.53 },
  },
};

export const Default: Story = {
  args: {
    agentPerformance: samplePerformance,
    agentCapabilities: sampleCapabilities,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    agentPerformance: {},
    agentCapabilities: {},
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    agentPerformance: {},
    agentCapabilities: {},
    loading: false,
  },
};

export const SingleAgent: Story = {
  args: {
    agentPerformance: {
      coordinator: samplePerformance.coordinator,
    },
    agentCapabilities: {
      coordinator: sampleCapabilities.coordinator,
    },
    loading: false,
  },
};

export const HighReliabilityAgents: Story = {
  args: {
    agentPerformance: {
      alpha: {
        agent_name: 'Alpha Agent',
        total_tasks: 100,
        successful_tasks: 98,
        failed_tasks: 2,
        average_duration: 3.2,
        reliability_score: 0.98,
      },
      beta: {
        agent_name: 'Beta Agent',
        total_tasks: 80,
        successful_tasks: 76,
        failed_tasks: 4,
        average_duration: 5.6,
        reliability_score: 0.95,
      },
    },
    agentCapabilities: {
      alpha: { agent: 'Alpha Agent', capabilities: ['fast-execution', 'retries'], performance: { total_tasks: 100, reliability: 0.98 } },
      beta: { agent: 'Beta Agent', capabilities: ['analysis', 'reporting'], performance: { total_tasks: 80, reliability: 0.95 } },
    },
    loading: false,
  },
};
