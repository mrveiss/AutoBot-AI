import type { Meta, StoryObj } from '@storybook/vue3';
import VideoProcessor from './VideoProcessor.vue';

const meta = {
  title: 'Components/Vision/VideoProcessor',
  component: VideoProcessor,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof VideoProcessor>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { VideoProcessor },
    template: `<VideoProcessor />`,
  }),
};

export const DropZoneIdle: Story = {
  render: () => ({
    components: { VideoProcessor },
    template: `
      <div style="max-width: 800px;">
        <VideoProcessor />
      </div>
    `,
  }),
};

export const WithFrameResults: Story = {
  render: () => ({
    components: { VideoProcessor },
    template: `
      <div style="max-width: 800px; padding: 16px;">
        <VideoProcessor @analysis-complete="onComplete" @add-to-gallery="onGallery" />
      </div>
    `,
    methods: {
      onComplete(result: unknown) {
        // eslint-disable-next-line no-console
        console.log('Analysis complete:', result);
      },
      onGallery(item: unknown) {
        // eslint-disable-next-line no-console
        console.log('Add to gallery:', item);
      },
    },
  }),
};

export const NarrowLayout: Story = {
  render: () => ({
    components: { VideoProcessor },
    template: `
      <div style="max-width: 480px;">
        <VideoProcessor />
      </div>
    `,
  }),
};

export const WideLayout: Story = {
  render: () => ({
    components: { VideoProcessor },
    template: `
      <div style="max-width: 1200px;">
        <VideoProcessor />
      </div>
    `,
  }),
};
