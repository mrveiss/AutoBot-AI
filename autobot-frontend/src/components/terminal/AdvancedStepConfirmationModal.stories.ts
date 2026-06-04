import type { Meta } from '@storybook/vue3';
import type { StoryObj } from '@storybook/vue3';
import AdvancedStepConfirmationModal from './AdvancedStepConfirmationModal.vue';

const sampleStep = {
  command: 'sudo apt-get update && sudo apt-get upgrade -y',
  description: 'Update system packages',
  explanation: 'This command updates the package list and upgrades all installed packages to their latest versions.',
  stepNumber: 2,
  totalSteps: 5,
  requiresConfirmation: true,
};

const sampleSteps = [
  { command: 'git clone https://github.com/example/repo.git', description: 'Clone repository', stepNumber: 1, totalSteps: 5 },
  sampleStep,
  { command: 'cd repo && npm install', description: 'Install dependencies', stepNumber: 3, totalSteps: 5 },
  { command: 'npm run build', description: 'Build project', stepNumber: 4, totalSteps: 5 },
  { command: 'npm run test', description: 'Run tests', stepNumber: 5, totalSteps: 5 },
];

const meta = {
  title: 'Components/Terminal/AdvancedStepConfirmationModal',
  component: AdvancedStepConfirmationModal,
  tags: ['autodocs'],
  argTypes: {
    visible: {
      control: 'boolean',
      description: 'Whether the modal is visible',
    },
    currentStep: {
      control: 'object',
      description: 'The current step awaiting confirmation',
    },
    currentStepIndex: {
      control: { type: 'number', min: 0 },
      description: 'Zero-based index of the current step',
    },
    workflowSteps: {
      control: 'object',
      description: 'Full list of workflow steps',
    },
    sessionId: {
      control: 'text',
      description: 'Terminal session ID',
    },
  },
} as Meta<typeof AdvancedStepConfirmationModal>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  args: {
    visible: true,
    currentStep: sampleStep,
    currentStepIndex: 1,
    workflowSteps: sampleSteps,
    sessionId: 'session-abc-123',
  },
};

export const FirstStep: Story = {
  args: {
    visible: true,
    currentStep: { ...sampleSteps[0], stepNumber: 1 },
    currentStepIndex: 0,
    workflowSteps: sampleSteps,
    sessionId: 'session-abc-123',
  },
};

export const LastStep: Story = {
  args: {
    visible: true,
    currentStep: { ...sampleSteps[4], stepNumber: 5 },
    currentStepIndex: 4,
    workflowSteps: sampleSteps,
    sessionId: 'session-abc-123',
  },
};

export const SingleStep: Story = {
  args: {
    visible: true,
    currentStep: {
      command: 'rm -rf /tmp/build',
      description: 'Clean build artifacts',
      explanation: 'Removes all temporary build files from the /tmp/build directory.',
      stepNumber: 1,
      totalSteps: 1,
      requiresConfirmation: true,
    },
    currentStepIndex: 0,
    workflowSteps: [{ command: 'rm -rf /tmp/build', description: 'Clean build artifacts', stepNumber: 1, totalSteps: 1 }],
    sessionId: 'session-xyz-456',
  },
};

export const Hidden: Story = {
  args: {
    visible: false,
    currentStep: sampleStep,
    currentStepIndex: 1,
    workflowSteps: sampleSteps,
    sessionId: 'session-abc-123',
  },
};
