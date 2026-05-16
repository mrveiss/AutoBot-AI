import type { Meta } from '@storybook/vue3'
import type { StoryObj } from '@storybook/vue3'
import BackupManager from './BackupManager.vue'

const meta = {
  title: 'Components/Knowledge/BackupManager',
  component: BackupManager,
  tags: ['autodocs'],
} as Meta<typeof BackupManager>

export default meta
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>

export const Default: Story = {
  args: {},
}

export const Loading: Story = {
  args: {},
}

export const Empty: Story = {
  args: {},
}

export const WithBackups: Story = {
  args: {},
}
