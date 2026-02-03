#!/bin/bash
# AutoBot Ansible Deployment Scripts

cd "$(dirname "$0")/../../ansible"

case "$1" in
    "deploy-all")
        echo "🚀 Deploying entire AutoBot infrastructure..."
        ansible-playbook site.yml
        ;;
        
    "deploy-frontend")
        echo "🎨 Deploying frontend services..."
        ansible-playbook site.yml --tags frontend
        ;;
        
    "deploy-backend")  
        echo "⚙️ Deploying backend services..."
        ansible-playbook site.yml --tags backend
        ;;
        
    "deploy-ai")
        echo "🤖 Deploying AI services..."
        ansible-playbook site.yml --tags ai
        ;;
        
    "start-all")
        echo "▶️ Starting all AutoBot services..."
        ansible-playbook service_management.yml -e "service_action=start"
        ;;
        
    "stop-all")
        echo "⏹️ Stopping all AutoBot services..."
        ansible-playbook service_management.yml -e "service_action=stop"
        ;;
        
    "restart-all")
        echo "🔄 Restarting all AutoBot services..."
        ansible-playbook service_management.yml -e "service_action=restart"
        ;;
        
    "status")
        echo "📊 Checking AutoBot service status..."
        ansible-playbook service_management.yml -e "service_action=status"
        ;;
        
    "health")
        echo "🏥 Running health checks..."
        ansible-playbook service_management.yml --tags health
        ;;
        
    "update")
        echo "📦 Updating all systems..."
        ansible all -m apt -a "update_cache=yes upgrade=dist" --become
        ;;
        
    *)
        echo "AutoBot Ansible Management"
        echo "Usage: $0 {deploy-all|deploy-frontend|deploy-backend|deploy-ai|start-all|stop-all|restart-all|status|health|update}"
        echo ""
        echo "Examples:"
        echo "  $0 deploy-all     # Deploy entire infrastructure"
        echo "  $0 restart-all    # Restart all services"  
        echo "  $0 status         # Check service status"
        echo "  $0 health         # Run health checks"
        ;;
esac