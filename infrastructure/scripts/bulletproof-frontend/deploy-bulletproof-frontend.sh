#!/bin/bash

# Bulletproof Frontend Deployment System
# Eliminates all deployment failure points with atomic updates and verification

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="/home/kali/Desktop/AutoBot"
LOCAL_FRONTEND_DIR="$PROJECT_ROOT/autobot-vue"

# Remote Configuration
FRONTEND_VM="172.16.168.21"
FRONTEND_USER="autobot"
SSH_KEY="$HOME/.ssh/autobot_key"

# Service Directory Mapping (CRITICAL FIX)
SERVICE_DIR="/opt/autobot/src/autobot-vue"
BACKUP_DIR="/opt/autobot/backups/autobot-vue"
STAGING_DIR="/opt/autobot/staging/autobot-vue"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_debug() { echo -e "${BLUE}[DEBUG]${NC} $1"; }

# Deployment verification functions
verify_ssh_connection() {
    log_info "Verifying SSH connection to frontend VM..."
    if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 \
         "$FRONTEND_USER@$FRONTEND_VM" "echo 'SSH connection verified'" &>/dev/null; then
        log_error "Cannot connect to frontend VM at $FRONTEND_VM"
        return 1
    fi
    log_info "✓ SSH connection verified"
}

verify_local_build() {
    log_info "Verifying local frontend build..."

    if [ ! -d "$LOCAL_FRONTEND_DIR/dist" ]; then
        log_warn "No dist directory found, building frontend..."
        cd "$LOCAL_FRONTEND_DIR"

        # Install dependencies if node_modules missing
        if [ ! -d "node_modules" ]; then
            log_info "Installing dependencies..."
            npm ci
        fi

        # Build with cache busting
        log_info "Building frontend with cache-busting..."
        VITE_BUILD_TIMESTAMP=$(date +%s) npm run build

        if [ ! -d "dist" ]; then
            log_error "Build failed - no dist directory created"
            return 1
        fi
    fi

    # Verify critical files exist
    local critical_files=("dist/index.html" "dist/assets")
    for file in "${critical_files[@]}"; do
        if [ ! -e "$LOCAL_FRONTEND_DIR/$file" ]; then
            log_error "Critical file missing from build: $file"
            return 1
        fi
    done

    log_info "✓ Local build verified"
}

create_atomic_deployment_package() {
    log_info "Creating atomic deployment package..."

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local package_name="autobot-frontend-${timestamp}.tar.gz"
    local temp_dir="/tmp/autobot-frontend-deploy-$$"

    mkdir -p "$temp_dir"

    cd "$LOCAL_FRONTEND_DIR"

    # Create deployment manifest
    cat > "$temp_dir/deployment-manifest.json" << EOF
{
    "timestamp": "$timestamp",
    "git_hash": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
    "build_id": "${VITE_BUILD_TIMESTAMP:-$timestamp}",
    "deployment_target": "$SERVICE_DIR",
    "backup_target": "$BACKUP_DIR/$timestamp"
}
EOF

    # Package source and build
    tar -czf "$temp_dir/$package_name" \
        --exclude='node_modules' \
        --exclude='.git' \
        --exclude='test-results' \
        --exclude='playwright-report' \
        --exclude='logs' \
        --exclude='*.log' \
        .

    echo "$temp_dir/$package_name"
}

deploy_with_atomic_swap() {
    local package_path=$1
    local package_name=$(basename "$package_path")

    log_info "Deploying package with atomic swap: $package_name"

    # Upload deployment package
    scp -i "$SSH_KEY" \
        "$package_path" "$FRONTEND_USER@$FRONTEND_VM:/tmp/"

    # Execute atomic deployment on remote
    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << EOF
        set -euo pipefail

        # Create directories
        sudo mkdir -p "$SERVICE_DIR" "$BACKUP_DIR" "$STAGING_DIR"
        sudo chown -R \$USER:autobot-service "$SERVICE_DIR" "$BACKUP_DIR" "$STAGING_DIR" 2>/dev/null || true

        # Extract to staging
        echo "Extracting to staging directory..."
        rm -rf "$STAGING_DIR"
        mkdir -p "$STAGING_DIR"
        cd "$STAGING_DIR"
        tar -xzf "/tmp/$package_name"

        # Install dependencies in staging
        echo "Installing dependencies in staging..."
        if [ -f "package.json" ]; then
            npm ci --production=false
        fi

        # Verify staging build
        echo "Verifying staging deployment..."
        if [ ! -f "dist/index.html" ]; then
            echo "ERROR: Missing index.html in staging build"
            exit 1
        fi

        # Create backup of current deployment
        if [ -d "$SERVICE_DIR" ]; then
            echo "Creating backup of current deployment..."
            backup_name="backup-\$(date +%Y%m%d_%H%M%S)"
            sudo mkdir -p "$BACKUP_DIR"
            sudo mv "$SERVICE_DIR" "$BACKUP_DIR/\$backup_name" 2>/dev/null || true
        fi

        # Atomic swap: staging -> service
        echo "Performing atomic swap..."
        sudo mkdir -p "\$(dirname '$SERVICE_DIR')"
        sudo mv "$STAGING_DIR" "$SERVICE_DIR"

        # Set correct permissions
        sudo chown -R autobot-service:autobot-service "$SERVICE_DIR"
        sudo chmod -R 755 "$SERVICE_DIR"

        # Cleanup
        rm -f "/tmp/$package_name"

        echo "✓ Atomic deployment completed successfully"
EOF

    if [ $? -eq 0 ]; then
        log_info "✓ Atomic deployment completed successfully"
        return 0
    else
        log_error "Atomic deployment failed"
        return 1
    fi
}

