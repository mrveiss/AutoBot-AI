// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import BaseInput from './BaseInput.vue';

const meta = {
  title: 'Components/Base/BaseInput',
  component: BaseInput,
  argTypes: {
    modelValue: {
      control: 'text',
      description: 'Input value (v-model)',
    },
    type: {
      control: 'select',
      options: ['text', 'email', 'password', 'number', 'url', 'date', 'time'],
      description: 'HTML input type',
    },
    placeholder: {
      control: 'text',
      description: 'Placeholder text',
    },
    label: {
      control: 'text',
      description: 'Input label',
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the input',
    },
    readonly: {
      control: 'boolean',
      description: 'Make input read-only',
    },
    required: {
      control: 'boolean',
      description: 'Mark as required',
    },
    error: {
      control: 'text',
      description: 'Error message',
    },
    helperText: {
      control: 'text',
      description: 'Helper text',
    },
    clearable: {
      control: 'boolean',
      description: 'Show clear button',
    },
  },
} as Meta<typeof BaseInput>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    modelValue: '',
    placeholder: 'Enter text...',
    label: 'Input Label',
  },
};

export const WithLabel: Story = {
  args: {
    modelValue: '',
    label: 'Email Address',
    placeholder: 'your@email.com',
    type: 'email',
  },
};

export const Required: Story = {
  args: {
    modelValue: '',
    label: 'Required Field',
    placeholder: 'Enter something...',
    required: true,
  },
};

export const WithError: Story = {
  args: {
    modelValue: 'invalid-email',
    label: 'Email',
    type: 'email',
    error: 'Please enter a valid email address',
  },
};

export const WithHelperText: Story = {
  args: {
    modelValue: '',
    label: 'Password',
    type: 'password',
    helperText: 'Must be at least 8 characters',
  },
};

export const Disabled: Story = {
  args: {
    modelValue: 'Disabled value',
    label: 'Disabled Input',
    disabled: true,
  },
};

export const ReadOnly: Story = {
  args: {
    modelValue: 'Read-only value',
    label: 'Read-Only Input',
    readonly: true,
  },
};

export const Clearable: Story = {
  args: {
    modelValue: 'Clear me',
    label: 'Clearable Input',
    clearable: true,
    placeholder: 'Click X to clear',
  },
};

export const Email: Story = {
  args: {
    modelValue: '',
    type: 'email',
    label: 'Email Address',
    placeholder: 'user@example.com',
  },
};

export const Password: Story = {
  args: {
    modelValue: '',
    type: 'password',
    label: 'Password',
    placeholder: '••••••••',
  },
};

export const Number: Story = {
  args: {
    modelValue: '',
    type: 'number',
    label: 'Age',
    placeholder: 'Enter your age',
  },
};

export const Date: Story = {
  args: {
    modelValue: '',
    type: 'date',
    label: 'Date of Birth',
  },
};

export const InputTypes: Story = {
  render: () => ({
    components: { BaseInput },
    template: `
      <div class="space-y-4">
        <BaseInput type="text" label="Text Input" placeholder="Enter text" />
        <BaseInput type="email" label="Email Input" placeholder="user@example.com" />
        <BaseInput type="password" label="Password Input" placeholder="••••••••" />
        <BaseInput type="number" label="Number Input" placeholder="Enter number" />
        <BaseInput type="url" label="URL Input" placeholder="https://example.com" />
        <BaseInput type="date" label="Date Input" />
      </div>
    `,
  }),
};
