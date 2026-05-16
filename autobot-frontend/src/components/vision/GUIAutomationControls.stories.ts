import type { Meta, StoryObj } from '@storybook/vue3';
import GUIAutomationControls from './GUIAutomationControls.vue';

const meta = {
  title: 'Components/Vision/GUIAutomationControls',
  component: GUIAutomationControls,
  tags: ['autodocs'],
  argTypes: {
    opportunities: {
      control: 'object',
      description: 'List of automation opportunities to display',
    },
    loading: {
      control: 'boolean',
      description: 'Whether the component is loading/analyzing',
    },
  },
} as Meta<typeof GUIAutomationControls>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

const sampleOpportunities = [
  {
    element_id: 'btn-submit-001',
    element_type: 'button',
    action: 'Click Submit',
    description: 'Submit form button is available and ready to be clicked.',
    confidence: 0.92,
  },
  {
    element_id: 'input-search-002',
    element_type: 'input',
    action: 'Type in Search',
    description: 'Search input field is focused and ready for text entry.',
    confidence: 0.78,
  },
  {
    element_id: 'dropdown-menu-003',
    element_type: 'dropdown',
    action: 'Open Dropdown',
    description: 'Dropdown menu can be expanded to reveal options.',
    confidence: 0.55,
  },
];

export const Default: Story = {
  args: {
    opportunities: sampleOpportunities,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    opportunities: [],
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    opportunities: [],
    loading: false,
  },
};

export const HighConfidenceOnly: Story = {
  args: {
    opportunities: [
      {
        element_id: 'btn-ok-001',
        element_type: 'button',
        action: 'Click OK',
        description: 'OK button detected with very high confidence.',
        confidence: 0.97,
      },
      {
        element_id: 'link-nav-002',
        element_type: 'link',
        action: 'Follow Navigation Link',
        description: 'Navigation link is clearly visible and clickable.',
        confidence: 0.89,
      },
    ],
    loading: false,
  },
};

export const MixedConfidence: Story = {
  args: {
    opportunities: [
      {
        element_id: 'btn-primary-001',
        element_type: 'button',
        action: 'Submit',
        description: 'Primary action button.',
        confidence: 0.95,
      },
      {
        element_id: 'checkbox-terms-002',
        element_type: 'checkbox',
        action: 'Toggle Checkbox',
        description: 'Terms and conditions checkbox.',
        confidence: 0.62,
      },
      {
        element_id: 'icon-close-003',
        element_type: 'icon',
        action: 'Close Modal',
        description: 'Close icon for dismissing the modal dialog.',
        confidence: 0.38,
      },
    ],
    loading: false,
  },
};
