import type { Meta, StoryObj } from '@storybook/vue3';
import EndpointEnforcement from './EndpointEnforcement.vue';

const meta = {
  title: 'Components/FeatureFlags/EndpointEnforcement',
  component: EndpointEnforcement,
  tags: ['autodocs'],
  argTypes: {
    overrides: {
      control: 'object',
      description: 'Map of endpoint path to EnforcementMode override',
    },
    globalMode: {
      control: 'select',
      options: ['disabled', 'log_only', 'enforced'],
      description: 'The global default enforcement mode',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading/saving state',
    },
  },
} as Meta<typeof EndpointEnforcement>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const WithOverrides: Story = {
  args: {
    overrides: {
      '/api/admin/users': 'enforced',
      '/api/settings/global': 'log_only',
      '/api/debug/dump': 'disabled',
    },
    globalMode: 'log_only',
    loading: false,
  },
};

export const Empty: Story = {
  args: {
    overrides: {},
    globalMode: 'log_only',
    loading: false,
  },
};

export const GlobalEnforced: Story = {
  args: {
    overrides: {
      '/api/public/health': 'disabled',
    },
    globalMode: 'enforced',
    loading: false,
  },
};

export const GlobalDisabled: Story = {
  args: {
    overrides: {
      '/api/admin/users': 'enforced',
      '/api/payments/process': 'enforced',
    },
    globalMode: 'disabled',
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    overrides: {
      '/api/admin/users': 'enforced',
    },
    globalMode: 'log_only',
    loading: true,
  },
};
