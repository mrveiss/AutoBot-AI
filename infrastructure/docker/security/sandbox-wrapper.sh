#!/bin/bash
"""
Sandbox Security Wrapper for AutoBot

Enhanced security wrapper that sets up isolation, monitoring, and controls
before executing commands in the sandbox environment.
"""

set -euo pipefail

# Security configuration
SECURITY_LEVEL="${SECURITY_LEVEL:-high}"
MONITOR_ENABLED="${MONITOR_ENABLED:-true}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
SANDBOX_MODE="${SANDBOX_MODE:-restricted}"

# Logging setup
LOG_FILE="/var/log/autobot/sandbox-wrapper.log"
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WRAPPER] $*"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WRAPPER] ERROR: $*" >&2
}

# Security initialization
init_security() {
    log "Initializing sandbox security (level: $SECURITY_LEVEL, mode: $SANDBOX_MODE)"

    # Set up secure environment
    export HISTFILE=/dev/null
    export HISTSIZE=0
    export HISTFILESIZE=0
    unset HISTFILE

    # Limit shell features
    set +H  # Disable history expansion

    # Create secure temporary directory
    export TMPDIR="/sandbox/tmp"
    mkdir -p "$TMPDIR"
    chmod 700 "$TMPDIR"

    # Set resource limits
    ulimit -c 0        # No core dumps
    ulimit -f 102400   # File size limit (100MB)
    ulimit -m 524288   # Memory limit (512MB)
    ulimit -n 256      # Open file limit
    ulimit -u 50       # Process limit
    ulimit -t 300      # CPU time limit (5 minutes)

    # Network restrictions based on security level
    if [[ "$SECURITY_LEVEL" == "high" ]]; then
        # Very restrictive network access
        setup_network_restrictions_high
    elif [[ "$SECURITY_LEVEL" == "medium" ]]; then
        # Moderate network restrictions
        setup_network_restrictions_medium
    fi

    log "Security initialization completed"
}

setup_network_restrictions_high() {
    log "Setting up high-level network restrictions"

    # Block all outbound connections except localhost
    # Note: This would require iptables in a real deployment
    export no_proxy="localhost,127.0.0.1,::1"
    export NO_PROXY="localhost,127.0.0.1,::1"

    # Disable network tools
    alias wget='echo "Network access restricted in high security mode" && false'
    alias curl='echo "Network access restricted in high security mode" && false'
    alias nc='echo "Network tools disabled in high security mode" && false'
    alias netcat='echo "Network tools disabled in high security mode" && false'
}

setup_network_restrictions_medium() {
    log "Setting up medium-level network restrictions"

    # Allow limited outbound but log all connections
    export HTTP_PROXY=""
    export HTTPS_PROXY=""

    # Wrap network tools with logging
    alias wget='log_network_activity wget'
    alias curl='log_network_activity curl'
}

log_network_activity() {
    local tool="$1"
    shift
    log "NETWORK: $tool $*"
    command "$tool" "$@"
}

# File system security
setup_filesystem_security() {
    log "Setting up filesystem security"

    # Create secure workspace
    mkdir -p /sandbox/workspace
    chmod 750 /sandbox/workspace

    # Prevent access to sensitive directories
    if [[ "$SECURITY_LEVEL" == "high" ]]; then
        # Very restrictive file access
        alias find='restricted_find'
        alias locate='echo "locate disabled in high security mode" && false'
        alias which='restricted_which'
    fi

    # Set up file integrity monitoring
    if command -v aide >/dev/null 2>&1; then
        log "Initializing file integrity monitoring"
        aide --init >/dev/null 2>&1 || true
    fi
}

restricted_find() {
    # Only allow find in workspace and tmp directories
    local allowed_paths="/sandbox/workspace /sandbox/tmp"
    local path=""

    for arg in "$@"; do
        if [[ "$arg" =~ ^/ ]]; then
            path="$arg"
            break
        fi
    done

    if [[ -n "$path" ]]; then
        for allowed in $allowed_paths; do
            if [[ "$path" == "$allowed"* ]]; then
                command find "$@"
                return
            fi
        done
        echo "find: access denied to $path (security restriction)"
        return 1
    else
        command find "$@"
    fi
}

