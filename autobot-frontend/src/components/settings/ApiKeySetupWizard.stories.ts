// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta } from '@storybook/vue3';
import ApiKeySetupWizard from './ApiKeySetupWizard.vue';
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
import type { StoryObj } from '@storybook/vue3';
type Story = StoryObj<any>;

const meta = {
  title: 'Components/Settings/ApiKeySetupWizard',
  component: ApiKeySetupWizard,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'boolean',
      description: 'Controls the visibility of the wizard modal (v-model)',
    },
  },
} as Meta<typeof ApiKeySetupWizard>;

export default meta;

export const Open: Story = {
  args: {
    modelValue: true,
  },
};

export const Closed: Story = {
  args: {
    modelValue: false,
  },
};

export const StepOne: Story = {
  name: 'Step 1 – Role Selection',
  args: {
    modelValue: true,
  },
};

export const WithRolesSelected: Story = {
  name: 'With Roles Pre-selected (render)',
  render: () => ({
    components: { ApiKeySetupWizard },
    data() {
      return { open: true };
    },
    template: `<ApiKeySetupWizard v-model="open" />`,
  }),
};

export const ClosedState: Story = {
  name: 'Modal Hidden',
  render: () => ({
    components: { ApiKeySetupWizard },
    data() {
      return { open: false };
    },
    template: `
      <div>
        <p style="color:#aaa">Modal is closed — modelValue=false</p>
        <ApiKeySetupWizard v-model="open" />
      </div>
    `,
  }),
};
