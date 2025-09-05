#!/bin/bash
# AutoBot VM Discovery Script (Linux/WSL version)
# Discovers AutoBot VMs and updates Ansible inventory

NETWORK_RANGE="192.168.100.0/24"
INVENTORY_PATH="../../ansible/inventory/hosts.yml"
UPDATE_INVENTORY=false
SHOW_ALL=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --network-range)
            NETWORK_RANGE="$2"
            shift 2
            ;;
        --inventory-path)
            INVENTORY_PATH="$2"
            shift 2
            ;;
        --update-inventory)
            UPDATE_INVENTORY=true
            shift
            ;;
        --show-all)
            SHOW_ALL=true
            shift
            ;;
        --help)
            echo "AutoBot VM Discovery Tool (Linux/WSL)"
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --network-range CIDR    Network to scan (default: 192.168.100.0/24)"
            echo "  --inventory-path PATH   Ansible inventory file (default: ../../ansible/inventory/hosts.yml)"
            echo "  --update-inventory      Update Ansible inventory with discovered IPs"
            echo "  --show-all             Show detailed information"
            echo "  --help                 Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Check if required tools are available
check_requirements() {
    local missing_tools=()
    
    if ! command -v nmap &> /dev/null; then
        missing_tools+=("nmap")
    fi
    
    if ! command -v nc &> /dev/null && ! command -v netcat &> /dev/null; then
        missing_tools+=("netcat")
    fi
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        echo -e "${RED}❌ Missing required tools: ${missing_tools[*]}${NC}"
        echo -e "${YELLOW}Install with: sudo apt-get install nmap netcat${NC}"
        exit 1
    fi
}

# Test if a specific port is open on an IP
test_port() {
    local ip=$1
    local port=$2
    local timeout=2
    
    if command -v nc &> /dev/null; then
        nc -z -w$timeout $ip $port 2>/dev/null
    elif command -v netcat &> /dev/null; then
        netcat -z -w$timeout $ip $port 2>/dev/null
    else
        return 1
    fi
}

# Test VM connectivity and identify services
test_vm_services() {
    local ip=$1
    local services=()
    
    # Test common AutoBot service ports
    declare -A service_ports=(
        [22]="SSH"
        [80]="HTTP"
        [443]="HTTPS"
        [5173]="Vue Frontend"
        [8001]="FastAPI Backend"
        [8080]="AI Stack"
        [8081]="NPU Worker"
        [6379]="Redis"
    )
    
    for port in "${!service_ports[@]}"; do
        if test_port $ip $port; then
            services+=("${service_ports[$port]}($port)")
        fi
    done
    
    echo "${services[@]}"
}

# Determine VM type based on services
identify_vm_type() {
    local services="$1"
    
    if [[ $services == *"Vue Frontend"* ]]; then
        echo "Frontend"
    elif [[ $services == *"FastAPI Backend"* ]]; then
        echo "Backend"
    elif [[ $services == *"AI Stack"* ]]; then
        echo "AI Stack"
    elif [[ $services == *"NPU Worker"* ]]; then
        echo "NPU Worker"
    elif [[ $services == *"Redis"* ]]; then
        echo "Redis"
    elif [[ $services == *"SSH"* ]]; then
        echo "Generic Linux"
    else
        echo "Unknown"
    fi
}

# Get hostname for IP
get_hostname() {
    local ip=$1
    
    # Try to resolve hostname
    local hostname=$(host $ip 2>/dev/null | awk '{print $NF}' | sed 's/\.$//') 
    if [[ $hostname == *"not found"* ]] || [[ $hostname == "$ip" ]]; then
        hostname="N/A"
    fi
    echo "$hostname"
}

