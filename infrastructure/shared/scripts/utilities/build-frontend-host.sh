#!/bin/bash
# Build frontend on host (fast) then copy to Docker

echo "🚀 Building frontend on host (bypassing Docker networking issues)..."

cd autobot-vue

# Install dependencies on host (should be fast with your 1Gbps)
echo "📦 Installing npm dependencies on host..."
npm install

# Build the production bundle
echo "🔨 Building production bundle..."
npm run build

# Copy built files to Docker context
echo "📋 Copying built files for Docker..."
mkdir -p ../docker/frontend/dist
cp -r dist/* ../docker/frontend/dist/

echo "✅ Frontend built successfully on host!"
echo "   Now Docker just needs to copy static files (seconds, not hours)"

cd ..
