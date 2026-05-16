import type { Meta, StoryObj } from '@storybook/vue3';
import WorkflowNotificationConfig from './WorkflowNotificationConfig.vue';

const meta = {
  title: 'Components/Workflow/WorkflowNotificationConfig',
  component: WorkflowNotificationConfig,
  tags: ['autodocs'],
  argTypes: {
    workflows: {
      control: 'object',
      description: 'List of workflow summaries available for selection',
    },
  },
} as Meta<typeof WorkflowNotificationConfig>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const sampleWorkflows = [
  { workflow_id: 'wf-aaa111', name: 'Backend Deployment' },
  { workflow_id: 'wf-bbb222', name: 'Database Migration' },
  { workflow_id: 'wf-ccc333', name: 'Security Scan' },
  { workflow_id: 'wf-ddd444', name: 'Nightly Backup' },
];

export const WithWorkflows: Story = {
  args: {
    workflows: sampleWorkflows,
  },
};

export const NoWorkflows: Story = {
  args: {
    workflows: [],
  },
};

export const SingleWorkflow: Story = {
  args: {
    workflows: [sampleWorkflows[0]],
  },
};

export const ManyWorkflows: Story = {
  args: {
    workflows: Array.from({ length: 12 }, (_, i) => ({
      workflow_id: `wf-bulk-${i}`,
      name: `Workflow ${i + 1} — ${['Deploy', 'Backup', 'Scan', 'Migrate'][i % 4]}`,
    })),
  },
};
