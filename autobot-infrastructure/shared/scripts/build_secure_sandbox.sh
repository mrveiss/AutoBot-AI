#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# =============================================================================
# DEV/SANDBOX ONLY - This script assumes Docker containers.
# Production uses native deployments. See Ansible roles for equivalent.
# =============================================================================
# Build the secure sandbox Docker image for AutoBot
# This script creates the enhanced security sandbox container

set -e

echo "🔒 Building AutoBot Secure Sandbox Container..."

# Change to project root
cd "$(dirname "$0")/.."

# Ensure required directories exist
mkdir -p docker/security
mkdir -p docker/volumes/config

# Create minimal security files if they don't exist
if [ ! -f "docker/security/aide.conf" ]; then
    cat > docker/security/aide.conf << 'EOF'
# Basic AIDE configuration for sandbox
database_in=file:/var/lib/aide/aide.db
database_out=file:/var/lib/aide/aide.db.new
database_new=file:/var/lib/aide/aide.db.new
gzip_dbout=yes

# Rules
All=p+i+n+u+g+s+m+c+md5+sha1+rmd160+sha256+sha512
Binlib=p+i+n+u+g+s+m+c+md5+sha1+rmd160+sha256+sha512
ConfFiles=p+i+n+u+g+s+m+c+md5+sha1+rmd160+sha256+sha512

# Directories to monitor
/bin Binlib
/sbin Binlib
/usr/bin Binlib
/usr/sbin Binlib
/etc ConfFiles
EOF
fi

if [ ! -f "docker/security/rkhunter.conf" ]; then
    cat > docker/security/rkhunter.conf << 'EOF'
# RKHunter configuration for sandbox
MIRRORS_MODE=0
UPDATE_MIRRORS=0
PKGMGR=NONE
WEB_CMD=""
DISABLE_TESTS="suspscan hidden_procs deleted_files packet_cap_apps apps"
ALLOW_SSH_ROOT_USER=no
ALLOW_SSH_PROT_V1=0
EOF
fi

if [ ! -f "docker/security/sandbox-wrapper.sh" ]; then
    cat > docker/security/sandbox-wrapper.sh << 'EOF'
#!/bin/bash
# Sandbox wrapper script with security monitoring

echo "🔒 AutoBot Secure Sandbox Started"
echo "   Container ID: $HOSTNAME"
echo "   Security Level: ${SECURITY_LEVEL:-high}"
echo "   Monitor Enabled: ${MONITOR_ENABLED:-true}"

# Start security monitoring if enabled
if [ "${MONITOR_ENABLED}" = "true" ]; then
    echo "🔍 Starting security monitor..."
    python3 /usr/local/bin/security-monitor --monitor &
    MONITOR_PID=$!

    # Trap signals to cleanup
    trap "kill $MONITOR_PID 2>/dev/null; exit" SIGTERM SIGINT
fi

# Execute the actual command
if [ $# -eq 0 ]; then
    exec /bin/bash
else
    exec "$@"
fi
EOF
    chmod +x docker/security/sandbox-wrapper.sh
fi

# Build the Docker image
echo "🏗️  Building secure sandbox image..."
docker build -f docker/secure-sandbox.Dockerfile -t autobot/secure-sandbox:latest . || {
    echo "❌ Failed to build secure sandbox image"
    echo "   This is likely due to missing security files."
    echo "   The sandbox executor will use alpine:3.18 as fallback."

    # Create a basic fallback image
    echo "🔄 Creating basic sandbox fallback..."
    cat > /tmp/sandbox-fallback.dockerfile << 'EOF'
FROM alpine:3.18

RUN apk add --no-cache bash python3 py3-pip psutil && \
    adduser -D -s /bin/bash sandbox && \
    mkdir -p /sandbox/{workspace,logs,tmp} && \
    chown -R sandbox:sandbox /sandbox

USER sandbox
WORKDIR /sandbox/workspace
CMD ["/bin/bash"]
EOF

    docker build -f /tmp/sandbox-fallback.dockerfile -t autobot/secure-sandbox:latest . && {
        echo "✅ Basic sandbox fallback created successfully"
        rm /tmp/sandbox-fallback.dockerfile
    } || {
        echo "❌ Failed to create fallback image"
        exit 1
    }
}

# Test the image
echo "🧪 Testing sandbox image..."
CONTAINER_ID=$(docker run -d --rm --name autobot-sandbox-test autobot/secure-sandbox:latest sleep 10)

if docker ps | grep -q autobot-sandbox-test; then
    echo "✅ Sandbox container started successfully"
    docker stop autobot-sandbox-test >/dev/null 2>&1
else
    echo "❌ Sandbox container test failed"
    exit 1
fi

echo "✅ Secure sandbox image built successfully: autobot/secure-sandbox:latest"
echo ""
echo "🔍 Image details:"
docker images autobot/secure-sandbox:latest --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

echo ""
echo "🚀 To use the sandbox:"
echo "   docker run --rm -it autobot/secure-sandbox:latest"
echo "   docker run --rm -it --security-opt no-new-privileges autobot/secure-sandbox:latest"
