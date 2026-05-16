// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import type { PostSyncAction } from '@/composables/useRoles'
import PostSyncActionBadges from './PostSyncActionBadges.vue'

const sampleActions: PostSyncAction[] = [
  {
    role_name: 'autobot-backend',
    display_name: 'AutoBot Backend',
    category: 'restart',
    label: 'Restart Backend',
    command: null,
    systemd_service: 'autobot-backend',
  },
  {
    role_name: 'db-migrate',
    display_name: 'Database Migration',
    category: 'schema',
    label: 'Run Migrations',
    command: 'python manage.py migrate',
    systemd_service: null,
  },
  {
    role_name: 'npm-install',
    display_name: 'NPM Install',
    category: 'install',
    label: 'Install Packages',
    command: 'npm install',
    systemd_service: null,
  },
]

const meta = {
  title: 'Orchestration/PostSyncActionBadges',
  component: PostSyncActionBadges,
  tags: ['autodocs'],
} satisfies Meta<typeof PostSyncActionBadges>

export default meta

export const Default = {
  args: {
    actions: sampleActions,
    executingAction: null,
  },
}

export const Executing = {
  args: {
    actions: sampleActions,
    executingAction: { roleName: 'autobot-backend', category: 'restart' },
  },
}

export const Empty = {
  args: {
    actions: [],
    executingAction: null,
  },
}
