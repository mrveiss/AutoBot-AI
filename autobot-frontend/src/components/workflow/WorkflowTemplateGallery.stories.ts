// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import WorkflowTemplateGallery from './WorkflowTemplateGallery.vue';

const meta = {
  title: 'Components/Workflow/WorkflowTemplateGallery',
  component: WorkflowTemplateGallery,
  tags: ['autodocs'],
  argTypes: {
    templates: {
      control: 'object',
      description: 'Array of workflow templates (used when useApi is false)',
    },
    loading: {
      control: 'boolean',
      description: 'Whether templates are loading (used when useApi is false)',
    },
    useApi: {
      control: 'boolean',
      description: 'When true, fetches templates from the API; when false, uses the templates prop',
    },
  },
} as Meta<typeof WorkflowTemplateGallery>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const makeTemplate = (
  id: string,
  name: string,
  description: string,
  category: string,
  icon: string,
  stepCount = 4,
) => ({
  id,
  name,
  description,
  category,
  icon,
  estimated_duration_minutes: stepCount * 5,
  agents_involved: ['coordinator', 'executor'],
  steps: Array.from({ length: stepCount }, (_, i) => ({
    task_id: `${id}-step-${i}`,
    agent_type: 'executor',
    action: 'run',
    command: `step_cmd_${i}`,
    description: `Step ${i + 1}`,
    requires_approval: i === stepCount - 1,
    dependencies: i > 0 ? [`${id}-step-${i - 1}`] : [],
    inputs: {},
    estimated_duration_seconds: 60,
    prompt: null,
    tools_allowed: null,
    tools_denied: [],
  })),
});

const sampleTemplates = [
  makeTemplate('tpl-001', 'Deploy Backend Service', 'Full CI/CD pipeline for backend deployment', 'Development', 'fas fa-code', 5),
  makeTemplate('tpl-002', 'Security Vulnerability Scan', 'Automated CVE scanning across all services', 'Security', 'fas fa-shield-alt', 3),
  makeTemplate('tpl-003', 'Database Backup', 'Scheduled backup with integrity verification', 'Backup', 'fas fa-database', 4),
  makeTemplate('tpl-004', 'System Health Report', 'Aggregate system metrics and generate report', 'System', 'fas fa-cog', 6),
  makeTemplate('tpl-005', 'Log Analysis', 'Parse and summarise application logs', 'Analysis', 'fas fa-chart-bar', 3),
  makeTemplate('tpl-006', 'Community Sync', 'Sync contributions from external repositories', 'Community', 'fas fa-users', 2),
];

export const StaticTemplates: Story = {
  args: {
    templates: sampleTemplates,
    loading: false,
    useApi: false,
  },
};

export const LoadingState: Story = {
  args: {
    templates: [],
    loading: true,
    useApi: false,
  },
};

export const Empty: Story = {
  args: {
    templates: [],
    loading: false,
    useApi: false,
  },
};

export const ApiMode: Story = {
  args: {
    templates: [],
    loading: false,
    useApi: true,
  },
};

export const SingleTemplate: Story = {
  args: {
    templates: [sampleTemplates[0]],
    loading: false,
    useApi: false,
  },
};
