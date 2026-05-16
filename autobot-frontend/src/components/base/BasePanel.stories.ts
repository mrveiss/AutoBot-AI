import type { Meta, StoryObj } from '@storybook/vue3';
import BasePanel from './BasePanel.vue';

const meta = {
  title: 'Components/Base/BasePanel',
  component: BasePanel,
  argTypes: {
    title: {
      control: 'text',
      description: 'Panel title',
    },
    collapsible: {
      control: 'boolean',
      description: 'Allow panel to collapse',
    },
    collapsed: {
      control: 'boolean',
      description: 'Start in collapsed state',
    },
  },
} as Meta<typeof BasePanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    title: 'Panel Title',
  },
  render: (args: any) => ({
    components: { BasePanel },
    setup() {
      return { args };
    },
    template: `
      <BasePanel v-bind="args">
        <p>This is the panel content. You can add any HTML content here.</p>
      </BasePanel>
    `,
  }),
};

export const Collapsible: Story = {
  args: {
    title: 'Collapsible Panel',
    collapsible: true,
  },
  render: (args: any) => ({
    components: { BasePanel },
    setup() {
      return { args };
    },
    template: `
      <BasePanel v-bind="args">
        <p>This panel can be collapsed and expanded by clicking the title.</p>
        <p>Content can be hidden when the panel is collapsed.</p>
      </BasePanel>
    `,
  }),
};

export const StartCollapsed: Story = {
  args: {
    title: 'Collapsed by Default',
    collapsible: true,
    collapsed: true,
  },
  render: (args: any) => ({
    components: { BasePanel },
    setup() {
      return { args };
    },
    template: `
      <BasePanel v-bind="args">
        <p>This panel starts in a collapsed state.</p>
      </BasePanel>
    `,
  }),
};

export const WithComplexContent: Story = {
  args: {
    title: 'Settings Panel',
    collapsible: true,
  },
  render: (args: any) => ({
    components: { BasePanel },
    setup() {
      return { args };
    },
    template: `
      <BasePanel v-bind="args">
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1">Option 1</label>
            <input type="checkbox" checked />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">Option 2</label>
            <input type="checkbox" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">Option 3</label>
            <input type="checkbox" checked />
          </div>
        </div>
      </BasePanel>
    `,
  }),
};
