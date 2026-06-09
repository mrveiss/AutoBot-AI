// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import EnforcementModeSelector from './EnforcementModeSelector.vue';

const meta = {
  title: 'Components/FeatureFlags/EnforcementModeSelector',
  component: EnforcementModeSelector,
  tags: ['autodocs'],
  argTypes: {
    currentMode: {
      control: 'select',
      options: ['disabled', 'log_only', 'enforced'],
      description: 'Currently active enforcement mode',
    },
    loading: {
      control: 'boolean',
      description: 'Show pending/updating state on the selected mode option',
    },
  },
} as Meta<typeof EnforcementModeSelector>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Disabled: Story = {
  args: {
    currentMode: 'disabled',
    loading: false,
  },
};

export const LogOnly: Story = {
  args: {
    currentMode: 'log_only',
    loading: false,
  },
};

export const Enforced: Story = {
  args: {
    currentMode: 'enforced',
    loading: false,
  },
};

export const Updating: Story = {
  args: {
    currentMode: 'log_only',
    loading: true,
  },
};

export const Interactive: Story = {
  render: () => ({
    components: { EnforcementModeSelector },
    data() {
      return { mode: 'disabled' as 'disabled' | 'log_only' | 'enforced', busy: false };
    },
    methods: {
      onUpdate(newMode: 'disabled' | 'log_only' | 'enforced') {
        this.busy = true;
        setTimeout(() => {
          this.mode = newMode;
          this.busy = false;
        }, 800);
      },
    },
    template: `
      <EnforcementModeSelector
        :current-mode="mode"
        :loading="busy"
        @update:mode="onUpdate"
      />
    `,
  }),
};
