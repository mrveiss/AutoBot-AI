// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import WorkflowAutomation from './WorkflowAutomation.vue';

const sampleSteps = [
  { stepNumber: 1, totalSteps: 4, command: 'git pull origin main', description: 'Pull latest changes', requiresConfirmation: false },
  { stepNumber: 2, totalSteps: 4, command: 'npm install', description: 'Install dependencies', requiresConfirmation: false },
  { stepNumber: 3, totalSteps: 4, command: 'npm run build', description: 'Build project', requiresConfirmation: true },
  { stepNumber: 4, totalSteps: 4, command: 'pm2 restart autobot', description: 'Restart service', requiresConfirmation: true },
];

const meta = {
  title: 'Components/Terminal/WorkflowAutomation',
  component: WorkflowAutomation,
  tags: ['autodocs'],
  argTypes: {
    automationPaused: {
      control: 'boolean',
      description: 'Whether automation execution is currently paused',
    },
    hasAutomatedWorkflow: {
      control: 'boolean',
      description: 'Whether an automated workflow is loaded and active',
    },
    currentWorkflowStep: {
      control: { type: 'number', min: 0 },
      description: 'Zero-based index of the step currently being executed',
    },
    workflowSteps: {
      control: 'object',
      description: 'Full ordered list of workflow steps to execute',
    },
    pendingWorkflowStep: {
      control: 'object',
      description: 'The step currently awaiting user confirmation (null if none)',
    },
    automationQueue: {
      control: 'object',
      description: 'Queue of steps waiting to be executed',
    },
    waitingForUserConfirmation: {
      control: 'boolean',
      description: 'Whether the automation is blocked waiting for user confirmation',
    },
  },
} as Meta<typeof WorkflowAutomation>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// NOTE: WorkflowAutomation is a renderless orchestration component — its
// template contains only a placeholder comment.  All state is managed via
// emits and computed two-way bindings.  These stories demonstrate the prop
// contract and allow Storybook Controls to exercise it.

export const Idle: Story = {
  args: {
    automationPaused: false,
    hasAutomatedWorkflow: false,
    currentWorkflowStep: 0,
    workflowSteps: [],
    pendingWorkflowStep: null,
    automationQueue: [],
    waitingForUserConfirmation: false,
  },
};

export const RunningWorkflow: Story = {
  args: {
    automationPaused: false,
    hasAutomatedWorkflow: true,
    currentWorkflowStep: 1,
    workflowSteps: sampleSteps,
    pendingWorkflowStep: null,
    automationQueue: [sampleSteps[2], sampleSteps[3]],
    waitingForUserConfirmation: false,
  },
};

export const WaitingForConfirmation: Story = {
  args: {
    automationPaused: false,
    hasAutomatedWorkflow: true,
    currentWorkflowStep: 2,
    workflowSteps: sampleSteps,
    pendingWorkflowStep: sampleSteps[2],
    automationQueue: [sampleSteps[3]],
    waitingForUserConfirmation: true,
  },
};

export const Paused: Story = {
  args: {
    automationPaused: true,
    hasAutomatedWorkflow: true,
    currentWorkflowStep: 1,
    workflowSteps: sampleSteps,
    pendingWorkflowStep: null,
    automationQueue: [sampleSteps[2], sampleSteps[3]],
    waitingForUserConfirmation: false,
  },
};

export const Completed: Story = {
  args: {
    automationPaused: false,
    hasAutomatedWorkflow: false,
    currentWorkflowStep: 4,
    workflowSteps: sampleSteps,
    pendingWorkflowStep: null,
    automationQueue: [],
    waitingForUserConfirmation: false,
  },
};
