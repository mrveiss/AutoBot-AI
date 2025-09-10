#!/bin/bash
# Test Docker connectivity and proxy configuration

echo "🧪 Testing Docker connectivity..."
echo

# Test 1: Docker daemon connection
echo "1. Testing Docker daemon connection..."
if docker version > /dev/null 2>&1; then
    echo "   ✅ Docker daemon is accessible"
else
    echo "   ❌ Docker daemon connection failed"
    echo "   💡 Check if Docker Desktop is running on Windows"
fi
echo

# Test 2: Registry connectivity
echo "2. Testing Docker registry connectivity..."
if curl -s --connect-timeout 5 https://registry-1.docker.io/v2/ > /dev/null; then
    echo "   ✅ Can reach Docker registry directly"
else
    echo "   ❌ Cannot reach Docker registry"
    echo "   💡 This suggests proxy is blocking registry access"
fi
echo

# Test 3: Try pulling a small test image
echo "3. Testing image pull (small test image)..."
if timeout 30 docker pull hello-world > /dev/null 2>&1; then
    echo "   ✅ Image pull successful - proxy is working correctly"
else
    echo "   ❌ Image pull failed - proxy configuration needed"
    echo
    echo "📋 DOCKER DESKTOP PROXY FIX REQUIRED:"
    echo "   1. Open Docker Desktop on Windows"
    echo "   2. Go to Settings → Resources → Proxies"
    echo "   3. Either:"
    echo "      a) Disable 'Manual proxy configuration', OR"
    echo "      b) Add these to 'Bypass proxy settings':"
    echo "         • *.docker.io"
    echo "         • registry-1.docker.io"
    echo "         • 192.168.65.0/24"
    echo "         • localhost"
    echo "         • 127.0.0.1"
    echo
fi
echo

# Test 4: Network connectivity
echo "4. Testing Docker network connectivity..."
docker network ls | grep -q autobot-network
if [ $? -eq 0 ]; then
    echo "   ✅ AutoBot network exists"
else
    echo "   ℹ️  AutoBot network will be created when containers start"
fi

echo
echo "🎯 NEXT STEPS:"
echo "   1. Fix proxy settings in Docker Desktop (Windows)"
echo "   2. Run: docker-compose -f docker/compose/docker-compose.hybrid.yml up -d"
echo "   3. Test with: ./run_agent.sh --test-mode"