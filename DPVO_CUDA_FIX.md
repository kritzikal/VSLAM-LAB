# DPVO CUDA Kernel Error - Fix Guide

 

## Problem

 

DPVO is crashing with:

```

RuntimeError: CUDA error: no kernel image is available for execution on the device

```

 

**Root Cause**: DPVO's custom CUDA extensions (`altcorr` module) were pre-compiled for a different GPU architecture than your RTX 3060 Ti (compute capability 8.6).

 

## Quick Fix (Try First)

 

### Option 1: Rebuild DPVO CUDA Extensions

 

Run this automated script:

 

```bash

chmod +x fix_dpvo_cuda.sh

./fix_dpvo_cuda.sh

```

 

### Option 2: Manual Rebuild

 

```bash

# Set CUDA architecture for RTX 3060 Ti

export TORCH_CUDA_ARCH_LIST="8.6"

 

# Uninstall current DPVO

pixi run -e dpvo pip uninstall -y dpvo

 

# Reinstall from source (forces recompilation)

pixi run -e dpvo pip install dpvo --no-binary dpvo --force-reinstall --no-cache-dir

```

 

This will take 5-10 minutes to compile.

 

### Option 3: Build from Local DPVO Source (If Available)

 

If DPVO source is in `Baselines/DPVO/`:

 

```bash

cd Baselines/DPVO

export TORCH_CUDA_ARCH_LIST="8.6"

 

# Clean previous builds

rm -rf build/ dist/ *.egg-info

 

# Rebuild for your GPU

pixi run -e dpvo pip install -e . --no-build-isolation --force-reinstall

 

cd ../..

```

 

## Verify Fix

 

Test if DPVO CUDA extensions work:

 

```bash

pixi run -e dpvo python -c "

import torch

from dpvo.altcorr import correlation

coords = torch.randn(1, 100, 2).cuda()

print('✓ DPVO CUDA extensions working!')

"

```

 

If this passes, try running DPVO again:

 

```bash

pixi run vslamlab configs/exp_hamlyn_ablation.yaml

```

 

## Alternative: Use DROID-SLAM Instead

 

If DPVO continues to have issues, you can run the ablation study with DROID-SLAM only:

 

### Create a DROID-SLAM only config:

 

```bash

# Create simplified ablation config

cat > configs/exp_hamlyn_droidslam_only.yaml << 'EOF'

# Ablation Study - DROID-SLAM Only (DPVO having issues)

 

exp_droidslam_baseline:

  Config: config_hamlyn_endoscopy.yaml

  NumRuns: 3

  Parameters: {verbose: 1}

  Module: droidslam

 

exp_droidslam_relaxed:

  Config: config_hamlyn_endoscopy.yaml

  NumRuns: 3

  Parameters: {

    verbose: 1,

    constraint_config: relaxed,

    apply_constraints: true,

    save_raw_trajectory: true,

    refine_iterations: 2

  }

  Module: droidslam

 

exp_droidslam_default:

  Config: config_hamlyn_endoscopy.yaml

  NumRuns: 3

  Parameters: {

    verbose: 1,

    constraint_config: default,

    apply_constraints: true,

    save_raw_trajectory: true,

    refine_iterations: 2

  }

  Module: droidslam

 

exp_droidslam_strict:

  Config: config_hamlyn_endoscopy.yaml

  NumRuns: 3

  Parameters: {

    verbose: 1,

    constraint_config: strict,

    apply_constraints: true,

    save_raw_trajectory: true,

    refine_iterations: 3

  }

  Module: droidslam

EOF

 

# Run DROID-SLAM ablation

pixi run vslamlab configs/exp_hamlyn_droidslam_only.yaml

```

 

## Why This Happens

 

DPVO has custom CUDA kernels that are compiled at installation time. When you install a pre-built wheel, the kernels are compiled for a generic architecture. Your RTX 3060 Ti needs kernels specifically compiled for compute capability 8.6.

 

The solution is to rebuild DPVO from source on your machine, which will compile the kernels for your specific GPU.

 

## Debugging Tips

 

### Check DPVO Installation Type

 

```bash

pixi run -e dpvo pip show dpvo

```

 

Look for "Editable project location" - if it's not there, DPVO is a pre-built package.

 

### Check CUDA Compute Capability

 

```bash

pixi run -e dpvo python -c "

import torch

props = torch.cuda.get_device_properties(0)

print(f'GPU: {props.name}')

print(f'Compute Capability: {props.major}.{props.minor}')

print(f'PyTorch CUDA: {torch.version.cuda}')

"

```

 

Should show:

- Compute Capability: 8.6

- PyTorch CUDA: 12.6

 

### Enable CUDA Debug Mode

 

```bash

export CUDA_LAUNCH_BLOCKING=1

export TORCH_USE_CUDA_DSA=1

 

pixi run vslamlab configs/exp_hamlyn_ablation.yaml

```

 

This gives more detailed error messages.

 

## Still Having Issues?

 

### Check Available GPU Architectures

 

```bash

pixi run -e dpvo python -c "

import torch

if hasattr(torch.cuda, 'get_arch_list'):

    print('Compiled for architectures:', torch.cuda.get_arch_list())

"

```

 

### Try Downgrading PyTorch

 

If rebuild doesn't work, try an older PyTorch version:

 

```bash

pixi run -e dpvo pip install torch==2.2.0 torchvision --index-url https://download.pytorch.org/whl/cu121

```

 

### Use CPU Mode (Very Slow)

 

As a last resort for testing:

 

```bash

CUDA_VISIBLE_DEVICES="" pixi run vslamlab configs/exp_hamlyn_ablation.yaml

```

 

## Summary

 

**Best Solution**: Rebuild DPVO from source with `TORCH_CUDA_ARCH_LIST="8.6"`

 

**Workaround**: Use DROID-SLAM only for ablation study

 

**Quick Test**: Run `./fix_dpvo_cuda.sh` and let it handle everything automatically