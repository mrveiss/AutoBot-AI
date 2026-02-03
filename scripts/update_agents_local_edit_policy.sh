#!/bin/bash

# AutoBot Agent Local-Only Edit Policy Enforcement Script
# Adds mandatory local-only editing rules to all agent configurations

# Local-only editing enforcement text to add to all agents
LOCAL_EDIT_POLICY='

## 🚨 MANDATORY LOCAL-ONLY EDITING ENFORCEMENT

**CRITICAL: ALL code edits MUST be done locally, NEVER on remote servers**

### ⛔ ABSOLUTE PROHIBITIONS:
- **NEVER SSH to remote VMs to edit files**: `ssh user@172.16.168.21 "vim file"`
- **NEVER use remote text editors**: vim, nano, emacs on VMs
- **NEVER modify configuration directly on servers**
- **NEVER execute code changes directly on remote hosts**

### ✅ MANDATORY WORKFLOW: LOCAL EDIT → SYNC → DEPLOY

1. **Edit Locally**: ALL changes in `/home/kali/Desktop/AutoBot/`
2. **Test Locally**: Verify changes work in local environment
3. **Sync to Remote**: Use approved sync scripts or Ansible
4. **Verify Remote**: Check deployment success (READ-ONLY)

### 🔄 Required Sync Methods:

#### Frontend Changes:
```bash
# Edit locally first
vim /home/kali/Desktop/AutoBot/autobot-vue/src/components/MyComponent.vue

# Then sync to VM1 (172.16.168.21)
./scripts/utilities/sync-frontend.sh components/MyComponent.vue
# OR
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/ /home/autobot/autobot-vue/src/components/
```

#### Backend Changes:
```bash
# Edit locally first
vim /home/kali/Desktop/AutoBot/backend/api/chat.py

# Then sync to VM4 (172.16.168.24)
./scripts/utilities/sync-to-vm.sh ai-stack backend/api/ /home/autobot/backend/api/
# OR
ansible-playbook -i ansible/inventory ansible/playbooks/deploy-backend.yml
```

#### Configuration Changes:
```bash
# Edit locally first
vim /home/kali/Desktop/AutoBot/config/redis.conf

# Then deploy via Ansible
ansible-playbook -i ansible/inventory ansible/playbooks/update-redis-config.yml
```

#### Docker/Infrastructure:
```bash
# Edit locally first
vim /home/kali/Desktop/AutoBot/docker-compose.yml

# Then deploy via Ansible
ansible-playbook -i ansible/inventory ansible/playbooks/deploy-infrastructure.yml
```

### 📍 VM Target Mapping:
- **VM1 (172.16.168.21)**: Frontend - Web interface
- **VM2 (172.16.168.22)**: NPU Worker - Hardware AI acceleration  
- **VM3 (172.16.168.23)**: Redis - Data layer
- **VM4 (172.16.168.24)**: AI Stack - AI processing
- **VM5 (172.16.168.25)**: Browser - Web automation

### 🔐 SSH Key Requirements:
- **Key Location**: `~/.ssh/autobot_key`
- **Authentication**: ONLY SSH key-based (NO passwords)
- **Sync Commands**: Always use `-i ~/.ssh/autobot_key`

### ❌ VIOLATION EXAMPLES:
```bash
# WRONG - Direct editing on VM
ssh autobot@172.16.168.21 "vim /home/autobot/app.py"

# WRONG - Remote configuration change  
ssh autobot@172.16.168.23 "sudo vim /etc/redis/redis.conf"

# WRONG - Direct Docker changes on VM
ssh autobot@172.16.168.24 "docker-compose up -d"
```

### ✅ CORRECT EXAMPLES:
```bash
# RIGHT - Local edit + sync
vim /home/kali/Desktop/AutoBot/app.py
./scripts/utilities/sync-to-vm.sh ai-stack app.py /home/autobot/app.py

# RIGHT - Local config + Ansible
vim /home/kali/Desktop/AutoBot/config/redis.conf  
ansible-playbook ansible/playbooks/update-redis.yml

# RIGHT - Local Docker + deployment
vim /home/kali/Desktop/AutoBot/docker-compose.yml
ansible-playbook ansible/playbooks/deploy-containers.yml
```

**This policy is NON-NEGOTIABLE. Violations will be corrected immediately.**'

# List of all agent files
AGENT_FILES=(
    "frontend-engineer-agent.md"
    "security-auditor.md"
    "ai-ml-engineer-md.md"
    "code-reviewer.md"
    "devops-engineer-md.md"
    "testing-engineer-md.md"
    "performance-engineer-md.md"
    "database-engineer-md.md"
    "documentation-engineer-md.md"
    "multimodal-engineer-md.md"
    "project-manager-md.md"
    "project-task-planner.md"
    "prd-writer.md"
    "content-writer.md"
    "senior-backend-engineer.md"
    "systems-architect.md"
    "code-refactorer.md"
    "code-skeptic.md"
    "frontend-designer.md"
)

# Function to add local-only edit policy to agent
add_local_edit_policy() {
    local agent_file=$1
    echo "Adding local-only edit policy to: $agent_file"
    
    if [[ -f "$agent_file" ]]; then
        # Check if policy already exists
        if grep -q "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT" "$agent_file"; then
            echo "  - Local-only editing policy already present in $agent_file"
        else
            # Add policy at the end of the file
            echo "$LOCAL_EDIT_POLICY" >> "$agent_file"
            echo "  ✅ Added local-only editing enforcement to $agent_file"
        fi
    else
        echo "  ⚠️  Warning: $agent_file not found"
    fi
}

echo "🚨 Adding Mandatory Local-Only Edit Policy to All AutoBot Agents"
echo "=============================================================="

# Add policy to all agents
for agent in "${AGENT_FILES[@]}"; do
    add_local_edit_policy "$agent"
done

echo ""
echo "✅ Local-Only Edit Policy Update Complete!"
echo ""
echo "📋 Summary:"
echo "- Policy added to all agent configuration files"
echo "- Agents now MUST edit locally and sync to remote VMs"  
echo "- Direct SSH editing is explicitly prohibited"
echo "- Sync scripts and Ansible playbooks are mandatory for remote deployment"
echo ""
echo "🔒 Enforcement Level: MANDATORY"
echo "⚠️  Violations will be detected and corrected immediately"