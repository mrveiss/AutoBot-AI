// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import ExperimentTimeline from './ExperimentTimeline.vue'

const now = Math.floor(Date.now() / 1000)

const meta = {
  title: 'Components/AutoResearch/ExperimentTimeline',
  component: ExperimentTimeline,
  tags: ['autodocs'],
  argTypes: {
    experiments: {
      control: 'object',
      description: 'List of experiment objects to display in the timeline',
    },
    pendingApprovals: {
      control: 'object',
      description: 'List of pending approval requests keyed by experiment_id',
    },
  },
} as Meta<typeof ExperimentTimeline>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Empty: Story = {
  args: {
    experiments: [],
    pendingApprovals: [],
  },
}

export const MixedStates: Story = {
  args: {
    experiments: [
      {
        id: 'exp-001',
        hypothesis: 'Increasing warmup steps to 500 improves early training stability',
        description: 'Warmup steps experiment',
        state: 'completed',
        hyperparams: { warmup_steps: 500 },
        result: {
          val_bpb: 2.3956,
          train_loss: 1.42,
          val_loss: 1.58,
          steps_completed: 10000,
          tokens_per_second: 8400,
          wall_time_seconds: 310,
          error_message: null,
        },
        baseline_val_bpb: 2.4812,
        tags: ['warmup'],
        created_at: now - 3600,
        started_at: now - 3500,
        completed_at: now - 3200,
      },
      {
        id: 'exp-002',
        hypothesis: 'Smaller batch size reduces gradient noise',
        description: 'Batch size reduction experiment',
        state: 'running',
        hyperparams: { batch_size: 16 },
        result: null,
        baseline_val_bpb: 2.4812,
        tags: ['batch'],
        created_at: now - 1800,
        started_at: now - 1700,
        completed_at: null,
      },
      {
        id: 'exp-003',
        hypothesis: 'Cosine LR schedule outperforms step decay',
        description: 'LR schedule comparison',
        state: 'pending',
        hyperparams: { lr_schedule: 'cosine' },
        result: null,
        baseline_val_bpb: 2.4812,
        tags: ['lr'],
        created_at: now - 600,
        started_at: null,
        completed_at: null,
      },
    ],
    pendingApprovals: [],
  },
}

export const WithFailedExperiment: Story = {
  args: {
    experiments: [
      {
        id: 'exp-fail-001',
        hypothesis: 'Very high learning rate for fast convergence',
        description: 'High LR experiment',
        state: 'failed',
        hyperparams: { learning_rate: 0.1 },
        result: {
          val_bpb: null,
          train_loss: null,
          val_loss: null,
          steps_completed: 42,
          tokens_per_second: null,
          wall_time_seconds: 15,
          error_message: 'NaN loss after 42 steps — training diverged',
        },
        baseline_val_bpb: 2.4812,
        tags: ['lr', 'unstable'],
        created_at: now - 7200,
        started_at: now - 7100,
        completed_at: now - 7085,
      },
    ],
    pendingApprovals: [],
  },
}

export const WithPendingApproval: Story = {
  args: {
    experiments: [
      {
        id: 'exp-approve-001',
        hypothesis: 'Layer-norm placement before attention improves stability',
        description: 'Pre-LN architecture test',
        state: 'completed',
        hyperparams: { pre_ln: true },
        result: {
          val_bpb: 2.3124,
          train_loss: 1.38,
          val_loss: 1.52,
          steps_completed: 10000,
          tokens_per_second: 7900,
          wall_time_seconds: 380,
          error_message: null,
        },
        baseline_val_bpb: 2.4812,
        tags: ['architecture'],
        created_at: now - 900,
        started_at: now - 800,
        completed_at: now - 400,
      },
    ],
    pendingApprovals: [
      {
        session_id: 'session-abc-123',
        experiment_id: 'exp-approve-001',
        details: { baseline_val_bpb: 2.4812, result_val_bpb: 2.3124 },
      },
    ],
  },
}

export const KeptAndDiscarded: Story = {
  args: {
    experiments: [
      {
        id: 'exp-kept-001',
        hypothesis: 'Dropout 0.1 prevents overfitting',
        description: 'Dropout experiment',
        state: 'kept',
        hyperparams: { dropout: 0.1 },
        result: {
          val_bpb: 2.3800,
          train_loss: 1.40,
          val_loss: 1.55,
          steps_completed: 10000,
          tokens_per_second: 8200,
          wall_time_seconds: 295,
          error_message: null,
        },
        baseline_val_bpb: 2.4812,
        tags: ['regularization'],
        created_at: now - 5400,
        started_at: now - 5300,
        completed_at: now - 5000,
      },
      {
        id: 'exp-disc-001',
        hypothesis: 'Gradient clipping at 0.5 stabilizes training',
        description: 'Gradient clipping test',
        state: 'discarded',
        hyperparams: { grad_clip: 0.5 },
        result: {
          val_bpb: 2.5200,
          train_loss: 1.55,
          val_loss: 1.70,
          steps_completed: 10000,
          tokens_per_second: 8100,
          wall_time_seconds: 302,
          error_message: null,
        },
        baseline_val_bpb: 2.4812,
        tags: ['optimization'],
        created_at: now - 9000,
        started_at: now - 8900,
        completed_at: now - 8600,
      },
    ],
    pendingApprovals: [],
  },
}
