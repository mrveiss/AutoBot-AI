// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import PresetsSettingsPanel from './PresetsSettingsPanel.vue'

const meta = {
  title: 'Components/Settings/PresetsSettingsPanel',
  component: PresetsSettingsPanel,
  tags: ['autodocs'],
} as Meta<typeof PresetsSettingsPanel>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories
type Story = StoryObj<any>

export const Default: Story = {}
