// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { Meta, StoryObj } from '@storybook/vue3';
import MachineProfilePanel from './MachineProfilePanel.vue';

const meta = {
  title: 'Components/ManPage/MachineProfilePanel',
  component: MachineProfilePanel,
  tags: ['autodocs'],
  argTypes: {
    profile: {
      control: 'object',
      description: 'Machine profile data object',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading spinner',
    },
  },
} as Meta<typeof MachineProfilePanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const LinuxProfile: Story = {
  args: {
    profile: {
      machine_id: 'autobot-node-01',
      os_type: 'linux',
      distro: 'Ubuntu 22.04 LTS',
      package_manager: 'apt',
      available_tools: ['curl', 'wget', 'git', 'docker', 'python3', 'pip3'],
      architecture: 'x86_64',
    },
    loading: false,
  },
};

export const WindowsProfile: Story = {
  args: {
    profile: {
      machine_id: 'autobot-win-01',
      os_type: 'windows',
      distro: 'N/A',
      package_manager: 'winget',
      available_tools: ['powershell', 'git'],
      architecture: 'x86_64',
    },
    loading: false,
  },
};

export const MacOSProfile: Story = {
  args: {
    profile: {
      machine_id: 'autobot-mac-01',
      os_type: 'macos',
      distro: 'Ventura 13.5',
      package_manager: 'brew',
      available_tools: ['curl', 'git', 'python3'],
      architecture: 'arm64',
    },
    loading: false,
  },
};

export const NoData: Story = {
  args: {
    profile: null,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    profile: null,
    loading: true,
  },
};