# Scan AutoBot network for VMs
scan_network() {
    local network=$1
    local discovered_vms=()
    
    echo -e "${CYAN}🔍 Scanning AutoBot internal network: $network${NC}"
    echo -e "${YELLOW}This may take 30-60 seconds...${NC}"
    
    # Extract network base (e.g., 192.168.100 from 192.168.100.0/24)
    local network_base=$(echo $network | cut -d'.' -f1-3)
    
    # Use nmap to quickly find live hosts
    echo -e "${GRAY}Running initial host discovery...${NC}"
    local live_hosts=($(nmap -sn ${network} 2>/dev/null | grep "Nmap scan report" | awk '{print $5}' | grep -E "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$"))
    
    if [[ ${#live_hosts[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No hosts found with nmap, trying manual scan...${NC}"
        # Manual ping scan for VM range (10-50)
        for i in {10..50}; do
            local ip="${network_base}.$i"
            if ping -c 1 -W 1 $ip &> /dev/null; then
                live_hosts+=($ip)
            fi
        done
    fi
    
    if [[ ${#live_hosts[@]} -eq 0 ]]; then
        echo -e "${RED}❌ No live hosts found on network $network${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✅ Found ${#live_hosts[@]} live hosts, testing services...${NC}"
    
    # Test each live host for AutoBot services
    local host_count=0
    for ip in "${live_hosts[@]}"; do
        ((host_count++))
        echo -ne "\r${GRAY}Testing host $host_count/${#live_hosts[@]}: $ip${NC}"
        
        local hostname=$(get_hostname $ip)
        local services=$(test_vm_services $ip)
        local vm_type=$(identify_vm_type "$services")
        
        if [[ -n "$services" ]]; then
            discovered_vms+=("$ip|$hostname|$vm_type|$services")
            echo -e "\n${GREEN}✅ Found AutoBot VM: $ip ($vm_type)${NC}"
        fi
    done
    
    echo -e "\n"
    echo "${discovered_vms[@]}"
}

# Update Ansible inventory with discovered IPs
update_ansible_inventory() {
    local vms=("$@")
    
    if [[ ! -f "$INVENTORY_PATH" ]]; then
        echo -e "${RED}❌ Inventory file not found: $INVENTORY_PATH${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}📝 Updating Ansible inventory at: $INVENTORY_PATH${NC}"
    
    # Create backup
    cp "$INVENTORY_PATH" "${INVENTORY_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Update IPs for each discovered VM
    for vm_data in "${vms[@]}"; do
        IFS='|' read -r ip hostname vm_type services <<< "$vm_data"
        
        if [[ "$vm_type" != "Unknown" && "$vm_type" != "Generic Linux" ]]; then
            local service_name=""
            case "$vm_type" in
                "Frontend") service_name="autobot-frontend" ;;
                "Backend") service_name="autobot-backend" ;;
                "AI Stack") service_name="autobot-aistack" ;;
                "NPU Worker") service_name="autobot-npu" ;;
                "Redis") service_name="autobot-redis" ;;
            esac
            
            if [[ -n "$service_name" ]]; then
                # Update ansible_host line for this service
                sed -i "s/\($service_name:.*ansible_host:\s*\)[0-9.]*/\1$ip/" "$INVENTORY_PATH"
                echo -e "  ${GREEN}✅ Updated $service_name -> $ip${NC}"
            fi
        fi
    done
    
    echo -e "${GREEN}📝 Ansible inventory updated successfully!${NC}"
}

# Main execution
main() {
    echo -e "${CYAN}🤖 AutoBot VM Discovery Tool${NC}"
    echo -e "${CYAN}================================${NC}"
    
    # Check requirements
    check_requirements
    
    # Check if we can reach the AutoBot network
    local gateway_ip=$(echo $NETWORK_RANGE | cut -d'/' -f1 | sed 's/0$/1/')
    if ! ping -c 1 -W 2 $gateway_ip &> /dev/null; then
        echo -e "${YELLOW}⚠️  Cannot reach AutoBot gateway at $gateway_ip${NC}"
        echo -e "${YELLOW}   Make sure AutoBot Internal network is configured${NC}"
    else
        echo -e "${GREEN}🖥️  AutoBot gateway reachable: $gateway_ip${NC}"
    fi
    
    # Scan network
    local discovered_vms=($(scan_network $NETWORK_RANGE))
    
    if [[ ${#discovered_vms[@]} -eq 0 ]]; then
        echo -e "${RED}❌ No AutoBot VMs discovered on network $NETWORK_RANGE${NC}"
        echo -e "${YELLOW}   Make sure VMs are running and network is configured correctly.${NC}"
        exit 1
    fi
    
    # Display results
    echo -e "\n${CYAN}🎯 Discovered AutoBot VMs:${NC}"
    echo -e "${CYAN}=========================${NC}"
    printf "%-15s %-20s %-15s %s\n" "IP" "Hostname" "Type" "Services"
    echo "$(printf '%.0s-' {1..80})"
    
    for vm_data in "${discovered_vms[@]}"; do
        IFS='|' read -r ip hostname vm_type services <<< "$vm_data"
        printf "%-15s %-20s %-15s %s\n" "$ip" "$hostname" "$vm_type" "$services"
    done
    
    if [[ "$SHOW_ALL" == true ]]; then
        echo -e "\n${CYAN}📋 Detailed VM Information:${NC}"
        for vm_data in "${discovered_vms[@]}"; do
            IFS='|' read -r ip hostname vm_type services <<< "$vm_data"
            echo -e "  ${WHITE}IP:${NC} $ip"
            echo -e "  ${GRAY}Hostname:${NC} $hostname"
            echo -e "  ${YELLOW}Type:${NC} $vm_type"
            echo -e "  ${GREEN}Services:${NC} $services"
            echo "  ---"
        done
    fi
    
    if [[ "$UPDATE_INVENTORY" == true ]]; then
        update_ansible_inventory "${discovered_vms[@]}"
    fi
    
    echo -e "\n${CYAN}🔧 Next Steps:${NC}"
    echo -e "  ${GRAY}1. Use --update-inventory to update Ansible hosts.yml${NC}"
    echo -e "  ${GRAY}2. Test connectivity: ansible all -m ping${NC}"
    echo -e "  ${GRAY}3. Deploy services: ./scripts/ansible/deploy.sh deploy-all${NC}"
    
    echo -e "\n${GREEN}✅ Discovery complete!${NC}"
}

# Run main function
main "$@"