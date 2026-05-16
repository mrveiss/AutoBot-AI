// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import { ref } from 'vue'
import GovernanceModeSelector from './GovernanceModeSelector.vue'

const meta = {
  title: 'Skills/GovernanceModeSelector',
  component: GovernanceModeSelector,
  tags: ['autodocs'],
} satisfies Meta<typeof GovernanceModeSelector>

export default meta

export const FullAuto = {
  render: (args: any) => ({
    components: { GovernanceModeSelector },
    setup() {
      const mode = ref('full_auto')
      return { mode, args }
    },
    template: '<GovernanceModeSelector v-model="mode" />',
  }),
  args: {},
}

export const SemiAuto = {
  render: (args: any) => ({
    components: { GovernanceModeSelector },
    setup() {
      const mode = ref('semi_auto')
      return { mode, args }
    },
    template: '<GovernanceModeSelector v-model="mode" />',
  }),
  args: {},
}

export const Locked = {
  render: (args: any) => ({
    components: { GovernanceModeSelector },
    setup() {
      const mode = ref('locked')
      return { mode, args }
    },
    template: '<GovernanceModeSelector v-model="mode" />',
  }),
  args: {},
}
