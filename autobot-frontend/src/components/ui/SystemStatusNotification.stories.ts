// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import SystemStatusNotification from './SystemStatusNotification.vue';

const meta = {
  title: 'Components/UI/SystemStatusNotification',
  component: SystemStatusNotification,
  argTypes: {
    visible: {
      control: 'boolean',
      description: 'Whether the notification is visible',
    },
    severity: {
      control: 'select',
      options: ['info', 'warning', 'error', 'success'],
      description: 'Notification severity level',
    },
    title: {
      control: 'text',
      description: 'Notification title',
    },
    message: {
      control: 'text',
      description: 'Notification body message',
    },
    statusDetails: {
      control: 'object',
      description: 'Optional system status details (status, lastCheck, error, ...)',
    },
    allowDismiss: {
      control: 'boolean',
      description: 'Allow user to dismiss the notification',
    },
    showDetails: {
      control: 'boolean',
      description: 'Render the system details panel inside the overlay',
    },
    autoHide: {
      control: 'number',
      description: 'Auto-hide delay in ms (0 to disable)',
    },
  },
} as Meta<typeof SystemStatusNotification>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const InfoToast: Story = {
  args: {
    visible: true,
    severity: 'info',
    title: 'System update',
    message: 'A new version is available. Refresh to apply.',
    autoHide: 0,
  },
};

export const SuccessToast: Story = {
  args: {
    visible: true,
    severity: 'success',
    title: 'Connection restored',
    message: 'Backend is reachable again.',
    autoHide: 0,
  },
};

export const WarningToast: Story = {
  args: {
    visible: true,
    severity: 'warning',
    title: 'Service degraded',
    message: 'Knowledge base latency is higher than normal.',
    autoHide: 0,
  },
};

export const ErrorToast: Story = {
  args: {
    visible: true,
    severity: 'error',
    title: 'Backend unreachable',
    message: 'Retrying in the background...',
    autoHide: 0,
  },
};

export const CriticalOverlay: Story = {
  args: {
    visible: true,
    severity: 'error',
    title: 'Backend offline',
    message: 'Multiple consecutive health-check failures.',
    showDetails: true,
    autoHide: 0,
    statusDetails: {
      status: 'offline',
      lastCheck: Date.now(),
      consecutiveFailures: 8,
      error: 'ECONNREFUSED 192.0.2.20:8001',
    },
  },
};

export const WithStatusDetails: Story = {
  args: {
    visible: true,
    severity: 'warning',
    title: 'Service degraded',
    message: 'Some endpoints are slow to respond.',
    showDetails: true,
    autoHide: 0,
    statusDetails: {
      status: 'degraded',
      lastCheck: Date.now(),
      consecutiveFailures: 2,
    },
  },
};
