/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * VoiceBundleInfo.stories.ts — Storybook stories for VoiceBundleInfo (GH#7422).
 */

import type { Meta } from '@storybook/vue3'
import VoiceBundleInfo from './VoiceBundleInfo.vue'
import { useVoiceBundle } from '@/composables/useVoiceBundle'
import { ref } from 'vue'

const meta: Meta = {
  title: 'Views/Voice/VoiceBundleInfo',
  component: VoiceBundleInfo,
}

export default meta

export const AdminOverride = {
  render: () => ({
    components: { VoiceBundleInfo },
    setup() {
      const { bundleInfo, loading, error } = useVoiceBundle()
      bundleInfo.value = {
        bundle_name: 'voice_admin',
        tool_count: 28,
        resolution: 'user_override',
      }
      loading.value = false
      error.value = null
      return {}
    },
    template: `<div style="padding:24px;max-width:320px;"><VoiceBundleInfo /></div>`,
  }),
}

export const RoleDefault = {
  render: () => ({
    components: { VoiceBundleInfo },
    setup() {
      const { bundleInfo, loading, error } = useVoiceBundle()
      bundleInfo.value = {
        bundle_name: 'voice_extended',
        tool_count: 19,
        resolution: 'role_default',
      }
      loading.value = false
      error.value = null
      return {}
    },
    template: `<div style="padding:24px;max-width:320px;"><VoiceBundleInfo /></div>`,
  }),
}

export const SystemDefault = {
  render: () => ({
    components: { VoiceBundleInfo },
    setup() {
      const { bundleInfo, loading, error } = useVoiceBundle()
      bundleInfo.value = {
        bundle_name: 'voice_safe',
        tool_count: 12,
        resolution: 'global_env',
      }
      loading.value = false
      error.value = null
      return {}
    },
    template: `<div style="padding:24px;max-width:320px;"><VoiceBundleInfo /></div>`,
  }),
}

export const Loading = {
  render: () => ({
    components: { VoiceBundleInfo },
    setup() {
      const { bundleInfo, loading, error } = useVoiceBundle()
      bundleInfo.value = null
      loading.value = true
      error.value = null
      return {}
    },
    template: `<div style="padding:24px;max-width:320px;"><VoiceBundleInfo /></div>`,
  }),
}

export const ErrorState = {
  render: () => ({
    components: { VoiceBundleInfo },
    setup() {
      const { bundleInfo, loading, error } = useVoiceBundle()
      bundleInfo.value = null
      loading.value = false
      error.value = 'Unable to load voice bundle'
      return {}
    },
    template: `<div style="padding:24px;max-width:320px;"><VoiceBundleInfo /></div>`,
  }),
}

export const NoBundleAssigned = {
  render: () => ({
    components: { VoiceBundleInfo },
    setup() {
      const { bundleInfo, loading, error } = useVoiceBundle()
      bundleInfo.value = null
      loading.value = false
      error.value = null
      return {}
    },
    template: `<div style="padding:24px;max-width:320px;"><VoiceBundleInfo /></div>`,
  }),
}
