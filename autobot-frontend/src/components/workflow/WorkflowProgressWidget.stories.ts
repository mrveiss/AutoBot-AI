// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import WorkflowProgressWidget from './WorkflowProgressWidget.vue';

const meta = {
  title: 'Components/Workflow/WorkflowProgressWidget',
  component: WorkflowProgressWidget,
  tags: ['autodocs'],
  argTypes: {
    workflowId: {
      control: 'text',
      description: 'ID of the workflow to track; triggers data polling when set',
    },
  },
} as Meta<typeof WorkflowProgressWidget>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// WorkflowProgressWidget fetches its own data via the API using the workflowId prop.
// Stories show the idle state (no workflowId) and the loading state (workflowId set).

export const NoWorkflow: Story = {
  args: {
    workflowId: undefined,
  },
};

export const WithWorkflowId: Story = {
  args: {
    workflowId: 'wf-demo-001',
  },
};

export const AlternateWorkflow: Story = {
  args: {
    workflowId: 'wf-demo-002',
  },
};

export const ContainerContext: Story = {
  render: () => ({
    components: { WorkflowProgressWidget },
    template: `
      <div style="position: relative; height: 300px; background: #1e293b; border-radius: 8px; padding: 16px;">
        <p style="color: #94a3b8; font-size: 14px;">Page content area</p>
        <WorkflowProgressWidget workflow-id="wf-demo-003" />
      </div>
    `,
  }),
};
