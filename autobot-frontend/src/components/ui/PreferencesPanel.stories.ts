import type { Meta, StoryObj } from '@storybook/vue3';
import PreferencesPanel from './PreferencesPanel.vue';

const meta = {
  title: 'Components/UI/PreferencesPanel',
  component: PreferencesPanel,
  tags: ['autodocs'],
  argTypes: {},
} satisfies Meta<typeof PreferencesPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

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
