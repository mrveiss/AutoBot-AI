import type { Meta, StoryObj } from '@storybook/vue3';
import BaseButton from './BaseButton.vue';

const meta = {
  title: 'Components/Base/BaseButton',
  component: BaseButton,
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'success', 'error', 'warning', 'info', 'light', 'dark', 'outline-solid', 'ghost', 'link'],
      description: 'Button style variant',
    },
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg', 'xl'],
      description: 'Button size',
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the button',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading spinner',
    },
    block: {
      control: 'boolean',
      description: 'Full width button',
    },
    rounded: {
      control: 'boolean',
      description: 'Rounded corners',
    },
    label: {
      control: 'text',
      description: 'Button text label',
    },
    htmlType: {
      control: 'select',
      options: ['button', 'submit', 'reset'],
      description: 'HTML button type',
    },
  },
} as Meta<typeof BaseButton>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Primary: Story = {
  args: {
    variant: 'primary',
    label: 'Primary Button',
  },
};

export const Secondary: Story = {
  args: {
    variant: 'secondary',
    label: 'Secondary Button',
  },
};

export const Success: Story = {
  args: {
    variant: 'success',
    label: 'Success Button',
  },
};

export const Danger: Story = {
  args: {
    variant: 'error',
    label: 'Danger Button',
  },
};

export const Warning: Story = {
  args: {
    variant: 'warning',
    label: 'Warning Button',
  },
};

export const Info: Story = {
  args: {
    variant: 'info',
    label: 'Info Button',
  },
};

export const Disabled: Story = {
  args: {
    variant: 'primary',
    label: 'Disabled Button',
    disabled: true,
  },
};

export const Loading: Story = {
  args: {
    variant: 'primary',
    label: 'Loading Button',
    loading: true,
  },
};

export const Block: Story = {
  args: {
    variant: 'primary',
    label: 'Full Width Button',
    block: true,
  },
};

export const Small: Story = {
  args: {
    variant: 'primary',
    label: 'Small Button',
    size: 'sm',
  },
};

export const Large: Story = {
  args: {
    variant: 'primary',
    label: 'Large Button',
    size: 'lg',
  },
};

export const Rounded: Story = {
  args: {
    variant: 'primary',
    label: 'Rounded Button',
    rounded: true,
  },
};

export const AllSizes: Story = {
  render: () => ({
    components: { BaseButton },
    template: `
      <div class="flex gap-2 flex-wrap">
        <BaseButton size="xs" label="XS" />
        <BaseButton size="sm" label="SM" />
        <BaseButton size="md" label="MD" />
        <BaseButton size="lg" label="LG" />
        <BaseButton size="xl" label="XL" />
      </div>
    `,
  }),
};

export const AllVariants: Story = {
  render: () => ({
    components: { BaseButton },
    template: `
      <div class="flex gap-2 flex-wrap">
        <BaseButton variant="primary" label="Primary" />
        <BaseButton variant="secondary" label="Secondary" />
        <BaseButton variant="success" label="Success" />
        <BaseButton variant="error" label="Danger" />
        <BaseButton variant="warning" label="Warning" />
        <BaseButton variant="info" label="Info" />
        <BaseButton variant="light" label="Light" />
        <BaseButton variant="dark" label="Dark" />
        <BaseButton variant="ghost" label="Ghost" />
        <BaseButton variant="link" label="Link" />
      </div>
    `,
  }),
};
