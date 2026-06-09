// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * VoiceBundleInfo.stories.ts — Storybook stories for VoiceBundleInfo (GH#7422).
 *
 * State is injected via VOICE_BUNDLE_STATE_KEY so each story's decorator provides
 * its own reactive refs, shared with the component instance.  This avoids the
 * broken pattern of calling useVoiceBundle() in story setup() — that creates
 * separate ref instances that the component never reads (MVA-1162).
 */

import type { Meta, StoryObj } from '@storybook/vue3'
import VoiceBundleInfo from './VoiceBundleInfo.vue'
import { VOICE_BUNDLE_STATE_KEY } from '@/composables/useVoiceBundle'
import type { UserBundleInfo, VoiceBundleInjectedState } from '@/composables/useVoiceBundle'
import { ref, provide } from 'vue'

// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

const meta: Meta = {
  title: 'Views/Voice/VoiceBundleInfo',
  component: VoiceBundleInfo,
}

export default meta

function withState(state: {
  bundleInfo: UserBundleInfo | null
  loading: boolean
  error: string | null
}): Story['decorators'] {
  return [
    () => ({
      setup() {
        const injected: VoiceBundleInjectedState = {
          bundleInfo: ref(state.bundleInfo),
          loading: ref(state.loading),
          error: ref(state.error),
        }
        provide(VOICE_BUNDLE_STATE_KEY, injected)
        return {}
      },
      template: '<story />',
    }),
  ]
}

const wrapper = `<div style="padding:24px;max-width:320px;"><VoiceBundleInfo /></div>`

export const AdminOverride: Story = {
  decorators: withState({
    bundleInfo: { bundle_name: 'voice_admin', tool_count: 28, resolution: 'user_override' },
    loading: false,
    error: null,
  }),
  render: () => ({ components: { VoiceBundleInfo }, template: wrapper }),
}

export const RoleDefault: Story = {
  decorators: withState({
    bundleInfo: { bundle_name: 'voice_extended', tool_count: 19, resolution: 'role_default' },
    loading: false,
    error: null,
  }),
  render: () => ({ components: { VoiceBundleInfo }, template: wrapper }),
}

export const SystemDefault: Story = {
  decorators: withState({
    bundleInfo: { bundle_name: 'voice_safe', tool_count: 12, resolution: 'global_env' },
    loading: false,
    error: null,
  }),
  render: () => ({ components: { VoiceBundleInfo }, template: wrapper }),
}

export const Loading: Story = {
  decorators: withState({ bundleInfo: null, loading: true, error: null }),
  render: () => ({ components: { VoiceBundleInfo }, template: wrapper }),
}

export const ErrorState: Story = {
  decorators: withState({
    bundleInfo: null,
    loading: false,
    error: 'Unable to load voice bundle',
  }),
  render: () => ({ components: { VoiceBundleInfo }, template: wrapper }),
}

export const NoBundleAssigned: Story = {
  decorators: withState({ bundleInfo: null, loading: false, error: null }),
  render: () => ({ components: { VoiceBundleInfo }, template: wrapper }),
}
