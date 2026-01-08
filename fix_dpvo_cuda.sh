#!/bin/bash

# Fix DPVO CUDA kernel compatibility for RTX 3060 Ti

# This script rebuilds DPVO's custom CUDA extensions for your GPU architecture

 

set -e  # Exit on error

 

echo "=========================================="

echo "DPVO CUDA Extension Rebuild Script"

echo "=========================================="

echo ""

 

# Check if we're in the right directory

if [ ! -f "pixi.toml" ]; then

    echo "Error: Please run this script from the VSLAM-LAB root directory"

    exit 1

fi

 

echo "Step 1: Checking DPVO installation..."

DPVO_LOCATION=$(pixi run -e dpvo pip show dpvo 2>/dev/null | grep Location | cut -d' ' -f2)

 

if [ -z "$DPVO_LOCATION" ]; then

    echo "Error: DPVO not found in pixi environment"

    exit 1

fi

 

echo "  DPVO installed at: $DPVO_LOCATION"

echo ""

 

echo "Step 2: Checking if DPVO is editable install or package..."

DPVO_TYPE=$(pixi run -e dpvo pip show dpvo | grep "Editable project location" || echo "package")

 

if [[ "$DPVO_TYPE" == "package" ]]; then

    echo "  DPVO is a pre-built package (this is the problem!)"

    echo "  We need to rebuild from source for your RTX 3060 Ti"

else

    echo "  DPVO is editable install"

fi

echo ""

 

echo "Step 3: Setting up environment for CUDA compilation..."

export TORCH_CUDA_ARCH_LIST="8.6"  # RTX 3060 Ti compute capability

export CUDA_HOME=/usr/local/cuda

export PATH=$CUDA_HOME/bin:$PATH

export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

 

echo "  TORCH_CUDA_ARCH_LIST=$TORCH_CUDA_ARCH_LIST"

echo "  CUDA_HOME=$CUDA_HOME"

echo ""

 

echo "Step 4: Finding DPVO source directory..."

if [ -d "Baselines/DPVO" ]; then

    DPVO_SOURCE="Baselines/DPVO"

    echo "  Found DPVO source at: $DPVO_SOURCE"

else

    echo "  Warning: DPVO source not found in Baselines/DPVO"

    echo "  This is OK if DPVO is installed as a package"

fi

echo ""

 

echo "Step 5: Rebuilding DPVO CUDA extensions..."

echo "  This will take a few minutes..."

echo ""

 

# Option A: If DPVO source exists locally, rebuild from there

if [ -d "$DPVO_SOURCE" ]; then

    echo "  Building from local source..."

    cd "$DPVO_SOURCE"

 

    # Clean previous builds

    rm -rf build/ dist/ *.egg-info

 

    # Rebuild

    pixi run -e dpvo pip install -e . --no-build-isolation --force-reinstall

 

    cd ../..

    echo "  ✓ Rebuild complete from local source"

else

    # Option B: Clone and rebuild from GitHub

    echo "  No local source found. Rebuilding from installed package..."

 

    # Uninstall current DPVO

    pixi run -e dpvo pip uninstall -y dpvo

 

    # Reinstall with force recompile

    pixi run -e dpvo pip install dpvo --no-binary dpvo --force-reinstall

 

    echo "  ✓ Rebuild complete from package"

fi

 

echo ""

echo "Step 6: Verifying CUDA extensions..."

pixi run -e dpvo python -c "

import torch

import dpvo

print(f'DPVO version: {dpvo.__version__}')

print(f'PyTorch CUDA: {torch.version.cuda}')

print(f'GPU: {torch.cuda.get_device_name(0)}')

 

# Test altcorr module

try:

    from dpvo.altcorr import correlation

    print('✓ altcorr module loaded successfully')

 

    # Test basic operation

    coords = torch.randn(1, 100, 2).cuda()

    print('✓ CUDA tensor operations working')

 

    print('')

    print('========================================')

    print('✓ DPVO CUDA extensions rebuilt successfully!')

    print('========================================')

except Exception as e:

    print(f'✗ Error: {e}')

    print('CUDA extensions still not working. See troubleshooting below.')

    exit(1)

"

 

echo ""

echo "Done! You can now run the ablation study:"

echo "  pixi run vslamlab configs/exp_hamlyn_ablation.yaml"

echo ""