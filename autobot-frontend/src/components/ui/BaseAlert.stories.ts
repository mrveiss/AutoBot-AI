import type { Meta, StoryObj } from '@storybook/vue3';
import BaseAlert from './BaseAlert.vue';

const meta = {
  title: 'Components/UI/BaseAlert',
  component: BaseAlert,
  argTypes: {
    type: {
      control: 'select',
      options: ['success', 'error', 'warning', 'info'],
      description: 'Alert type',
    },
    title: {
      control: 'text',
      description: 'Alert title',
    },
    message: {
      control: 'text',
      description: 'Alert message',
    },
    closable: {
      control: 'boolean',
      description: 'Show close button',
    },
    icon: {
      control: 'boolean',
      description: 'Show icon',
    },
  },
} as Meta<typeof BaseAlert>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Success: Story = {
  args: {
    type: 'success',
    title: 'Success',
    message: 'Operation completed successfully',
  },
};

export const Error: Story = {
  args: {
    type: 'error',
    title: 'Error',
    message: 'An error occurred while processing your request',
  },
};

export const Warning: Story = {
  args: {
    type: 'warning',
    title: 'Warning',
    message: 'Please review this information before proceeding',
  },
};

export const Info: Story = {
  args: {
    type: 'info',
    title: 'Information',
    message: 'Here is some important information for you',
  },
};

export const Closable: Story = {
  args: {
    type: 'info',
    title: 'Closable Alert',
    message: 'This alert can be dismissed by clicking the close button',
    closable: true,
  },
};

export const NoIcon: Story = {
  args: {
    type: 'success',
    title: 'Success',
    message: 'Operation completed without displaying an icon',
    icon: false,
  },
};

export const AllTypes: Story = {
  render: () => ({
    components: { BaseAlert },
    template: `
      <div class="space-y-4">
        <BaseAlert type="success" title="Success" message="This is a success alert message" closable />
        <BaseAlert type="error" title="Error" message="This is an error alert message" closable />
        <BaseAlert type="warning" title="Warning" message="This is a warning alert message" closable />
        <BaseAlert type="info" title="Information" message="This is an info alert message" closable />
      </div>
    `,
  }),
};
