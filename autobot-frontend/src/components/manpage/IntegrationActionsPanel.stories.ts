// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import type { Meta, StoryObj } from '@storybook/vue3';
import IntegrationActionsPanel from './IntegrationActionsPanel.vue';

const meta = {
  title: 'Components/ManPage/IntegrationActionsPanel',
  component: IntegrationActionsPanel,
  tags: ['autodocs'],
  argTypes: {
    loading: {
      control: 'object',
      description: 'Loading state for each action button',
    },
    canInitialize: {
      control: 'boolean',
      description: 'Whether the initialize action is available',
    },
    canIntegrate: {
      control: 'boolean',
      description: 'Whether the integrate action is available',
    },
    hasIntegration: {
      control: 'boolean',
      description: 'Whether an integration exists (enables test search)',
    },
  },
} as Meta<typeof IntegrationActionsPanel>;

export default meta;
// #7273: relaxed to StoryObj<Record<string, unknown>> for render-only stories that don't match component props
type Story = StoryObj<Record<string, unknown>>;

export const Default: Story = {
  args: {
    loading: { initialize: false, integrate: false, search: false },
    canInitialize: true,
    canIntegrate: true,
    hasIntegration: true,
  },
};

export const AllDisabled: Story = {
  args: {
    loading: { initialize: false, integrate: false, search: false },
    canInitialize: false,
    canIntegrate: false,
    hasIntegration: false,
  },
};

export const InitializeLoading: Story = {
  args: {
    loading: { initialize: true, integrate: false, search: false },
    canInitialize: true,
    canIntegrate: true,
    hasIntegration: false,
  },
};

export const IntegrateLoading: Story = {
  args: {
    loading: { initialize: false, integrate: true, search: false },
    canInitialize: true,
    canIntegrate: true,
    hasIntegration: true,
  },
};

export const SearchLoading: Story = {
  args: {
    loading: { initialize: false, integrate: false, search: true },
    canInitialize: true,
    canIntegrate: true,
    hasIntegration: true,
  },
};
