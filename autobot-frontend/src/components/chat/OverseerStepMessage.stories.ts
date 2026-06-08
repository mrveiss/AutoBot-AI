// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import OverseerStepMessage from './OverseerStepMessage.vue';

const meta = {
  title: 'Components/Chat/OverseerStepMessage',
  component: OverseerStepMessage,
  tags: ['autodocs'],
  argTypes: {
    step: {
      control: 'object',
      description: 'OverseerStep object with status, command, and output',
    },
  },
} as Meta<typeof OverseerStepMessage>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Pending: Story = {
  args: {
    step: {
      step_number: 1,
      total_steps: 3,
      description: 'Check nginx service status',
      command: 'systemctl status nginx',
      status: 'pending',
    },
  },
};

export const Running: Story = {
  args: {
    step: {
      step_number: 2,
      total_steps: 3,
      description: 'Restart nginx service',
      command: 'systemctl restart nginx',
      status: 'running',
      is_streaming: true,
      stream_complete: false,
      output: 'Stopping nginx...\n',
    },
  },
};

export const Completed: Story = {
  args: {
    step: {
      step_number: 1,
      total_steps: 3,
      description: 'Check nginx service status',
      command: 'systemctl status nginx',
      status: 'completed',
      execution_time: 0.42,
      is_streaming: false,
      stream_complete: true,
      return_code: 0,
      output: '● nginx.service - A high performance web server\n   Active: active (running) since Mon 2025-01-01 12:00:00 UTC',
      command_explanation: {
        summary: 'Queries systemd for the current status of the nginx web server process.',
        breakdown: [
          { part: 'systemctl', explanation: 'System and service manager CLI' },
          { part: 'status', explanation: 'Show runtime status information' },
          { part: 'nginx', explanation: 'Target service name' },
        ],
        security_notes: null,
      },
      output_explanation: {
        summary: 'Nginx is running normally with no errors.',
        key_findings: ['Service is active and running', 'No error conditions detected'],
        details: 'The service has been active since startup with no recent restarts.',
        next_steps: null,
      },
    },
  },
};

export const Failed: Story = {
  args: {
    step: {
      step_number: 2,
      total_steps: 3,
      description: 'Restart nginx service',
      command: 'systemctl restart nginx',
      status: 'failed',
      execution_time: 1.2,
      return_code: 1,
      error: 'Job for nginx.service failed. See `journalctl -xe` for details.',
      output: 'Failed to restart nginx.service: Unit not found.',
    },
  },
};

export const WithSecurityNote: Story = {
  args: {
    step: {
      step_number: 1,
      total_steps: 2,
      description: 'Remove temporary files',
      command: 'rm -rf /tmp/build-artifacts',
      status: 'pending',
      command_explanation: {
        summary: 'Recursively removes the build artifacts directory.',
        breakdown: [
          { part: 'rm', explanation: 'Remove files and directories' },
          { part: '-rf', explanation: 'Recursive and force — no confirmation prompts' },
          { part: '/tmp/build-artifacts', explanation: 'Target path to delete' },
        ],
        security_notes: 'This operation is irreversible. Verify the path before proceeding.',
      },
    },
  },
};
