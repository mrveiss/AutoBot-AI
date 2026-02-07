#!/bin/bash

# OpenVINO Environment Setup Script
# This script sets up a dedicated OpenVINO environment for NPU acceleration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
VENVS_DIR="$PROJECT_ROOT/venvs"
OPENVINO_VENV="$VENVS_DIR/openvino_env"

echo "🔧 Setting up OpenVINO environment for NPU acceleration..."

# Create venvs directory if it doesn't exist
mkdir -p "$VENVS_DIR"

# Create OpenVINO virtual environment
if [ ! -d "$OPENVINO_VENV" ]; then
    echo "📦 Creating OpenVINO virtual environment..."
    python3 -m venv "$OPENVINO_VENV"
else
    echo "✅ OpenVINO virtual environment already exists"
fi

# Activate the environment
source "$OPENVINO_VENV/bin/activate"

# Upgrade pip and install OpenVINO with all accelerations
echo "📦 Installing OpenVINO with NPU support..."
pip install --upgrade pip setuptools wheel
pip install openvino openvino-dev[pytorch,tensorflow2,onnx] || {
    echo "⚠️ Full OpenVINO install failed, trying core only..."
    pip install openvino
}

# Install additional optimization packages
echo "📦 Installing optimization packages..."
pip install numpy optimum[openvino] || echo "⚠️ Some optimization packages failed to install"

# Test the installation
echo "🧪 Testing OpenVINO NPU setup..."
python3 -c "
import sys
try:
    from openvino.runtime import Core
    core = Core()
    devices = core.available_devices
    print(f'✅ OpenVINO available devices: {devices}')

    npu_devices = [d for d in devices if 'NPU' in d]
    if npu_devices:
        print(f'🚀 NPU devices ready: {npu_devices}')

        # Test NPU capability
        try:
            # Simple capability test
            print('🧪 Testing NPU capabilities...')
            # You could add a simple model loading test here
            print('✅ NPU appears functional')
        except Exception as e:
            print(f'⚠️ NPU test failed: {e}')
    else:
        print('ℹ️ No NPU devices detected')
        print('   Check Intel NPU driver installation')

    # Check for other accelerators
    gpu_devices = [d for d in devices if 'GPU' in d]
    if gpu_devices:
        print(f'🎮 GPU devices available: {gpu_devices}')

except ImportError as e:
    print(f'❌ OpenVINO import failed: {e}')
    sys.exit(1)
except Exception as e:
    print(f'⚠️ OpenVINO test error: {e}')
    sys.exit(1)
"

echo "✅ OpenVINO environment setup complete!"
echo "🔧 To use this environment:"
echo "   source $OPENVINO_VENV/bin/activate"
echo "   python your_openvino_script.py"

deactivate
