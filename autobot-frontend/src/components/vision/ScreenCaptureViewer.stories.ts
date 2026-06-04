import type { Meta, StoryObj } from '@storybook/vue3';
import ScreenCaptureViewer from './ScreenCaptureViewer.vue';

const meta = {
  title: 'Components/Vision/ScreenCaptureViewer',
  component: ScreenCaptureViewer,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof ScreenCaptureViewer>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const sampleAnalysisResult = {
  confidence_score: 0.87,
  timestamp: Math.floor(Date.now() / 1000),
  ui_elements: [
    {
      element_id: 'el-btn-001',
      element_type: 'button',
      confidence: 0.94,
      text_content: 'Submit',
      bbox: { x: 100, y: 200, width: 120, height: 40 },
      center_point: [160, 220],
      possible_interactions: ['click'],
    },
    {
      element_id: 'el-input-002',
      element_type: 'input',
      confidence: 0.89,
      text_content: 'Search...',
      bbox: { x: 50, y: 100, width: 300, height: 36 },
      center_point: [200, 118],
      possible_interactions: ['click', 'type'],
    },
    {
      element_id: 'el-link-003',
      element_type: 'link',
      confidence: 0.72,
      text_content: 'Learn more',
      bbox: { x: 400, y: 350, width: 90, height: 20 },
      center_point: [445, 360],
      possible_interactions: ['click'],
    },
    {
      element_id: 'el-menu-004',
      element_type: 'menu',
      confidence: 0.45,
      text_content: null,
      bbox: { x: 0, y: 0, width: 200, height: 600 },
      center_point: [100, 300],
      possible_interactions: ['click', 'hover'],
    },
  ],
  text_regions: [
    { text: 'Welcome to AutoBot Dashboard' },
    { text: 'System Status: Online' },
    { text: 'Last updated: just now' },
  ],
  layout_structure: {
    type: 'application_window',
    regions: ['header', 'sidebar', 'main_content', 'footer'],
  },
};

export const Default: Story = {
  args: {},
  render: () => ({
    components: { ScreenCaptureViewer },
    template: `<div style="height: 600px;"><ScreenCaptureViewer /></div>`,
  }),
};

export const WithAnalysisResult: Story = {
  render: () => ({
    components: { ScreenCaptureViewer },
    setup() {
      return { sampleAnalysisResult };
    },
    template: `
      <div style="height: 600px;">
        <ScreenCaptureViewer />
      </div>
    `,
  }),
};

export const EmptyState: Story = {
  render: () => ({
    components: { ScreenCaptureViewer },
    template: `
      <div style="height: 500px;">
        <ScreenCaptureViewer />
      </div>
    `,
  }),
};

export const CompactView: Story = {
  render: () => ({
    components: { ScreenCaptureViewer },
    template: `
      <div style="height: 400px; width: 600px;">
        <ScreenCaptureViewer />
      </div>
    `,
  }),
};
