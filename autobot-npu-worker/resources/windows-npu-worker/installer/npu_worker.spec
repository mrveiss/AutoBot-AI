# -*- mode: python ; coding: utf-8 -*-
"""
AutoBot NPU Worker - PyInstaller Spec File
Bundles Python application with all dependencies for Windows deployment
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# Base paths
block_cipher = None
app_path = os.path.abspath(os.path.join(SPECPATH, '..', 'app'))
config_path = os.path.abspath(os.path.join(SPECPATH, '..', 'config'))

# Collect OpenVINO dependencies
openvino_datas = collect_data_files('openvino')
openvino_binaries = collect_dynamic_libs('openvino')
openvino_hiddenimports = collect_submodules('openvino')

# Collect other package data files
fastapi_datas = collect_data_files('fastapi')
pydantic_datas = collect_data_files('pydantic')
uvicorn_datas = collect_data_files('uvicorn')

# Configuration files to include
added_files = [
    (os.path.join(config_path, 'npu_worker.yaml'), 'config'),
    (os.path.join(config_path, '*.yaml'), 'config'),
]

# Combine all data files
all_datas = added_files + openvino_datas + fastapi_datas + pydantic_datas + uvicorn_datas

# All binaries
all_binaries = openvino_binaries

# Hidden imports (modules not automatically detected)
hidden_imports = [
    # OpenVINO
    'openvino',
    'openvino.runtime',
    'openvino.inference_engine',
    'openvino.tools',

    # FastAPI and dependencies
    'fastapi',
    'fastapi.responses',
    'fastapi.routing',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',

    # Pydantic
    'pydantic',
    'pydantic.dataclasses',
    'pydantic.json',
    'pydantic.networks',
    'pydantic.types',

    # HTTP and networking
    'aiohttp',
    'aiohttp.web',
    'aiohttp.client',

    # Redis
    'redis',
    'redis.asyncio',

    # Scientific computing
    'numpy',
    'numpy.core',
    'numpy.core._multiarray_umath',
    'sklearn',
    'sklearn.utils',
    'sklearn.metrics',
    'sklearn.metrics.pairwise',

    # Logging
    'structlog',

    # Configuration
    'yaml',
    'dotenv',

    # System
    'asyncio',
    'multiprocessing',
    'concurrent.futures',
] + openvino_hiddenimports

# Analysis phase
a = Analysis(
    [os.path.join(app_path, 'npu_worker.py')],
    pathex=[app_path],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary packages to reduce size
        'matplotlib',
        'tkinter',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'setuptools',
        'wheel',
        'pip',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Create PYZ archive (Python bytecode)
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

# Create EXE executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoBotNPUWorker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress with UPX if available
    console=True,  # Console window for logging
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, 'assets', 'icon.ico') if os.path.exists(os.path.join(SPECPATH, 'assets', 'icon.ico')) else None,
    version_file=None,  # TODO: Create version file with product info
)

# Collect all files into dist directory
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AutoBotNPUWorker'
)

# Additional notes for bundling
"""
Build Instructions:
1. Install PyInstaller: pip install pyinstaller
2. Install all dependencies: pip install -r requirements.txt
3. Run PyInstaller: pyinstaller installer/npu_worker.spec
4. Output will be in: dist/AutoBotNPUWorker/

Size Optimization Tips:
- Use UPX compression (enabled above)
- Exclude unnecessary packages (configured in excludes)
- Consider using PyInstaller's --onefile option for single executable

Troubleshooting:
- If OpenVINO fails to bundle, check openvino-dev is installed
- For missing DLL errors, add to binaries manually
- Check PyInstaller warnings for missing modules
"""
