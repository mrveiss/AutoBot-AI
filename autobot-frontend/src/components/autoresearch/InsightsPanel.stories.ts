// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform

import type { Meta, StoryObj } from '@storybook/vue3'
import InsightsPanel from './InsightsPanel.vue'

const now = Math.floor(Date.now() / 1000)

const meta = {
  title: 'Components/AutoResearch/InsightsPanel',
  component: InsightsPanel,
  tags: ['autodocs'],
  argTypes: {
    insights: {
      control: 'object',
      description: 'List of ExperimentInsight objects synthesized from completed experiments',
    },
  },
} as Meta<typeof InsightsPanel>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Empty: Story = {
  args: {
    insights: [],
  },
}

export const HighConfidence: Story = {
  args: {
    insights: [
      {
        id: 'insight-001',
        statement: 'Warmup steps between 400 and 600 consistently reduce early training instability across all tested architectures.',
        confidence: 0.92,
        supporting_experiments: ['exp-001', 'exp-004', 'exp-007'],
        related_hyperparams: ['warmup_steps'],
        synthesized_at: now - 1200,
        session_id: 'session-abc-123',
      },
      {
        id: 'insight-002',
        statement: 'Cosine learning rate decay outperforms step decay by an average of 2.1% on val_bpb after 10k steps.',
        confidence: 0.88,
        supporting_experiments: ['exp-002', 'exp-005'],
        related_hyperparams: ['lr_schedule', 'learning_rate'],
        synthesized_at: now - 900,
        session_id: 'session-abc-123',
      },
    ],
  },
}

export const MixedConfidence: Story = {
  args: {
    insights: [
      {
        id: 'insight-high',
        statement: 'Pre-layer-norm placement significantly improves training stability for deeper models.',
        confidence: 0.91,
        supporting_experiments: ['exp-003', 'exp-006', 'exp-009'],
        related_hyperparams: ['pre_ln', 'num_layers'],
        synthesized_at: now - 3600,
        session_id: 'session-def-456',
      },
      {
        id: 'insight-mid',
        statement: 'Dropout values below 0.15 have negligible regularization effect on this dataset size.',
        confidence: 0.62,
        supporting_experiments: ['exp-010', 'exp-011'],
        related_hyperparams: ['dropout'],
        synthesized_at: now - 2400,
        session_id: 'session-def-456',
      },
      {
        id: 'insight-low',
        statement: 'Gradient clipping at 0.5 may improve stability in early epochs but requires more investigation.',
        confidence: 0.38,
        supporting_experiments: ['exp-008'],
        related_hyperparams: ['grad_clip'],
        synthesized_at: now - 1800,
        session_id: null,
      },
    ],
  },
}

export const ManyInsights: Story = {
  args: {
    insights: Array.from({ length: 8 }, (_, i) => ({
      id: `insight-bulk-${i + 1}`,
      statement: `Insight #${i + 1}: Parameter interaction ${i + 1} shows consistent effect across ${i + 2} experiments with varying batch sizes.`,
      confidence: Math.round((0.95 - i * 0.08) * 100) / 100,
      supporting_experiments: Array.from({ length: i + 1 }, (__, j) => `exp-bulk-${j + 1}`),
      related_hyperparams: ['batch_size', 'learning_rate'].slice(0, (i % 2) + 1),
      synthesized_at: now - (i + 1) * 600,
      session_id: i < 4 ? 'session-bulk-001' : null,
    })),
  },
}

export const SingleInsight: Story = {
  args: {
    insights: [
      {
        id: 'insight-single',
        statement: 'Increasing context length beyond 512 tokens yields diminishing returns on validation perplexity for this task.',
        confidence: 0.75,
        supporting_experiments: ['exp-ctx-001', 'exp-ctx-002', 'exp-ctx-003'],
        related_hyperparams: ['context_length', 'seq_len'],
        synthesized_at: now - 300,
        session_id: 'session-ctx-789',
      },
    ],
  },
}
