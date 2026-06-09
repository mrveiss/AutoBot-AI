// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import NpuWorkerPairConfirmDialog from './NpuWorkerPairConfirmDialog.vue'
import type { NpuWorkerPairResult } from '@/composables/useNpuWorkers'

const meta = {
  title: 'Components/Admin/NpuWorkerPairConfirmDialog',
  component: NpuWorkerPairConfirmDialog,
} as Meta<typeof NpuWorkerPairConfirmDialog>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories
type Story = StoryObj<any>

const inferenceResult: NpuWorkerPairResult = {
  success: true,
  worker_id: 'npu-worker-rtx3060',
  recommended_profile: 'inference',
  recommended_models: [{ id: 'gemma-3-4b', reason: 'fits in 8GB VRAM' }],
  vram_gb: 8.0,
  compute_class: 'consumer-gpu',
  capabilities_summary: 'CUDA, 1× RTX 3060 8 GB, 32 GB RAM',
}

const embeddingResult: NpuWorkerPairResult = {
  success: true,
  worker_id: 'npu-worker-cpu-only',
  recommended_profile: 'embedding',
  recommended_models: [],
  vram_gb: 0,
  compute_class: 'cpu-only',
  capabilities_summary: 'No GPU detected, 32 GB RAM — embedding workloads only',
}

const noSuggestionResult: NpuWorkerPairResult = {
  success: true,
  worker_id: 'npu-worker-unknown',
  recommended_profile: null,
  recommended_models: null,
  vram_gb: null,
  compute_class: null,
  capabilities_summary: null,
}

export const InferenceRecommended: Story = {
  render: () => ({
    components: { NpuWorkerPairConfirmDialog },
    setup() {
      const show = ref(true)
      return { show, pairResult: inferenceResult }
    },
    template: `
      <NpuWorkerPairConfirmDialog
        v-model="show"
        :pairResult="pairResult"
        @confirm="(p) => console.log('confirmed', p)"
        @cancel="console.log('cancelled')"
      />
    `,
  }),
}

export const EmbeddingRecommended: Story = {
  render: () => ({
    components: { NpuWorkerPairConfirmDialog },
    setup() {
      const show = ref(true)
      return { show, pairResult: embeddingResult }
    },
    template: `
      <NpuWorkerPairConfirmDialog
        v-model="show"
        :pairResult="pairResult"
        @confirm="(p) => console.log('confirmed', p)"
        @cancel="console.log('cancelled')"
      />
    `,
  }),
}

export const NoSuggestion: Story = {
  render: () => ({
    components: { NpuWorkerPairConfirmDialog },
    setup() {
      const show = ref(true)
      return { show, pairResult: noSuggestionResult }
    },
    template: `
      <NpuWorkerPairConfirmDialog
        v-model="show"
        :pairResult="pairResult"
        @confirm="(p) => console.log('confirmed', p)"
        @cancel="console.log('cancelled')"
      />
    `,
  }),
}
