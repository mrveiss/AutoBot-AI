#!/bin/bash
# Setup passwordless sudo for AutoBot operations

echo "Setting up passwordless sudo for AutoBot operations..."

# Create sudoers file for AutoBot operations
sudo tee /etc/sudoers.d/autobot << 'EOF'
# Allow kali user to run specific commands without password for AutoBot
kali ALL=(ALL) NOPASSWD: /usr/bin/lsof
kali ALL=(ALL) NOPASSWD: /usr/bin/kill
kali ALL=(ALL) NOPASSWD: /usr/bin/pkill
kali ALL=(ALL) NOPASSWD: /usr/sbin/usermod -aG docker kali
EOF

# Validate sudoers file
sudo visudo -c -f /etc/sudoers.d/autobot

if [ $? -eq 0 ]; then
    echo "✅ Passwordless sudo configured successfully for AutoBot operations"
    echo "The following commands now work without password:"
    echo "  - sudo lsof (port checking)"
    echo "  - sudo kill (process termination)"  
    echo "  - sudo pkill (process cleanup)"
    echo "  - sudo usermod (docker group)"
else
    echo "❌ Failed to configure sudoers file"
    sudo rm -f /etc/sudoers.d/autobot
    exit 1
fi