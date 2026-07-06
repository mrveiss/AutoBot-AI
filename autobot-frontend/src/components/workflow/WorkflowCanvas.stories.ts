// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import WorkflowCanvas from './WorkflowCanvas.vue';

const meta = {
  title: 'Components/Workflow/WorkflowCanvas',
  component: WorkflowCanvas,
  tags: ['autodocs'],
  argTypes: {
    nodes: {
      control: 'object',
      description: 'Array of workflow nodes on the canvas',
    },
    selectedNodeId: {
      control: 'text',
      description: 'ID of the currently selected node, or null',
    },
  },
} as Meta<typeof WorkflowCanvas>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Empty: Story = {
  args: {
    nodes: [],
    selectedNodeId: null,
  },
};

export const WithStepNodes: Story = {
  args: {
    nodes: [
      {
        id: 'node_1',
        type: 'step',
        position: { x: 100, y: 100 },
        data: {
          description: 'Install dependencies',
          command: 'npm install',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 30,
        },
        connections: ['node_2'],
      },
      {
        id: 'node_2',
        type: 'step',
        position: { x: 400, y: 100 },
        data: {
          description: 'Run tests',
          command: 'npm test',
          risk_level: 'low',
          requires_confirmation: false,
          estimated_duration: 60,
        },
        connections: ['node_3'],
      },
      {
        id: 'node_3',
        type: 'step',
        position: { x: 700, y: 100 },
        data: {
          description: 'Deploy to production',
          command: 'npm run deploy',
          risk_level: 'high',
          requires_confirmation: true,
          estimated_duration: 120,
        },
        connections: [],
      },
    ],
    selectedNodeId: 'node_2',
  },
};

export const WithConditionNode: Story = {
  args: {
    nodes: [
      {
        id: 'node_start',
        type: 'step',
        position: { x: 80, y: 120 },
        data: { description: 'Check environment', command: 'env check', risk_level: 'low', requires_confirmation: false, estimated_duration: 5 },
        connections: ['node_cond'],
      },
      {
        id: 'node_cond',
        type: 'condition',
        position: { x: 360, y: 120 },
        data: { condition: 'ENV == production' },
        connections: [],
      },
    ],
    selectedNodeId: null,
  },
};

export const WithVisionNodes: Story = {
  args: {
    nodes: [
      {
        id: 'vis_1',
        type: 'vision-capture',
        position: { x: 80, y: 80 },
        data: { target: 'vnc', include_ocr: true, include_elements: true, include_layout: true },
        connections: ['vis_2'],
      },
      {
        id: 'vis_2',
        type: 'vision-find-element',
        position: { x: 360, y: 80 },
        data: { target: 'vnc', element_type: 'button', text_match: 'Submit', confidence_threshold: 0.8 },
        connections: ['vis_3'],
      },
      {
        id: 'vis_3',
        type: 'vision-click',
        position: { x: 640, y: 80 },
        data: { target: 'vnc', element_ref: '', click_type: 'single' },
        connections: [],
      },
    ],
    selectedNodeId: 'vis_1',
  },
};

export const SelectedNode: Story = {
  args: {
    nodes: [
      {
        id: 'sel_1',
        type: 'step',
        position: { x: 100, y: 150 },
        data: { description: 'Selected step', command: 'echo hello', risk_level: 'medium', requires_confirmation: true, estimated_duration: 10 },
        connections: [],
      },
    ],
    selectedNodeId: 'sel_1',
  },
};
