#!/usr/bin/env python3

"""

CUDA Diagnostic Script for VSLAM-LAB

Checks PyTorch and CUDA configuration

"""

import sys


def check_cuda():
    print("=" * 60)

    print("CUDA DIAGNOSTIC REPORT")

    print("=" * 60)

    print()

    # Check PyTorch

    try:

        import torch

        print(f"✓ PyTorch imported successfully")

        print(f"  Version: {torch.__version__}")

    except ImportError as e:

        print(f"✗ PyTorch import failed: {e}")

        sys.exit(1)

    print()

    # Check CUDA availability

    cuda_available = torch.cuda.is_available()

    print(f"CUDA Available: {'✓ YES' if cuda_available else '✗ NO'}")

    if not cuda_available:
        print()

        print("⚠️  CUDA is not available. Possible reasons:")

        print("   1. No NVIDIA GPU")

        print("   2. NVIDIA drivers not installed")

        print("   3. PyTorch built without CUDA support")

        print("   4. CUDA_VISIBLE_DEVICES set to empty")

        print()

        print("Run: nvidia-smi")

        print("To check if GPU and drivers are working")

        sys.exit(1)

    print()

    # CUDA details

    print("CUDA Configuration:")

    print(f"  CUDA Version (PyTorch): {torch.version.cuda}")

    try:

        print(f"  cuDNN Version: {torch.backends.cudnn.version()}")

        print(f"  cuDNN Enabled: {torch.backends.cudnn.enabled}")

    except:

        print(f"  cuDNN: Not available")

    print()

    # GPU information

    device_count = torch.cuda.device_count()

    print(f"GPU Devices: {device_count}")

    print()

    for i in range(device_count):

        props = torch.cuda.get_device_properties(i)

        print(f"GPU {i}: {props.name}")

        print(f"  Compute Capability: {props.major}.{props.minor}")

        print(f"  Total Memory: {props.total_memory / 1024 ** 3:.2f} GB")

        print(f"  Multi Processors: {props.multi_processor_count}")

        # Check compute capability compatibility

        compute_capability = float(f"{props.major}.{props.minor}")

        if compute_capability < 3.5:

            print(f"  ⚠️  WARNING: Compute capability {compute_capability} is very old")

            print(f"             PyTorch 2.x may not support this GPU")

        elif compute_capability < 6.0:

            print(f"  ⚠️  WARNING: Compute capability {compute_capability} is old")

            print(f"             Limited PyTorch 2.x support")

        else:

            print(f"  ✓  Compute capability {compute_capability} is supported")

        print()

    # Test CUDA operation

    print("Testing CUDA Operations:")

    try:

        # Simple tensor operation

        x = torch.randn(100, 100).cuda()

        y = torch.randn(100, 100).cuda()

        z = torch.matmul(x, y)

        print(f"  ✓ Basic tensor operations: PASSED")

        # Check if result is valid

        if torch.isnan(z).any():

            print(f"  ✗ Result contains NaN: FAILED")

        else:

            print(f"  ✓ Result validation: PASSED")

        # Cleanup

        del x, y, z

        torch.cuda.empty_cache()



    except RuntimeError as e:

        print(f"  ✗ CUDA operation FAILED:")

        print(f"    {str(e)}")

        print()

        print("⚠️  This is the error causing DPVO to fail!")

        print()

        print("Recommended fixes:")

        print("1. Check if PyTorch CUDA version matches nvidia-smi CUDA version")

        print("2. Reinstall PyTorch with correct CUDA version:")

        print("   pixi run -e dpvo pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118")

        print("   (Replace cu118 with your CUDA version: cu118, cu121, cu124)")

        print()

        sys.exit(1)

    print()

    print("=" * 60)

    print("✓ ALL CUDA CHECKS PASSED")

    print("=" * 60)

    print()

    print("DPVO should work with this configuration.")

    print()


if __name__ == "__main__":
    check_cuda()