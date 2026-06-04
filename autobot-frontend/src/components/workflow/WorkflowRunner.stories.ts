import type { Meta, StoryObj } from '@storybook/vue3';
import WorkflowRunner from './WorkflowRunner.vue';

const meta = {
  title: 'Components/Workflow/WorkflowRunner',
  component: WorkflowRunner,
  tags: ['autodocs'],
  argTypes: {
    workflows: {
      control: 'object',
      description: 'List of active workflows shown in the sidebar',
    },
    currentWorkflow: {
      control: 'object',
      description: 'Currently selected workflow shown in the detail panel, or null',
    },
    loading: {
      control: 'boolean',
      description: 'Whether the workflow list is refreshing',
    },
  },
} as Meta<typeof WorkflowRunner>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const makeSteps = (statuses: string[]) =>
  statuses.map((status, i) => ({
    step_id: `s${i}`,
    status,
    description: `Step ${i + 1}: ${['Build', 'Test', 'Deploy', 'Verify', 'Notify'][i] ?? 'Task'}`,
    command: `cmd_step_${i}`,
    risk_level: i === 2 ? 'high' : 'low',
    requires_confirmation: i === 2,
    started_at: status === 'completed' ? new Date(Date.now() - (5 - i) * 60_000).toISOString() : undefined,
    completed_at: status === 'completed' ? new Date(Date.now() - (4 - i) * 60_000).toISOString() : undefined,
    execution_result: status === 'completed' ? { exit_code: 0, output: 'OK' } : undefined,
  }));

const activeWorkflow = {
  workflow_id: 'wf-runner-001',
  name: 'Deploy Backend v2.5',
  description: 'Production deployment of backend service version 2.5.0',
  automation_mode: 'supervised',
  current_step: 2,
  total_steps: 5,
  steps: makeSteps(['completed', 'completed', 'executing', 'pending', 'pending']),
  created_at: new Date(Date.now() - 600_000).toISOString(),
  started_at: new Date(Date.now() - 580_000).toISOString(),
  completed_at: null,
  is_paused: false,
  is_cancelled: false,
  phase: 'executing',
  active_service: 'autobot-backend',
};

const pausedWorkflow = {
  ...activeWorkflow,
  workflow_id: 'wf-runner-002',
  name: 'Security Scan',
  current_step: 1,
  steps: makeSteps(['completed', 'paused', 'pending', 'pending', 'pending']),
  is_paused: true,
};

export const NoSelection: Story = {
  args: {
    workflows: [activeWorkflow, pausedWorkflow],
    currentWorkflow: null,
    loading: false,
  },
};

export const WithSelectedWorkflow: Story = {
  args: {
    workflows: [activeWorkflow, pausedWorkflow],
    currentWorkflow: activeWorkflow,
    loading: false,
  },
};

export const PausedWorkflow: Story = {
  args: {
    workflows: [pausedWorkflow],
    currentWorkflow: pausedWorkflow,
    loading: false,
  },
};

export const EmptyList: Story = {
  args: {
    workflows: [],
    currentWorkflow: null,
    loading: false,
  },
};

export const LoadingRefresh: Story = {
  args: {
    workflows: [activeWorkflow],
    currentWorkflow: activeWorkflow,
    loading: true,
  },
};

export const WithApprovalPending: Story = {
  args: {
    workflows: [
      {
        ...activeWorkflow,
        workflow_id: 'wf-runner-approval',
        name: 'High-Risk Deploy',
        current_step: 2,
        steps: makeSteps(['completed', 'completed', 'waiting_approval', 'pending', 'pending']),
      },
    ],
    currentWorkflow: {
      ...activeWorkflow,
      workflow_id: 'wf-runner-approval',
      name: 'High-Risk Deploy',
      current_step: 2,
      steps: makeSteps(['completed', 'completed', 'waiting_approval', 'pending', 'pending']),
    },
    loading: false,
  },
};
