#!/bin/bash
# IPTables Security Rules for AutoBot Sandbox
# Advanced network isolation and security rules for the Docker sandbox environment

set -euo pipefail

# Configuration
SECURITY_LEVEL="${SECURITY_LEVEL:-high}"
LOG_ENABLED="${LOG_ENABLED:-true}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [IPTABLES] $*"
}

setup_base_rules() {
    log "Setting up base iptables rules (security level: $SECURITY_LEVEL)"

    # Clear existing rules
    iptables -F
    iptables -X
    iptables -t nat -F
    iptables -t nat -X
    iptables -t mangle -F
    iptables -t mangle -X

    # Set default policies
    iptables -P INPUT DROP
    iptables -P FORWARD DROP
    iptables -P OUTPUT DROP

    # Allow loopback traffic
    iptables -A INPUT -i lo -j ACCEPT
    iptables -A OUTPUT -o lo -j ACCEPT

    # Allow established connections
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

    log "Base rules configured"
}

setup_high_security_rules() {
    log "Configuring high security network rules"

    # Very restrictive - only essential local communication

    # Allow DNS queries (limited)
    iptables -A OUTPUT -p udp --dport 53 -m limit --limit 10/min -j ACCEPT
    iptables -A OUTPUT -p tcp --dport 53 -m limit --limit 10/min -j ACCEPT

    # Block all other outbound traffic
    iptables -A OUTPUT -j LOG --log-prefix "BLOCKED_OUT: " --log-level 4
    iptables -A OUTPUT -j DROP

    # Block all inbound traffic except established
    iptables -A INPUT -j LOG --log-prefix "BLOCKED_IN: " --log-level 4
    iptables -A INPUT -j DROP
}

setup_medium_security_rules() {
    log "Configuring medium security network rules"

    # Allow DNS
    iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
    iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

    # Allow HTTP/HTTPS with rate limiting
    iptables -A OUTPUT -p tcp --dport 80 -m limit --limit 100/min -j ACCEPT
    iptables -A OUTPUT -p tcp --dport 443 -m limit --limit 100/min -j ACCEPT

    # Allow NTP
    iptables -A OUTPUT -p udp --dport 123 -j ACCEPT

    # Log and block everything else
    if [[ "$LOG_ENABLED" == "true" ]]; then
        iptables -A OUTPUT -j LOG --log-prefix "MEDIUM_BLOCKED: " --log-level 4
    fi
    iptables -A OUTPUT -j DROP

    # Block most inbound traffic
    iptables -A INPUT -j DROP
}

setup_low_security_rules() {
    log "Configuring low security network rules"

    # Allow most outbound traffic with logging
    iptables -A OUTPUT -p tcp --dport 1:1024 -j ACCEPT
    iptables -A OUTPUT -p udp --dport 1:1024 -j ACCEPT

    # Log suspicious ports
    iptables -A OUTPUT -p tcp --dport 22 -j LOG --log-prefix "SSH_OUT: "
    iptables -A OUTPUT -p tcp --dport 23 -j LOG --log-prefix "TELNET_OUT: "
    iptables -A OUTPUT -p tcp --dport 3389 -j LOG --log-prefix "RDP_OUT: "

    # Allow after logging
    iptables -A OUTPUT -j ACCEPT

    # Block inbound traffic
    iptables -A INPUT -j DROP
}

setup_ddos_protection() {
    log "Setting up DDoS protection rules"

    # Limit new connections
    iptables -A INPUT -p tcp --dport 22 -m limit --limit 3/min --limit-burst 3 -j ACCEPT
    iptables -A INPUT -p tcp --dport 80 -m limit --limit 25/min --limit-burst 100 -j ACCEPT

    # Protection against port scans
    iptables -A INPUT -m recent --name portscan --rcheck --seconds 86400 -j DROP
    iptables -A INPUT -m recent --name portscan --set -j LOG --log-prefix "PORT_SCAN: "
    iptables -A INPUT -m recent --name portscan --set -j DROP

    # SYN flood protection
    iptables -A INPUT -p tcp --syn -m limit --limit 1/s --limit-burst 3 -j ACCEPT
    iptables -A INPUT -p tcp --syn -j DROP

    # Ping flood protection
    iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 1/s -j ACCEPT
    iptables -A INPUT -p icmp --icmp-type echo-request -j DROP
}

setup_logging_rules() {
    if [[ "$LOG_ENABLED" != "true" ]]; then
        return
    fi

    log "Setting up security logging rules"

    # Log invalid packets
    iptables -A INPUT -m state --state INVALID -j LOG --log-prefix "INVALID: "
    iptables -A INPUT -m state --state INVALID -j DROP

    # Log fragmented packets
    iptables -A INPUT -f -j LOG --log-prefix "FRAGMENT: "
    iptables -A INPUT -f -j DROP

    # Log XMAS packets
    iptables -A INPUT -p tcp --tcp-flags ALL ALL -j LOG --log-prefix "XMAS: "
    iptables -A INPUT -p tcp --tcp-flags ALL ALL -j DROP

    # Log NULL packets
    iptables -A INPUT -p tcp --tcp-flags ALL NONE -j LOG --log-prefix "NULL: "
    iptables -A INPUT -p tcp --tcp-flags ALL NONE -j DROP
}

setup_application_rules() {
    log "Setting up application-specific rules"

    # Allow sandbox applications
    iptables -A OUTPUT -m owner --uid-owner 1000 -j ACCEPT  # sandbox user

    # Restrict other users
    iptables -A OUTPUT -m owner --uid-owner 1001 -j DROP   # sandbox-restricted

    # Monitor specific applications
    iptables -A OUTPUT -m string --string "wget" --algo bm -j LOG --log-prefix "WGET: "
    iptables -A OUTPUT -m string --string "curl" --algo bm -j LOG --log-prefix "CURL: "
}

save_rules() {
    log "Saving iptables rules"

    # Save current rules
    iptables-save > /etc/iptables/rules.v4 2>/dev/null || true

    # Create backup
    iptables-save > "/var/log/autobot/iptables-$(date +%Y%m%d-%H%M%S).rules" 2>/dev/null || true
}

show_status() {
    log "Current iptables status:"
    iptables -L -n -v --line-numbers
}

main() {
    case "${1:-setup}" in
        "setup")
            setup_base_rules
            setup_ddos_protection
            setup_logging_rules

            case "$SECURITY_LEVEL" in
                "high")
                    setup_high_security_rules
                    ;;
                "medium")
                    setup_medium_security_rules
                    ;;
                "low")
                    setup_low_security_rules
                    ;;
                *)
                    log "Unknown security level: $SECURITY_LEVEL, using high"
                    setup_high_security_rules
                    ;;
            esac

            setup_application_rules
            save_rules
            log "IPTables rules configured for security level: $SECURITY_LEVEL"
            ;;
        "status")
            show_status
            ;;
        "save")
            save_rules
            ;;
        "clear")
            iptables -F
            iptables -X
            iptables -P INPUT ACCEPT
            iptables -P FORWARD ACCEPT
            iptables -P OUTPUT ACCEPT
            log "IPTables rules cleared"
            ;;
        *)
            echo "Usage: $0 {setup|status|save|clear}"
            exit 1
            ;;
    esac
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root for iptables configuration"
    exit 1
fi

main "$@"
