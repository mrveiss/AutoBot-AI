import type { Meta, StoryObj } from '@storybook/vue3';
import PermissionDenied from './PermissionDenied.vue';

const meta = {
  title: 'Components/Common/PermissionDenied',
  component: PermissionDenied,
  tags: ['autodocs'],
} satisfies Meta<typeof PermissionDenied>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => ({
    components: { PermissionDenied },
    template: '<PermissionDenied />',
  }),
};

export const WithContext: Story = {
  render: () => ({
    components: { PermissionDenied },
    template: `
      <div class="space-y-4">
        <h2 class="text-2xl font-bold">Permission Denied Example</h2>
        <PermissionDenied />
      </div>
    `,
  }),
};
