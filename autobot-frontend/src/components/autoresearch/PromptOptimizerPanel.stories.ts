// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import type { Meta, StoryObj } from '@storybook/vue3'
import PromptOptimizerPanel from './PromptOptimizerPanel.vue'

const now = Math.floor(Date.now() / 1000)

const sampleVariant = (id: string, score: number, round: number, text: string) => ({
  id,
  prompt_text: text,
  output: 'Sample output from this variant.',
  scores: { coherence: score, relevance: score - 0.1 },
  final_score: score,
  round_number: round,
  created_at: now - round * 300,
})

const meta = {
  title: 'Components/AutoResearch/PromptOptimizerPanel',
  component: PromptOptimizerPanel,
  tags: ['autodocs'],
  argTypes: {
    session: {
      control: 'object',
      description: 'Active OptimizationSession, or null when no session is running',
    },
    variants: {
      control: 'object',
      description: 'List of PromptVariant objects evaluated in the current or past session',
    },
  },
} as Meta<typeof PromptOptimizerPanel>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const NoSession: Story = {
  args: {
    session: null,
    variants: [],
  },
}

export const SessionRunning: Story = {
  args: {
    session: {
      id: 'opt-session-001',
      status: 'running',
      rounds_completed: 2,
      max_rounds: 5,
      best_variant: sampleVariant(
        'variant-best',
        7.42,
        2,
        'You are an expert research assistant. Analyze the hypothesis systematically and provide evidence-based conclusions.',
      ),
      baseline_score: 6.1,
      all_variants: [],
    },
    variants: [
      sampleVariant(
        'variant-001',
        6.10,
        1,
        'You are a helpful assistant. Answer the question as accurately as possible.',
      ),
      sampleVariant(
        'variant-002',
        7.42,
        2,
        'You are an expert research assistant. Analyze the hypothesis systematically and provide evidence-based conclusions.',
      ),
    ],
  },
}

export const SessionCompleted: Story = {
  args: {
    session: {
      id: 'opt-session-002',
      status: 'completed',
      rounds_completed: 5,
      max_rounds: 5,
      best_variant: sampleVariant(
        'variant-best-final',
        8.91,
        5,
        'You are a rigorous scientific researcher. Evaluate the given hypothesis against available evidence, identify confounding variables, and synthesize a structured verdict with confidence intervals.',
      ),
      baseline_score: 6.1,
      all_variants: [],
    },
    variants: [
      sampleVariant('variant-r1', 6.10, 1, 'You are a helpful assistant. Answer the question as accurately as possible.'),
      sampleVariant('variant-r2', 6.85, 2, 'You are a scientific assistant. Evaluate hypotheses based on empirical evidence.'),
      sampleVariant('variant-r3', 7.63, 3, 'You are a research scientist. Provide structured analysis of the hypothesis with supporting evidence.'),
      sampleVariant('variant-r4', 8.24, 4, 'You are an expert analyst. Systematically evaluate hypotheses with structured evidence and confidence scores.'),
      sampleVariant('variant-r5', 8.91, 5, 'You are a rigorous scientific researcher. Evaluate the given hypothesis against available evidence, identify confounding variables, and synthesize a structured verdict with confidence intervals.'),
    ],
  },
}

export const SessionFailed: Story = {
  args: {
    session: {
      id: 'opt-session-003',
      status: 'failed',
      rounds_completed: 1,
      max_rounds: 5,
      best_variant: null,
      baseline_score: 6.1,
      all_variants: [],
    },
    variants: [
      sampleVariant('variant-f1', 4.20, 1, 'You are a helpful assistant.'),
    ],
  },
}

export const WithVariantsNoSession: Story = {
  args: {
    session: null,
    variants: [
      sampleVariant(
        'variant-arch-001',
        7.10,
        1,
        'You are an expert in machine learning. Analyze training dynamics and suggest hyperparameter improvements.',
      ),
      sampleVariant(
        'variant-arch-002',
        8.05,
        2,
        'You are a senior ML engineer specializing in transformer architectures. Diagnose the experimental hypothesis and provide actionable optimization recommendations.',
      ),
      sampleVariant(
        'variant-arch-003',
        8.67,
        3,
        'You are a world-class deep learning researcher. Evaluate the training experiment hypothesis with domain expertise, citing relevant architectural trade-offs and empirical findings.',
      ),
    ],
  },
}
