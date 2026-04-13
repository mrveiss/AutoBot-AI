import type { Meta, StoryObj } from '@storybook/vue3';
import EmptyState from './EmptyState.vue';

const meta = {
  title: 'Components/UI/EmptyState',
  component: EmptyState,
  tags: ['autodocs'],
  argTypes: {
    icon: {
      control: 'text',
      description: 'Icon class name',
    },
    title: {
      control: 'text',
      description: 'Empty state title',
    },
    description: {
      control: 'text',
      description: 'Empty state description',
    },
  },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    title: 'No data available',
    description: 'There is no data to display at this time',
  },
};

export const NoResults: Story = {
  args: {
    icon: 'fas fa-search',
    title: 'No search results',
    description: 'Try adjusting your search criteria',
  },
};

export const NoItems: Story = {
  args: {
    icon: 'fas fa-inbox',
    title: 'Inbox is empty',
    description: 'You have no items in your inbox',
  },
};

export const WithIcon: Story = {
  args: {
    icon: 'fas fa-folder-open',
    title: 'No files',
    description: 'This directory is empty',
  },
};

export const CreateNew: Story = {
  args: {
    icon: 'fas fa-plus-circle',
    title: 'No projects yet',
    description: 'Create your first project to get started',
  },
};

export const WithSlot: Story = {
  render: () => ({
    components: { EmptyState },
    template: `
      <EmptyState
        icon="fas fa-chart-bar"
        title="No analytics data"
        description="Analytics will appear here once data is available"
      >
        <button class="mt-4 px-4 py-2 bg-blue-500 text-white rounded">
          Refresh Data
        </button>
      </EmptyState>
    `,
  }),
};
