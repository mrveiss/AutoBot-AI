// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import NpuWorkerPairConfirmDialog from '../NpuWorkerPairConfirmDialog.vue'
import type { NpuWorkerPairResult } from '@/composables/useNpuWorkers'

const inferenceResult: NpuWorkerPairResult = {
  success: true,
  worker_id: 'npu-worker-rtx3060',
  recommended_profile: 'inference',
  recommended_models: [{ id: 'gemma-3-4b', reason: 'fits in 8GB VRAM' }],
  vram_gb: 8.0,
  compute_class: 'consumer-gpu',
  capabilities_summary: 'CUDA, 1× RTX 3060 8 GB, 32 GB RAM',
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

// Teleport renders to document.body — query from there
function q<T extends Element = Element>(sel: string): T | null {
  return document.body.querySelector<T>(sel)
}

async function click(sel: string) {
  const el = q<HTMLElement>(sel)
  if (!el) throw new Error(`Element not found: ${sel}`)
  el.click()
  await nextTick()
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const wrappers: VueWrapper<any>[] = []

function mountDialog(pairResult: NpuWorkerPairResult, modelValue = true) {
  const w = mount(NpuWorkerPairConfirmDialog, {
    props: { modelValue, pairResult },
    attachTo: document.body,
  })
  wrappers.push(w)
  return w
}

afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers.length = 0
})

describe('NpuWorkerPairConfirmDialog', () => {
  describe('profile selector pre-fill', () => {
    it('pre-fills profile selector with recommended_profile', () => {
      mountDialog(inferenceResult)
      const select = q<HTMLSelectElement>('select')
      expect(select?.value).toBe('inference')
    })

    it('defaults to inference when recommended_profile is null', () => {
      mountDialog(noSuggestionResult)
      const select = q<HTMLSelectElement>('select')
      expect(select?.value).toBe('inference')
    })

    it('resets to recommended_profile when dialog reopens', async () => {
      const wrapper = mountDialog(inferenceResult)
      const select = q<HTMLSelectElement>('select')!

      // Override to mixed via DOM + trigger Vue update
      select.value = 'mixed'
      select.dispatchEvent(new Event('change'))
      await nextTick()
      expect(select.value).toBe('mixed')

      // Close and reopen
      await wrapper.setProps({ modelValue: false })
      await wrapper.setProps({ modelValue: true })

      expect(q<HTMLSelectElement>('select')?.value).toBe('inference')
    })
  })

  describe('capabilities_summary tooltip', () => {
    it('shows Why? button when capabilities_summary is present', () => {
      mountDialog(inferenceResult)
      expect(q('.pair-confirm-why-btn')).toBeTruthy()
    })

    it('hides Why? button when capabilities_summary is null', () => {
      mountDialog(noSuggestionResult)
      expect(q('.pair-confirm-why-btn')).toBeNull()
    })

    it('shows tooltip on mouseenter', async () => {
      mountDialog(inferenceResult)
      const btn = q<HTMLElement>('.pair-confirm-why-btn')!
      btn.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
      await nextTick()
      const tooltip = q('.pair-confirm-tooltip')
      expect(tooltip).toBeTruthy()
      expect(tooltip?.textContent).toContain('RTX 3060')
    })

    it('hides tooltip on mouseleave', async () => {
      mountDialog(inferenceResult)
      const btn = q<HTMLElement>('.pair-confirm-why-btn')!
      btn.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
      await nextTick()
      btn.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }))
      await nextTick()
      expect(q('.pair-confirm-tooltip')).toBeNull()
    })
  })

  describe('manual override', () => {
    it('shows override note when profile changed from recommendation', async () => {
      mountDialog(inferenceResult)
      const select = q<HTMLSelectElement>('select')!
      select.value = 'mixed'
      select.dispatchEvent(new Event('change'))
      await nextTick()
      expect(q('.pair-confirm-override-note')).toBeTruthy()
    })

    it('hides override note when profile matches recommendation', async () => {
      mountDialog(inferenceResult)
      const select = q<HTMLSelectElement>('select')!
      select.value = 'mixed'
      select.dispatchEvent(new Event('change'))
      await nextTick()
      select.value = 'inference'
      select.dispatchEvent(new Event('change'))
      await nextTick()
      expect(q('.pair-confirm-override-note')).toBeNull()
    })

    it('emits confirm with overridden profile', async () => {
      const wrapper = mountDialog(inferenceResult)
      const select = q<HTMLSelectElement>('select')!
      select.value = 'embedding'
      select.dispatchEvent(new Event('change'))
      await nextTick()

      await click('.pair-confirm-btn-confirm')

      const events = wrapper.emitted('confirm')
      expect(events).toHaveLength(1)
      expect(events![0]).toEqual([{ workerId: 'npu-worker-rtx3060', profile: 'embedding' }])
    })

    it('emits confirm with recommended profile when no override', async () => {
      const wrapper = mountDialog(inferenceResult)
      await click('.pair-confirm-btn-confirm')

      const events = wrapper.emitted('confirm')
      expect(events).toHaveLength(1)
      expect(events![0]).toEqual([{ workerId: 'npu-worker-rtx3060', profile: 'inference' }])
    })
  })

  describe('cancel', () => {
    it('emits cancel on cancel button click', async () => {
      const wrapper = mountDialog(inferenceResult)
      await click('.pair-confirm-btn-cancel')
      expect(wrapper.emitted('cancel')).toHaveLength(1)
    })

    it('emits update:modelValue=false on cancel', async () => {
      const wrapper = mountDialog(inferenceResult)
      await click('.pair-confirm-btn-cancel')
      expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
    })
  })

  describe('visibility', () => {
    it('renders dialog when modelValue is true', () => {
      mountDialog(inferenceResult, true)
      expect(q('.pair-confirm-dialog')).toBeTruthy()
    })

    it('hides dialog when modelValue is false', () => {
      mountDialog(inferenceResult, false)
      expect(q('.pair-confirm-dialog')).toBeNull()
    })
  })
})