restricted_which() {
    # Only show safe commands
    local cmd="$1"
    local safe_commands="bash sh python3 python ls cat grep sed awk"

    for safe in $safe_commands; do
        if [[ "$cmd" == "$safe" ]]; then
            command which "$cmd"
            return
        fi
    done

    echo "$cmd: command not found (security restriction)"
    return 1
}

# Process monitoring
setup_process_monitoring() {
    if [[ "$MONITOR_ENABLED" == "true" ]]; then
        log "Starting security monitoring"

        # Start security monitor in background
        python3 /usr/local/bin/security-monitor &
        echo $! > /tmp/security-monitor.pid

        # Set up cleanup trap
        trap 'cleanup_monitoring' EXIT TERM INT
    fi
}

cleanup_monitoring() {
    if [[ -f /tmp/security-monitor.pid ]]; then
        local pid=$(cat /tmp/security-monitor.pid)
        if kill -0 "$pid" 2>/dev/null; then
            log "Stopping security monitor (PID: $pid)"
            kill "$pid" 2>/dev/null || true
            rm -f /tmp/security-monitor.pid
        fi
    fi
}

# Command execution wrapper
execute_command() {
    local cmd=("$@")

    log "Executing command: ${cmd[*]}"

    # Command validation
    if ! validate_command "${cmd[@]}"; then
        error "Command validation failed: ${cmd[*]}"
        return 1
    fi

    # Set up execution environment
    cd /sandbox/workspace

    # Execute with monitoring
    local start_time=$(date +%s)
    local exit_code=0

    if [[ "$SECURITY_LEVEL" == "high" ]]; then
        # High security: Use timeout and strace monitoring
        timeout 300s strace -o /tmp/strace.log -f "${cmd[@]}" || exit_code=$?
    else
        # Standard execution
        "${cmd[@]}" || exit_code=$?
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log "Command completed with exit code $exit_code (duration: ${duration}s)"

    # Log execution details
    echo "{\"timestamp\":\"$(date -Iseconds)\",\"command\":\"${cmd[*]}\",\"exit_code\":$exit_code,\"duration\":$duration}" >> /var/log/autobot/command-log.jsonl

    return $exit_code
}

validate_command() {
    local cmd=("$@")
    local command_name="${cmd[0]}"

    # Blacklisted commands for security
    local blacklist=(
        "sudo" "su" "doas"
        "passwd" "chsh" "chfn"
        "mount" "umount"
        "iptables" "netfilter"
        "crontab" "at" "batch"
        "systemctl" "service"
        "docker" "podman"
        "ssh" "scp" "rsync"
        "nc" "netcat" "ncat"
        "nmap" "masscan"
        "tcpdump" "wireshark"
        "dd" "fdisk" "parted"
        "mkfs" "fsck"
        "reboot" "shutdown" "halt"
    )

    for blocked in "${blacklist[@]}"; do
        if [[ "$command_name" == "$blocked" ]]; then
            error "Command blocked by security policy: $command_name"
            return 1
        fi
    done

    # Additional validation for high security mode
    if [[ "$SECURITY_LEVEL" == "high" ]]; then
        local whitelist=(
            "bash" "sh" "dash"
            "python3" "python"
            "ls" "cat" "echo" "grep" "sed" "awk"
            "head" "tail" "wc" "sort" "uniq"
            "find" "which" "whereis"
            "cd" "pwd" "mkdir" "rmdir"
            "cp" "mv" "rm" "ln"
            "chmod" "chown"
            "tar" "gzip" "gunzip"
            "ps" "top" "htop"
            "env" "printenv" "export"
        )

        local allowed=false
        for safe in "${whitelist[@]}"; do
            if [[ "$command_name" == "$safe" ]]; then
                allowed=true
                break
            fi
        done

        if [[ "$allowed" != "true" ]]; then
            error "Command not in whitelist (high security mode): $command_name"
            return 1
        fi
    fi

    return 0
}

# Main execution
main() {
    log "AutoBot Sandbox Wrapper starting (PID: $$)"
    log "Security Level: $SECURITY_LEVEL, Monitor: $MONITOR_ENABLED, Mode: $SANDBOX_MODE"

    # Initialize security layers
    init_security
    setup_filesystem_security
    setup_process_monitoring

    # Execute the command or start shell
    if [[ $# -eq 0 ]]; then
        log "Starting interactive shell"
        exec /bin/bash --norc --noprofile
    else
        execute_command "$@"
    fi
}

# Run main function with all arguments
main "$@"
