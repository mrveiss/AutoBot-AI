// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import SkipLink from './SkipLink.vue'

const meta = {
  title: 'Common/SkipLink',
  component: SkipLink,
  tags: ['autodocs'],
  argTypes: {
    target: { control: 'text' },
    label: { control: 'text' },
  },
} satisfies Meta<typeof SkipLink>

export default meta

export const Default = {
  args: {
    target: '#main-content',
    label: 'Skip to main content',
  },
}

export const CustomLabel = {
  args: {
    target: '#nav',
    label: 'Skip to navigation',
  },
}
