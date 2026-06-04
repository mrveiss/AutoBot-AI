import type { Meta, StoryObj } from '@storybook/vue3';
import ThemeToggle from './ThemeToggle.vue';

const meta = {
  title: 'Components/UI/ThemeToggle',
  component: ThemeToggle,
  argTypes: {
    mode: {
      control: 'select',
      options: ['dropdown', 'buttons', 'toggle'],
      description: 'Display mode for the theme switcher',
    },
    compact: {
      control: 'boolean',
      description: 'Show icons only (no labels)',
    },
    showLabel: {
      control: 'boolean',
      description: 'Show the "Theme" label',
    },
  },
} as Meta<typeof ThemeToggle>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Dropdown: Story = {
  args: {
    mode: 'dropdown',
    showLabel: true,
  },
};

export const Buttons: Story = {
  args: {
    mode: 'buttons',
    showLabel: true,
  },
};

export const Toggle: Story = {
  args: {
    mode: 'toggle',
    showLabel: false,
  },
};

export const Compact: Story = {
  args: {
    mode: 'buttons',
    compact: true,
    showLabel: false,
  },
};

export const NoLabel: Story = {
  args: {
    mode: 'dropdown',
    showLabel: false,
  },
};

export const AllModes: Story = {
  render: () => ({
    components: { ThemeToggle },
    template: `
      <div class="flex flex-col gap-4">
        <div>
          <h4 class="text-sm font-semibold mb-2">Dropdown</h4>
          <ThemeToggle mode="dropdown" />
        </div>
        <div>
          <h4 class="text-sm font-semibold mb-2">Buttons</h4>
          <ThemeToggle mode="buttons" />
        </div>
        <div>
          <h4 class="text-sm font-semibold mb-2">Toggle</h4>
          <ThemeToggle mode="toggle" />
        </div>
        <div>
          <h4 class="text-sm font-semibold mb-2">Compact buttons</h4>
          <ThemeToggle mode="buttons" :compact="true" :show-label="false" />
        </div>
      </div>
    `,
  }),
};
