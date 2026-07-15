// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import HostSelector from './HostSelector.vue';
import { getConfig } from '@/config/ssot-config';
const config = getConfig();

const sampleHosts = [
  { id: 'main', name: 'Main Server', ip: config.vm.main, description: 'Primary AutoBot backend server' },
  { id: 'frontend', name: 'Frontend VM', ip: config.vm.frontend, description: 'Vue 3 frontend development VM' },
  { id: 'ai-stack', name: 'AI Stack', ip: config.vm.aistack, description: 'LLM inference and AI processing VM' },
];

const meta = {
  title: 'Components/Terminal/HostSelector',
  component: HostSelector,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'text',
      description: 'Currently selected host ID (v-model)',
    },
    hosts: {
      control: 'object',
      description: 'List of available host configurations',
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the host selector',
    },
    showDescription: {
      control: 'boolean',
      description: 'Show the description of the selected host below the selector',
    },
  },
} as Meta<typeof HostSelector>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    modelValue: 'main',
    hosts: sampleHosts,
    disabled: false,
    showDescription: true,
  },
};

export const WithoutDescription: Story = {
  args: {
    modelValue: 'frontend',
    hosts: sampleHosts,
    disabled: false,
    showDescription: false,
  },
};

export const Disabled: Story = {
  args: {
    modelValue: 'ai-stack',
    hosts: sampleHosts,
    disabled: true,
    showDescription: true,
  },
};

export const SingleHost: Story = {
  args: {
    modelValue: 'main',
    hosts: [sampleHosts[0]],
    disabled: false,
    showDescription: true,
  },
};

export const ManyHosts: Story = {
  args: {
    modelValue: 'main',
    hosts: [
      ...sampleHosts,
      { id: 'db', name: 'Database VM', ip: config.vm.redis, description: 'PostgreSQL and Redis server' },
      { id: 'monitoring', name: 'Monitoring', ip: config.vm.aistack, description: 'Grafana and Prometheus' },
      { id: 'backup', name: 'Backup Server', ip: '192.0.2.100', description: 'Automated backup storage' },
    ],
    disabled: false,
    showDescription: true,
  },
};
