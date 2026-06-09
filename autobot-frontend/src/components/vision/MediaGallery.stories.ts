// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import MediaGallery from './MediaGallery.vue';

const meta = {
  title: 'Components/Vision/MediaGallery',
  component: MediaGallery,
  tags: ['autodocs'],
  argTypes: {
    items: {
      control: 'object',
      description: 'Array of gallery items (images, videos, screen captures)',
    },
  },
} as Meta<typeof MediaGallery>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const now = Date.now();

const imageItems = [
  {
    id: 'img-001',
    type: 'image',
    filename: 'screenshot_dashboard.png',
    thumbnail: '',
    timestamp: now - 60000,
    analysisResult: {
      confidence: 0.91,
      processing_time: 1.23,
      device_used: 'npu',
    },
  },
  {
    id: 'img-002',
    type: 'image',
    filename: 'capture_analysis_report.jpg',
    thumbnail: '',
    timestamp: now - 120000,
    analysisResult: {
      confidence: 0.85,
      processing_time: 0.98,
      device_used: 'cpu',
    },
  },
];

const videoItems = [
  {
    id: 'vid-001',
    type: 'video',
    filename: 'screen_recording_session.mp4',
    thumbnail: '',
    timestamp: now - 300000,
    analysisResult: {
      frames_processed: 12,
      confidence: 0.88,
      processing_time: 14.5,
      device_used: 'npu',
    },
  },
];

const screenItems = [
  {
    id: 'scr-001',
    type: 'screen',
    filename: 'auto_capture_20260516_143022.png',
    thumbnail: '',
    timestamp: now - 30000,
    analysisResult: {
      confidence: 0.93,
      processing_time: 0.75,
      device_used: 'npu',
    },
  },
];

export const Default: Story = {
  args: {
    items: [...imageItems, ...videoItems, ...screenItems],
  },
};

export const Empty: Story = {
  args: {
    items: [],
  },
};

export const ImagesOnly: Story = {
  args: {
    items: imageItems,
  },
};

export const VideosOnly: Story = {
  args: {
    items: videoItems,
  },
};

export const MixedMediaTypes: Story = {
  args: {
    items: [
      ...imageItems,
      ...videoItems,
      ...screenItems,
      {
        id: 'scr-002',
        type: 'screen',
        filename: 'auto_capture_20260516_150000.png',
        thumbnail: '',
        timestamp: now - 600000,
        analysisResult: null,
      },
    ],
  },
};
