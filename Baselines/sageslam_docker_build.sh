#!/bin/bash
# Build SAGE-SLAM Docker image and compile the C++ SLAM system inside it.
# Build artifacts are saved to the host via volume mount.
#
# Prerequisites:
#   - Docker with nvidia-container-toolkit (for GPU access)
#   - NVIDIA drivers installed on host
#
# Usage:
#   cd Baselines/SAGE-SLAM-DEV && bash ../../Baselines/sageslam_docker_build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAGE_DIR="${SCRIPT_DIR}/SAGE-SLAM-DEV"
IMAGE_NAME="vslamlab-sageslam"

if [ ! -d "$SAGE_DIR" ]; then
    echo "[SAGE-SLAM] Error: SAGE-SLAM-DEV directory not found at $SAGE_DIR"
    exit 1
fi

cd "$SAGE_DIR"

echo "=========================================="
echo " Building SAGE-SLAM Docker image..."
echo "=========================================="

docker build \
    --build-arg UID="$(id -u)" \
    --build-arg GID="$(id -g)" \
    --build-arg UNAME="$(whoami)" \
    --build-arg PW=vslamlab \
    -t "$IMAGE_NAME" \
    .

echo "=========================================="
echo " Cleaning stale build caches..."
echo "=========================================="

# Clean from host first (best effort)
rm -rf system/thirdparty/build_Release build 2>/dev/null || true
# Clean from Docker too (handles files owned by Docker user)
docker run --rm \
    -v "$(pwd)":"/home/$(whoami)" \
    -w "/home/$(whoami)" \
    "$IMAGE_NAME" \
    rm -rf system/thirdparty/build_Release build

echo "=========================================="
echo " Compiling SAGE-SLAM inside Docker..."
echo "=========================================="

docker run --rm --gpus all \
    -v "$(pwd)":"/home/$(whoami)" \
    -w "/home/$(whoami)" \
    "$IMAGE_NAME" \
    bash -c 'SLAM_BUILD_TYPE=Release && \
        bash system/thirdparty/makedeps_with_argument.sh $SLAM_BUILD_TYPE && \
        mkdir -p build/$SLAM_BUILD_TYPE && \
        cd build/$SLAM_BUILD_TYPE && \
        cmake -DCMAKE_BUILD_TYPE=$SLAM_BUILD_TYPE ../../system && \
        make -j4'

echo "=========================================="
echo " SAGE-SLAM Docker build complete."
echo " Binary: $SAGE_DIR/build/Release/bin/df_demo"
echo "=========================================="
