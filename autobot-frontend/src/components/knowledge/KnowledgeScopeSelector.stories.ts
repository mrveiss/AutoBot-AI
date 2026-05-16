import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import KnowledgeScopeSelector from './KnowledgeScopeSelector.vue'

const meta = {
  title: 'Components/Knowledge/KnowledgeScopeSelector',
  component: KnowledgeScopeSelector,
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'select',
      options: ['private', 'shared', 'group', 'organization', 'system'],
    },
    disabled: { control: 'boolean' },
    showHelp: { control: 'boolean' },
    showGroupSelector: { control: 'boolean' },
    allowShared: { control: 'boolean' },
    allowGroup: { control: 'boolean' },
    allowOrganization: { control: 'boolean' },
    allowSystem: { control: 'boolean' },
    hasOrganization: { control: 'boolean' },
    isAdmin: { control: 'boolean' },
  },
} as Meta<typeof KnowledgeScopeSelector>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Private: Story = {
  args: {
    modelValue: 'private',
    disabled: false,
    showHelp: true,
    showGroupSelector: true,
    allowShared: true,
    allowGroup: true,
    allowOrganization: false,
    allowSystem: false,
    userGroups: [],
    hasOrganization: false,
    isAdmin: false,
  },
}

export const Shared: Story = {
  args: {
    modelValue: 'shared',
    disabled: false,
    showHelp: true,
    showGroupSelector: true,
    allowShared: true,
    allowGroup: true,
    allowOrganization: false,
    allowSystem: false,
    userGroups: [],
    hasOrganization: false,
    isAdmin: false,
  },
}

export const WithGroups: Story = {
  args: {
    modelValue: 'group',
    disabled: false,
    showHelp: true,
    showGroupSelector: true,
    allowShared: true,
    allowGroup: true,
    allowOrganization: false,
    allowSystem: false,
    userGroups: [
      { id: 'g1', name: 'Engineering' },
      { id: 'g2', name: 'DevOps' },
    ],
    hasOrganization: false,
    isAdmin: false,
  },
}

export const AdminWithAllOptions: Story = {
  args: {
    modelValue: 'system',
    disabled: false,
    showHelp: true,
    showGroupSelector: true,
    allowShared: true,
    allowGroup: true,
    allowOrganization: true,
    allowSystem: true,
    userGroups: [{ id: 'g1', name: 'Engineering' }],
    hasOrganization: true,
    isAdmin: true,
  },
}

export const Disabled: Story = {
  args: {
    modelValue: 'private',
    disabled: true,
    showHelp: false,
    showGroupSelector: false,
    allowShared: true,
    allowGroup: false,
    allowOrganization: false,
    allowSystem: false,
    userGroups: [],
    hasOrganization: false,
    isAdmin: false,
  },
}
