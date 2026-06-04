import type { Meta, StoryObj } from '@storybook/vue3';
import StableLoadingState from './StableLoadingState.vue';

const meta = {
  title: 'Components/UI/StableLoadingState',
  component: StableLoadingState,
  argTypes: {
    isLoading: {
      control: 'boolean',
      description: 'Whether to render the loading placeholder',
    },
    hasContent: {
      control: 'boolean',
      description: 'Whether the slot has rendered content',
    },
    variant: {
      control: 'select',
      options: ['chat', 'sidebar', 'modal', 'inline'],
      description: 'Layout variant for the placeholder',
    },
    minHeight: {
      control: 'text',
      description: 'CSS min-height to reserve while loading',
    },
    preserveSpace: {
      control: 'boolean',
      description: 'Reserve min-height to prevent layout shift',
    },
  },
} as Meta<typeof StableLoadingState>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Loading: Story = {
  args: {
    isLoading: true,
    hasContent: false,
    variant: 'chat',
  },
};

export const LoadedContent: Story = {
  render: () => ({
    components: { StableLoadingState },
    template: `
      <StableLoadingState :is-loading="false" :has-content="true" variant="chat">
        <div class="p-4 bg-white rounded shadow">
          <h3 class="font-semibold mb-2">Loaded content</h3>
          <p class="text-sm text-gray-600">This content is rendered once loading is complete.</p>
        </div>
      </StableLoadingState>
    `,
  }),
};

export const UpdatingExistingContent: Story = {
  render: () => ({
    components: { StableLoadingState },
    template: `
      <StableLoadingState :is-loading="true" :has-content="true" variant="chat">
        <div class="p-4 bg-white rounded shadow">
          <h3 class="font-semibold mb-2">Existing content</h3>
          <p class="text-sm text-gray-600">A small pulse appears while we refresh in the background.</p>
        </div>
      </StableLoadingState>
    `,
  }),
};

export const SidebarVariant: Story = {
  args: {
    isLoading: true,
    hasContent: false,
    variant: 'sidebar',
  },
};

export const ModalVariant: Story = {
  args: {
    isLoading: true,
    hasContent: false,
    variant: 'modal',
  },
};

export const InlineVariant: Story = {
  args: {
    isLoading: true,
    hasContent: false,
    variant: 'inline',
  },
};
