// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import OrgTreeNode from './OrgTreeNode.vue'

const meta = {
  title: 'Agents/OrgTreeNode',
  component: OrgTreeNode,
  tags: ['autodocs'],
  argTypes: {
    depth: { control: { type: 'number', min: 0, max: 5 } },
    selectedId: { control: 'text' },
  },
} satisfies Meta<typeof OrgTreeNode>

export default meta

export const Manager = {
  args: {
    node: {
      agent_id: 'agent-001',
      name: 'CEO',
      org_role: 'manager',
      title: 'Chief Executive Officer',
      capabilities: 'Strategic planning, agent coordination',
      direct_reports_count: 5,
      children: [],
    },
    depth: 0,
    selectedId: null,
  },
}

export const Specialist = {
  args: {
    node: {
      agent_id: 'agent-002',
      name: 'SeniorFrontendDeveloper',
      org_role: 'specialist',
      title: 'Senior Frontend Developer',
      capabilities: 'Vue 3, TypeScript, Storybook',
      direct_reports_count: 0,
      children: [],
    },
    depth: 1,
    selectedId: null,
  },
}

export const Selected = {
  args: {
    node: {
      agent_id: 'agent-003',
      name: 'BackendEngineer',
      org_role: 'specialist',
      title: 'Backend Engineer',
      capabilities: 'FastAPI, Redis, ChromaDB',
      direct_reports_count: 0,
      children: [],
    },
    depth: 1,
    selectedId: 'agent-003',
  },
}
