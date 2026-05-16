import type { Meta, StoryObj } from '@storybook/vue3';
import FileBrowserHeader from './FileBrowserHeader.vue';

const meta = {
  title: 'Components/FileBrowser/FileBrowserHeader',
  component: FileBrowserHeader,
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Optional title override; falls back to i18n key fileBrowser.header.title',
    },
    viewMode: {
      control: 'select',
      options: ['tree', 'list'],
      description: 'Current view mode (tree or list)',
    },
    currentPath: {
      control: 'text',
      description: 'Current filesystem path shown in the path navigation',
    },
    onUpload: { action: 'upload' },
    onNewFolder: { action: 'new-folder' },
    onNavigateToPath: { action: 'navigate-to-path' },
  },
} as Meta<typeof FileBrowserHeader>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    viewMode: 'tree',
    currentPath: '/',
  },
};

export const WithTitle: Story = {
  args: {
    title: 'My Files',
    viewMode: 'tree',
    currentPath: '/',
  },
};

export const ListMode: Story = {
  args: {
    viewMode: 'list',
    currentPath: '/documents',
  },
};

export const NestedPath: Story = {
  args: {
    viewMode: 'tree',
    currentPath: '/home/user/projects/autobot',
  },
};

export const TreeMode: Story = {
  args: {
    title: 'File Browser',
    viewMode: 'tree',
    currentPath: '/var/log',
  },
};
