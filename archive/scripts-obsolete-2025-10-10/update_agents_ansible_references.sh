#!/bin/bash

# Add Ansible Playbook References to All Agent Configurations
# Ensures all agents understand proper infrastructure management

set -e

AGENTS_DIR="/home/kali/Desktop/AutoBot/.claude/agents"
echo "🔧 Adding Ansible playbook references to all agent configurations..."

# Ansible reference block to add to all agents
ANSIBLE_BLOCK='### 🔧 Ansible Infrastructure Management

**MANDATORY: Use Ansible for all infrastructure operations**

#### Available Playbooks:

**Full Production Deployment:**
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-full.yml
```

**Development Environment:**
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-development-services.yml
```

**Health Check & Validation:**
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/health-check.yml
```

**Service-Specific Deployment:**
```bash
# Frontend (VM1: 172.16.168.21)
ansible frontend -i ansible/inventory/production.yml -m systemd -a "name=nginx state=restarted" -b

# Backend (VM4: 172.16.168.24) 
ansible backend -i ansible/inventory/production.yml -m systemd -a "name=autobot-backend state=restarted" -b

# Database (VM3: 172.16.168.23)
ansible database -i ansible/inventory/production.yml -m systemd -a "name=redis-stack-server state=restarted" -b

# AI/ML Services (VM2: 172.16.168.22, VM4: 172.16.168.24)
ansible aiml -i ansible/inventory/production.yml -m systemd -a "name=autobot-ai-stack state=restarted" -b

# Browser Automation (VM5: 172.16.168.25)
ansible browser -i ansible/inventory/production.yml -m systemd -a "name=autobot-playwright state=restarted" -b
```

#### VM Infrastructure:
- **VM1 (172.16.168.21)**: Frontend - nginx, Vue.js development server
- **VM2 (172.16.168.22)**: NPU Worker - Intel OpenVINO, hardware acceleration
- **VM3 (172.16.168.23)**: Database - Redis Stack, data persistence
- **VM4 (172.16.168.24)**: AI Stack - Backend APIs, AI processing
- **VM5 (172.16.168.25)**: Browser - Playwright, VNC, desktop environment

#### Health Monitoring:
```bash
# Quick system status
ansible all -i ansible/inventory/production.yml -m shell -a "uptime && systemctl is-active autobot-*"

# Service logs
ansible <group> -i ansible/inventory/production.yml -m shell -a "journalctl -u autobot-* --since '\''1 hour ago'\'' --no-pager"

# Network connectivity
ansible all -i ansible/inventory/production.yml -m shell -a "curl -s http://172.16.168.20:8001/api/health"
```

#### Emergency Recovery:
```bash
# Stop all services
ansible all -i ansible/inventory/production.yml -m systemd -a "name=autobot-* state=stopped" -b

# Restart specific group
ansible <group> -i ansible/inventory/production.yml -m systemd -a "name=autobot-* state=restarted" -b
```

**Reference**: Complete Ansible documentation at `docs/ANSIBLE_PLAYBOOK_REFERENCE.md`'

# Counter for processed files
processed=0
total_agents=0

# Count total agents
for file in "$AGENTS_DIR"/*.md; do
    if [[ -f "$file" ]]; then
        ((total_agents++))
    fi
done

echo "Found $total_agents agent configuration files to update"

# Process each agent file
for file in "$AGENTS_DIR"/*.md; do
    if [[ -f "$file" ]]; then
        filename=$(basename "$file")
        echo "Processing: $filename"
        
        # Check if the agent already has Ansible references
        if grep -q "Ansible Infrastructure Management" "$file"; then
            echo "  ✅ Already has Ansible references - skipping"
        else
            # Add Ansible block before the existing local-only editing policy
            if grep -q "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT" "$file"; then
                # Insert before the local-only editing section
                sed -i '/## 🚨 MANDATORY LOCAL-ONLY EDITING ENFORCEMENT/i\\n'"$(echo "$ANSIBLE_BLOCK" | sed 's/$/\\n/g' | tr -d '\n')"'\n' "$file"
                echo "  ✅ Added Ansible references before local-only editing section"
                ((processed++))
            else
                # Append at the end if no local-only editing section exists
                echo -e "\n$ANSIBLE_BLOCK" >> "$file"
                echo "  ✅ Added Ansible references at end of file"
                ((processed++))
            fi
        fi
    fi
done

echo ""
echo "🎉 Ansible reference update complete!"
echo "📊 Processed: $processed/$total_agents agent configurations"
echo "📄 Created: docs/ANSIBLE_PLAYBOOK_REFERENCE.md"
echo ""
echo "✅ All agents now have comprehensive Ansible playbook references"
echo "🔧 Agents can now use proper infrastructure management commands"
echo "🏗️  Reference guide available for complete automation capabilities"