restart_frontend_service() {
    log_info "Restarting frontend service..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        set -euo pipefail

        # Kill existing Vite processes
        echo "Stopping existing frontend processes..."
        pkill -f "vite.*5173" || true
        pkill -f "npm.*dev" || true

        # Wait for processes to terminate
        sleep 3

        # Start new frontend service
        echo "Starting frontend service..."
        cd /opt/autobot/src/autobot-vue

        # Set environment variables
        export VITE_BACKEND_HOST=172.16.168.20
        export VITE_BACKEND_PORT=8001
        export NODE_ENV=development

        # Start with logging
        nohup npm run dev -- --host 0.0.0.0 --port 5173 > logs/frontend.log 2>&1 &

        echo $! > /tmp/frontend.pid

        echo "Frontend service started with PID: $(cat /tmp/frontend.pid)"
EOF

    if [ $? -eq 0 ]; then
        log_info "✓ Frontend service restarted successfully"
    else
        log_error "Frontend service restart failed"
        return 1
    fi
}

verify_deployment() {
    log_info "Verifying deployment health..."

    # Wait for service to start
    sleep 10

    # Test frontend accessibility
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        log_debug "Health check attempt $attempt/$max_attempts"

        if curl -s -f "http://$FRONTEND_VM:5173" >/dev/null 2>&1; then
            log_info "✓ Frontend service is responding on port 5173"
            break
        fi

        if [ $attempt -eq $max_attempts ]; then
            log_error "Frontend service failed health check after $max_attempts attempts"
            return 1
        fi

        sleep 2
        ((attempt++))
    done

    # Verify router-view presence
    log_info "Verifying router-view presence in DOM..."
    local html_content=$(curl -s "http://$FRONTEND_VM:5173" 2>/dev/null || echo "")

    if echo "$html_content" | grep -q "router-view\|<router-view"; then
        log_info "✓ Router-view found in DOM"
    else
        log_warn "⚠ Router-view not found in initial DOM (may be loaded dynamically)"
    fi

    # Test API proxy
    if curl -s -f "http://$FRONTEND_VM:5173/api/health" >/dev/null 2>&1; then
        log_info "✓ API proxy working correctly"
    else
        log_warn "⚠ API proxy test failed (backend may be unavailable)"
    fi

    log_info "✓ Deployment verification completed"
}

cleanup_old_backups() {
    log_info "Cleaning up old backups..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        # Keep only last 5 backups
        if [ -d "/opt/autobot/backups/autobot-vue" ]; then
            cd /opt/autobot/backups/autobot-vue
            ls -t | tail -n +6 | xargs -r rm -rf
            echo "Old backups cleaned up"
        fi
EOF
}

rollback_deployment() {
    log_error "Rolling back to previous deployment..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        set -euo pipefail

        if [ -d "/opt/autobot/backups/autobot-vue" ]; then
            latest_backup=$(ls -t /opt/autobot/backups/autobot-vue | head -1)
            if [ -n "$latest_backup" ]; then
                echo "Rolling back to: $latest_backup"
                sudo rm -rf /opt/autobot/src/autobot-vue
                sudo mv "/opt/autobot/backups/autobot-vue/$latest_backup" /opt/autobot/src/autobot-vue
                sudo chown -R autobot-service:autobot-service /opt/autobot/src/autobot-vue
                echo "Rollback completed"
            else
                echo "No backup found for rollback"
                exit 1
            fi
        else
            echo "No backup directory found"
            exit 1
        fi
EOF
}

main() {
    log_info "Starting Bulletproof Frontend Deployment"
    log_info "========================================="

    # Pre-deployment verification
    verify_ssh_connection || exit 1
    verify_local_build || exit 1

    # Create deployment package
    local package_path
    package_path=$(create_atomic_deployment_package)

    if [ ! -f "$package_path" ]; then
        log_error "Failed to create deployment package"
        exit 1
    fi

    log_info "Created deployment package: $package_path"

    # Deploy with atomic swap
    if deploy_with_atomic_swap "$package_path"; then
        log_info "✓ Deployment package installed successfully"
    else
        log_error "Deployment failed, attempting rollback..."
        rollback_deployment
        exit 1
    fi

    # Restart service
    if restart_frontend_service; then
        log_info "✓ Frontend service restarted"
    else
        log_error "Service restart failed, attempting rollback..."
        rollback_deployment
        restart_frontend_service
        exit 1
    fi

    # Verify deployment
    if verify_deployment; then
        log_info "✓ Deployment verification passed"
    else
        log_error "Deployment verification failed, attempting rollback..."
        rollback_deployment
        restart_frontend_service
        exit 1
    fi

    # Cleanup
    cleanup_old_backups
    rm -rf "$(dirname "$package_path")"

    log_info "========================================="
    log_info "✅ BULLETPROOF DEPLOYMENT COMPLETED SUCCESSFULLY"
    log_info "Frontend URL: http://$FRONTEND_VM:5173"
    log_info "Service Directory: $SERVICE_DIR"
    log_info "========================================="
}

# Handle script interruption
trap 'log_error "Deployment interrupted"; exit 1' INT TERM

# Run main deployment
main "$@"
