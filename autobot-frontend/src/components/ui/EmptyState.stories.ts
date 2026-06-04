import type { Meta, StoryObj } from '@storybook/vue3';
import EmptyState from './EmptyState.vue';

// #6874: stories used `description` but the actual prop on EmptyState.vue is `message`.
// DataTable.vue + every other production caller already uses `:message`, so the bug
// was in this stories file (mismatched prop name made stories render blank body text
// in Storybook). Realigning to `message`.
const meta = {
  title: 'Components/UI/EmptyState',
  component: EmptyState,
  argTypes: {
    icon: {
      control: 'text',
      description: 'Icon class name',
    },
    title: {
      control: 'text',
      description: 'Empty state title',
    },
    message: {
      control: 'text',
      description: 'Empty state message text (rendered below the title)',
    },
    compact: {
      control: 'boolean',
      description: 'Compact mode (smaller spacing)',
    },
  },
} as Meta<typeof EmptyState>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    title: 'No data available',
    message: 'There is no data to display at this time',
  },
};

export const NoResults: Story = {
  args: {
    icon: 'fas fa-search',
    title: 'No search results',
    message: 'Try adjusting your search criteria',
  },
};

export const NoItems: Story = {
  args: {
    icon: 'fas fa-inbox',
    title: 'Inbox is empty',
    message: 'You have no items in your inbox',
  },
};

export const WithIcon: Story = {
  args: {
    icon: 'fas fa-folder-open',
    title: 'No files',
    message: 'This directory is empty',
  },
};

export const CreateNew: Story = {
  args: {
    icon: 'fas fa-plus-circle',
    title: 'No projects yet',
    message: 'Create your first project to get started',
  },
};

export const WithSlot: Story = {
  render: () => ({
    components: { EmptyState },
    template: `
      <EmptyState
        icon="fas fa-chart-bar"
        title="No analytics data"
        message="Analytics will appear here once data is available"
      >
        <button class="mt-4 px-4 py-2 bg-blue-500 text-white rounded">
          Refresh Data
        </button>
      </EmptyState>
    `,
  }),
};
