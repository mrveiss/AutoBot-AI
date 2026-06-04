import type { Meta, StoryObj } from '@storybook/vue3';
import PreferencesPanel from './PreferencesPanel.vue';

const meta = {
  title: 'Components/UI/PreferencesPanel',
  component: PreferencesPanel,
  argTypes: {},
} as Meta<typeof PreferencesPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { PreferencesPanel },
    template: '<PreferencesPanel />',
  }),
};

export const InSidebar: Story = {
  render: () => ({
    components: { PreferencesPanel },
    template: `
      <div class="max-w-md">
        <PreferencesPanel />
      </div>
    `,
  }),
};

export const InModal: Story = {
  render: () => ({
    components: { PreferencesPanel },
    template: `
      <div class="max-w-2xl border rounded-lg shadow-lg p-4 bg-white dark:bg-gray-900">
        <PreferencesPanel />
      </div>
    `,
  }),
};
