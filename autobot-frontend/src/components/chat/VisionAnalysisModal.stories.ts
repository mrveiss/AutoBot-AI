import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import VisionAnalysisModal from './VisionAnalysisModal.vue';

const meta = {
  title: 'Components/Chat/VisionAnalysisModal',
  component: VisionAnalysisModal,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof VisionAnalysisModal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// VisionAnalysisModal has no props — all state is internal.
// Stories demonstrate the visual shell only; actual file upload and API
// calls are not wired in Storybook.

export const Default: Story = {
  args: {},
};
