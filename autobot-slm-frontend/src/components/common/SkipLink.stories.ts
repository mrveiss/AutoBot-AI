// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import SkipLink from './SkipLink.vue'

const meta = {
  title: 'Common/SkipLink',
  component: SkipLink,
  tags: ['autodocs'],
  argTypes: {
    target: { control: 'text' },
  },
} satisfies Meta<typeof SkipLink>

export default meta

export const Default = {
  args: {
    target: '#main-content',
  },
}

export const CustomTarget = {
  args: {
    target: '#nav',
  },
}
