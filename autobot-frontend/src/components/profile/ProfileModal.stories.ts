import type { Meta, StoryObj } from '@storybook/vue3';
import ProfileModal from './ProfileModal.vue';

const meta = {
  title: 'UI/Singletons/ProfileModal',
  component: ProfileModal,
  argTypes: {
    isOpen: {
      control: 'boolean',
      description: 'Controls the visibility of the profile modal'
    }
  },
} as Meta<typeof ProfileModal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    isOpen: true
  },
  render: (args: any) => ({
    components: { ProfileModal },
    setup() {
      return { args };
    },
    template: `
      <div>
        <p class="mb-4 text-sm text-gray-600">
          ProfileModal is a singleton component that displays user profile settings and preferences.
          It is controlled via the <code>isOpen</code> prop and emits a <code>close</code> event when dismissed.
        </p>
        <ProfileModal :is-open="args.isOpen" @close="args.isOpen = false" />
      </div>
    `,
  }),
};

export const Closed: Story = {
  args: {
    isOpen: false
  },
  render: (args: any) => ({
    components: { ProfileModal },
    setup() {
      return { args };
    },
    template: `
      <div>
        <p class="mb-4 text-sm text-gray-600">
          When <code>isOpen</code> is false, the modal is hidden and does not render any overlay.
        </p>
        <ProfileModal :is-open="args.isOpen" @close="args.isOpen = false" />
        <p class="mt-4 text-sm text-gray-500">Modal is hidden in this state.</p>
      </div>
    `,
  }),
};

export const WithBackdrop: Story = {
  args: {
    isOpen: true
  },
  render: (args: any) => ({
    components: { ProfileModal },
    setup() {
      return { args };
    },
    template: `
      <div style="position: relative; width: 100%; height: 600px; background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; overflow: hidden;">
        <p style="padding: 16px; color: #666; font-size: 14px;">
          ProfileModal renders with a semi-transparent backdrop behind the modal content.
          Click the backdrop or close button to dismiss.
        </p>
        <ProfileModal :is-open="args.isOpen" @close="args.isOpen = false" />
      </div>
    `,
  }),
};
