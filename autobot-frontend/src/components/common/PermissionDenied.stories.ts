import type { Meta, StoryObj } from '@storybook/vue3';
import PermissionDenied from './PermissionDenied.vue';

const meta = {
  title: 'Components/Common/PermissionDenied',
  component: PermissionDenied,
} as Meta<typeof PermissionDenied>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

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
