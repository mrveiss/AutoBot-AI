#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# =============================================================================
# DEV/SANDBOX ONLY - This script assumes Docker containers.
# Production uses native deployments. See Ansible roles for equivalent.
# =============================================================================
# Build the hardened sandbox image `autobot/secure-sandbox:latest`.
#
# (#15127) This is the only builder of that image, and the image is not
# optional: `autobot-backend/secure_sandbox_executor.py` runs every
# code-execution container from it, and
# `autobot-backend/tests/integration/test_codeexec_docker_smoke.py` -- the gate
# that must pass before AUTOBOT_CODEEXEC_ENABLED is set anywhere -- self-skips
# unless the image is present locally. Nothing documented how to produce it.
#
# Two defects made this unrunnable and unsafe, both from the directory moves:
#   * `-f docker/secure-sandbox.Dockerfile` resolved to a path that no longer
#     held the Dockerfile, so the real build could never succeed;
#   * the failure branch then built an unhardened `alpine:3.18` and tagged it
#     `autobot/secure-sandbox:latest`, so the executor would have run untrusted
#     code in a container with none of the sandbox hardening, under the name
#     that asserts it has. A silent downgrade of a security boundary is worse
#     than no image at all, so the fallback is gone and this fails closed.
#
# The three security inputs this used to fabricate with heredocs are tracked
# files now (docker/security/), and a fabricated stand-in would be weaker than
# the tracked one it shadowed. Missing inputs are an error, not a prompt to
# invent them.

set -euo pipefail

# Build context is the shared tree: the Dockerfile's COPY paths are all
# `docker/security/...` relative to it, and docker-compose.secure-sandbox.yml
# uses the same context.
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly BUILD_CONTEXT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly DOCKERFILE="docker/secure-sandbox.Dockerfile"
readonly IMAGE="autobot/secure-sandbox:latest"

# Every path the Dockerfile COPYs, relative to the build context.
readonly REQUIRED_INPUTS=(
    "${DOCKERFILE}"
    "docker/security/aide.conf"
    "docker/security/iptables-rules.sh"
    "docker/security/limits.conf"
    "docker/security/rkhunter.conf"
    "docker/security/sandbox-wrapper.sh"
    "docker/security/security-monitor.py"
)

echo "🔒 Building AutoBot Secure Sandbox Container..."
echo "   Context: ${BUILD_CONTEXT}"

cd "${BUILD_CONTEXT}"

missing=()
for input in "${REQUIRED_INPUTS[@]}"; do
    [ -f "${input}" ] || missing+=("${input}")
done

if [ ${#missing[@]} -gt 0 ]; then
    echo "❌ Refusing to build: these inputs are missing from ${BUILD_CONTEXT}" >&2
    printf '   %s\n' "${missing[@]}" >&2
    echo "   Restore them; do not substitute weaker stand-ins for a hardened image." >&2
    exit 1
fi

echo "🏗️  Building ${IMAGE}..."
if ! docker build -f "${DOCKERFILE}" -t "${IMAGE}" .; then
    echo "❌ Failed to build ${IMAGE}" >&2
    echo "   Not falling back to an unhardened image: the sandbox executor and the" >&2
    echo "   code-execution smoke gate both treat this tag as the hardened sandbox." >&2
    exit 1
fi

echo "🧪 Testing sandbox image..."
docker run -d --rm --name autobot-sandbox-test "${IMAGE}" sleep 10 >/dev/null

if docker ps --format '{{.Names}}' | grep -qx autobot-sandbox-test; then
    echo "✅ Sandbox container started successfully"
    docker stop autobot-sandbox-test >/dev/null 2>&1 || true
else
    echo "❌ Sandbox container test failed" >&2
    exit 1
fi

echo "✅ Secure sandbox image built successfully: ${IMAGE}"
echo ""
echo "🔍 Image details:"
docker images "${IMAGE}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
