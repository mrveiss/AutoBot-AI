// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import RestartConfirmDialog from './RestartConfirmDialog.vue'

const meta = {
  title: 'Orchestration/RestartConfirmDialog',
  component: RestartConfirmDialog,
  tags: ['autodocs'],
  argTypes: {
    show: { control: 'boolean' },
    title: { control: 'text' },
    message: { control: 'text' },
    confirmButtonText: { control: 'text' },
    isProcessing: { control: 'boolean' },
  },
} satisfies Meta<typeof RestartConfirmDialog>

export default meta

export const Visible = {
  args: {
    show: true,
    title: 'Restart Service',
    message: 'Are you sure you want to restart autobot-backend? This will cause a brief interruption.',
    confirmButtonText: 'Restart',
    isProcessing: false,
  },
}

export const Processing = {
  args: {
    show: true,
    title: 'Restarting...',
    message: 'Restarting all services on node prod-01. This may take up to 30 seconds.',
    confirmButtonText: 'Restarting...',
    isProcessing: true,
  },
}

export const Hidden = {
  args: {
    show: false,
    title: 'Confirm Action',
    message: 'This dialog is hidden.',
    confirmButtonText: 'Confirm',
    isProcessing: false,
  },
}
