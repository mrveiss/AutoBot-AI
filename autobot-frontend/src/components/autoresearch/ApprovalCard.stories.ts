// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import ApprovalCard from './ApprovalCard.vue'

const meta = {
  title: 'Components/AutoResearch/ApprovalCard',
  component: ApprovalCard,
  tags: ['autodocs'],
  argTypes: {
    approval: {
      control: 'object',
      description: 'Approval details object containing session/experiment IDs and optional metrics',
    },
  },
} as Meta<typeof ApprovalCard>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const WithMetrics: Story = {
  args: {
    approval: {
      sessionId: 'session-abc-123',
      experimentId: 'exp-xyz-456',
      topic: 'Learning rate schedule',
      iteration: 3,
      metrics: {
        baseline_val_bpb: 2.4812,
        result_val_bpb: 2.3956,
        improvement: 0.0856,
        improvement_pct: 3.45,
      },
    },
  },
}

export const WithoutMetrics: Story = {
  args: {
    approval: {
      sessionId: 'session-def-789',
      experimentId: 'exp-uvw-012',
      topic: 'Batch size experiment',
    },
  },
}

export const NegativeImprovement: Story = {
  args: {
    approval: {
      sessionId: 'session-ghi-345',
      experimentId: 'exp-rst-678',
      iteration: 1,
      metrics: {
        baseline_val_bpb: 2.3956,
        result_val_bpb: 2.5100,
        improvement: -0.1144,
        improvement_pct: -4.77,
      },
    },
  },
}

export const MinimalData: Story = {
  args: {
    approval: {
      sessionId: 'session-min-001',
      experimentId: 'exp-min-001',
    },
  },
}

export const HighImprovement: Story = {
  args: {
    approval: {
      sessionId: 'session-high-999',
      experimentId: 'exp-high-999',
      topic: 'Warmup steps tuning',
      iteration: 7,
      metrics: {
        baseline_val_bpb: 3.1200,
        result_val_bpb: 2.7640,
        improvement: 0.356,
        improvement_pct: 11.41,
      },
    },
  },
}
