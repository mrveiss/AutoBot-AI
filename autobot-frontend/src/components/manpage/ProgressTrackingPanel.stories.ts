// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { Meta, StoryObj } from '@storybook/vue3';
import ProgressTrackingPanel from './ProgressTrackingPanel.vue';

const meta = {
  title: 'Components/ManPage/ProgressTrackingPanel',
  component: ProgressTrackingPanel,
  tags: ['autodocs'],
  argTypes: {
    show: {
      control: 'boolean',
      description: 'Whether the panel is visible',
    },
    state: {
      control: 'object',
      description: 'Progress state object',
    },
    websocketConnected: {
      control: 'boolean',
      description: 'WebSocket connection status',
    },
  },
} as Meta<typeof ProgressTrackingPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Hidden: Story = {
  args: {
    show: false,
    state: {
      currentTask: '',
      taskDetail: '',
      overallProgress: 0,
      taskProgress: 0,
      status: 'waiting',
      messages: [],
    },
    websocketConnected: false,
  },
};

export const Waiting: Story = {
  args: {
    show: true,
    state: {
      currentTask: '',
      taskDetail: '',
      overallProgress: 0,
      taskProgress: 0,
      status: 'waiting',
      messages: [],
    },
    websocketConnected: true,
  },
};

export const Running: Story = {
  args: {
    show: true,
    state: {
      currentTask: 'Integrating man pages',
      taskDetail: 'Processing section 8 commands',
      overallProgress: 55,
      taskProgress: 72,
      status: 'running',
      messages: [
        { text: 'Starting integration...', type: 'info', timestamp: Date.now() - 30000 },
        { text: 'Profile detected: Ubuntu 22.04', type: 'success', timestamp: Date.now() - 20000 },
        { text: 'Processing section 1 commands (42 found)', type: 'info', timestamp: Date.now() - 10000 },
        { text: 'Processing section 8 commands (67 found)', type: 'info', timestamp: Date.now() - 2000 },
      ],
    },
    websocketConnected: true,
  },
};

export const Completed: Story = {
  args: {
    show: true,
    state: {
      currentTask: 'Integration complete',
      taskDetail: 'All man pages processed successfully',
      overallProgress: 100,
      taskProgress: 100,
      status: 'success',
      messages: [
        { text: 'Starting integration...', type: 'info', timestamp: Date.now() - 60000 },
        { text: 'Profile detected: Ubuntu 22.04', type: 'success', timestamp: Date.now() - 50000 },
        { text: 'Processed 142 man pages', type: 'success', timestamp: Date.now() - 10000 },
        { text: 'Integration complete!', type: 'success', timestamp: Date.now() - 1000 },
      ],
    },
    websocketConnected: true,
  },
};

export const ErrorState: Story = {
  args: {
    show: true,
    state: {
      currentTask: 'Integration Failed',
      taskDetail: 'Backend connection lost',
      overallProgress: 30,
      taskProgress: 0,
      status: 'error',
      messages: [
        { text: 'Starting integration...', type: 'info', timestamp: Date.now() - 20000 },
        { text: 'Profile detected: Ubuntu 22.04', type: 'success', timestamp: Date.now() - 15000 },
        { text: 'Error: Backend connection lost', type: 'error', timestamp: Date.now() - 5000 },
      ],
    },
    websocketConnected: false,
  },
};
