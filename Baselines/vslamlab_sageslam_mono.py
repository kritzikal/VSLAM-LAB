"""VSLAMLAB wrapper for SAGE-SLAM monocular execution via Docker.

This script bridges the VSLAMLAB pipeline interface with SAGE-SLAM.
It converts VSLAMLAB input (images + calibration) to SAGE-SLAM's HDF5
format, runs SAGE-SLAM inside Docker, and converts output poses back
to VSLAMLAB's trajectory CSV format.

Prerequisites:
    - Docker image 'vslamlab-sageslam' built via sageslam_docker_build.sh
    - nvidia-container-toolkit for GPU access inside Docker

Usage (called by VSLAMLAB pipeline via pixi):
    python vslamlab_sageslam_mono.py --sequence_path <path> --calibration_yaml <path>
        --rgb_csv <path> --exp_folder <path> --exp_it <int>
        --verbose <int> --mode mono --enable_gui false
"""

import argparse
import csv
import os
import subprocess
import sys
import tempfile
import time
import yaml
import numpy as np

DOCKER_IMAGE = 'vslamlab-sageslam'


def parse_args():
    parser = argparse.ArgumentParser(description='VSLAMLAB SAGE-SLAM mono wrapper')
    parser.add_argument('--sequence_path', type=str, required=True)
    parser.add_argument('--calibration_yaml', type=str, required=True)
    parser.add_argument('--rgb_csv', type=str, required=True)
    parser.add_argument('--exp_folder', type=str, required=True)
    parser.add_argument('--exp_it', type=int, required=True)
    parser.add_argument('--settings_yaml', type=str, default='')
    parser.add_argument('--verbose', type=int, default=1)
    parser.add_argument('--mode', type=str, default='mono')
    parser.add_argument('--enable_gui', type=str, default='false')
    return parser.parse_args()


def read_calibration(calibration_yaml):
    """Read camera intrinsics from VSLAMLAB calibration YAML."""
    with open(calibration_yaml, 'r') as f:
        content = f.read()
    if content.startswith('%YAML'):
        content = '\n'.join(content.split('\n')[1:])
    calib = yaml.safe_load(content)
    fx = calib.get('Camera0.fx', calib.get('fx', 500.0))
    fy = calib.get('Camera0.fy', calib.get('fy', 500.0))
    cx = calib.get('Camera0.cx', calib.get('cx', 320.0))
    cy = calib.get('Camera0.cy', calib.get('cy', 240.0))
    return fx, fy, cx, cy


def read_rgb_csv(rgb_csv):
    """Read the RGB image list CSV."""
    timestamps = []
    image_paths = []
    with open(rgb_csv, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            timestamps.append(float(row[0]))
            image_paths.append(row[1])
    return timestamps, image_paths


def create_hdf5_from_images(image_paths, sequence_path, fx, fy, cx, cy, output_path,
                            target_width=640, verbose=0):
    """Convert VSLAMLAB images + calibration to SAGE-SLAM HDF5 format.

    Images are resized to target_width (preserving aspect ratio) to match
    SAGE-SLAM's expected input scale. Intrinsics are adjusted accordingly.

    SAGE-SLAM expects HDF5 with:
      - "color":      [N, H, W, 3] uint8
      - "mask":       [1, H, W, 1] uint8 (applied uniformly)
      - "intrinsics": [1, 3, 3] float32
    """
    import cv2
    import h5py

    # Read first image to get original dimensions
    first_img_path = os.path.join(sequence_path, image_paths[0])
    first_img = cv2.imread(first_img_path)
    if first_img is None:
        raise RuntimeError(f"Cannot read first image: {first_img_path}")
    orig_h, orig_w = first_img.shape[:2]

    # Compute resize scale
    scale = target_width / orig_w
    w = target_width
    h = int(orig_h * scale)
    scaled_fx = fx * scale
    scaled_fy = fy * scale
    scaled_cx = cx * scale
    scaled_cy = cy * scale

    if verbose > 0:
        print(f"[SAGE-SLAM] Resizing {orig_w}x{orig_h} -> {w}x{h} (scale={scale:.3f})")

    with h5py.File(output_path, 'w') as hf:
        # Create color dataset
        color_ds = hf.create_dataset('color', shape=(len(image_paths), h, w, 3),
                                     dtype=np.uint8, chunks=(1, h, w, 3))
        for i, img_rel in enumerate(image_paths):
            img_path = os.path.join(sequence_path, img_rel)
            img = cv2.imread(img_path)
            if img is not None:
                img_resized = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
                color_ds[i] = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)

        # Create mask (all ones = no masking)
        mask = np.ones((1, h, w, 1), dtype=np.uint8) * 255
        hf.create_dataset('mask', data=mask)

        # Create intrinsics [1, 3, 3]
        # SAGE-SLAM reads flattened: data[0]=fx, data[4]=fy, data[2]=cx, data[5]=cy
        # K[0,1]=width, K[1,0]=height
        K = np.zeros((1, 3, 3), dtype=np.float32)
        K[0, 0, 0] = scaled_fx   # index 0
        K[0, 0, 1] = w           # index 1 (width)
        K[0, 0, 2] = scaled_cx   # index 2
        K[0, 1, 0] = h           # index 3 (height)
        K[0, 1, 1] = scaled_fy   # index 4
        K[0, 1, 2] = scaled_cy   # index 5
        hf.create_dataset('intrinsics', data=K)

    return h, w


def rotation_matrix_to_quaternion(R):
    """Convert 3x3 rotation matrix to quaternion (qw, qx, qy, qz)."""
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (R[2, 1] - R[1, 2]) * s
        qy = (R[0, 2] - R[2, 0]) * s
        qz = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        qw = (R[2, 1] - R[1, 2]) / s
        qx = 0.25 * s
        qy = (R[0, 1] + R[1, 0]) / s
        qz = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        qw = (R[0, 2] - R[2, 0]) / s
        qx = (R[0, 1] + R[1, 0]) / s
        qy = 0.25 * s
        qz = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        qw = (R[1, 0] - R[0, 1]) / s
        qx = (R[0, 2] + R[2, 0]) / s
        qy = (R[1, 2] + R[2, 1]) / s
        qz = 0.25 * s
    return qw, qx, qy, qz


def write_trajectory_csv(trajectory, timestamps, output_path):
    """Write trajectory in VSLAMLAB CSV format."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ts', 'tx', 'ty', 'tz', 'qx', 'qy', 'qz', 'qw'])
        for ts, pose in zip(timestamps, trajectory):
            if pose is not None:
                tx, ty, tz = pose[0, 3], pose[1, 3], pose[2, 3]
                R = pose[:3, :3]
                qw, qx, qy, qz = rotation_matrix_to_quaternion(R)
                writer.writerow([f"{ts:.5f}", f"{tx:.6f}", f"{ty:.6f}", f"{tz:.6f}",
                                f"{qx:.6f}", f"{qy:.6f}", f"{qz:.6f}", f"{qw:.6f}"])


def parse_sage_output(log_dir):
    """Parse SAGE-SLAM output poses from the run log directory.

    SAGE-SLAM writes keyframe poses to the run log directory.
    """
    trajectory = []
    pose_dir = os.path.join(log_dir, 'poses')
    if not os.path.isdir(pose_dir):
        # Try looking for pose files directly in log_dir
        pose_dir = log_dir

    pose_files = sorted([f for f in os.listdir(pose_dir)
                         if f.endswith('.txt') or f.endswith('.npy')])

    for pf in pose_files:
        try:
            fpath = os.path.join(pose_dir, pf)
            if pf.endswith('.npy'):
                T = np.load(fpath)
            else:
                T = np.loadtxt(fpath)
            if T.shape == (4, 4):
                trajectory.append(T)
        except Exception:
            continue

    return trajectory


def main():
    args = parse_args()

    if args.verbose > 0:
        print(f"[SAGE-SLAM] Running on sequence: {args.sequence_path}")

    # Check Docker image exists
    check = subprocess.run(['docker', 'image', 'inspect', DOCKER_IMAGE],
                           capture_output=True)
    if check.returncode != 0:
        print(f"[SAGE-SLAM] Docker image '{DOCKER_IMAGE}' not found.")
        print(f"[SAGE-SLAM] Build it with: bash Baselines/sageslam_docker_build.sh")
        sys.exit(1)

    # Read inputs
    fx, fy, cx, cy = read_calibration(args.calibration_yaml)
    timestamps, image_paths = read_rgb_csv(args.rgb_csv)

    # Output trajectory path
    exp_it_str = str(args.exp_it).zfill(5)
    trajectory_output = os.path.join(args.exp_folder, f"{exp_it_str}_KeyFrameTrajectory.csv")

    start_time = time.time()

    # Create temporary working directory for Docker
    with tempfile.TemporaryDirectory(prefix='sageslam_') as tmpdir:
        # Create HDF5 from VSLAMLAB images
        hdf5_path = os.path.join(tmpdir, 'input_data.hdf5')
        if args.verbose > 0:
            print(f"[SAGE-SLAM] Creating HDF5 from {len(image_paths)} images...")
        create_hdf5_from_images(image_paths, args.sequence_path, fx, fy, cx, cy, hdf5_path,
                                verbose=args.verbose)

        # Create output directory inside tmpdir
        output_dir = os.path.join(tmpdir, 'output')
        os.makedirs(output_dir, exist_ok=True)

        # Get SAGE-SLAM directory (where this script lives)
        sage_dir = os.path.dirname(os.path.abspath(__file__))
        username = os.environ.get('USER', 'user')
        home_in_container = f'/home/{username}'

        # Build Docker run command
        docker_cmd = [
            'docker', 'run', '--rm', '--gpus', 'all',
            '-v', f'{sage_dir}:{home_in_container}',
            '-v', f'{tmpdir}:/data',
            '-w', home_in_container,
            '-e', 'MESA_GL_VERSION_OVERRIDE=3.3',
            DOCKER_IMAGE,
            'bash', '-c',
            (f'LD_LIBRARY_PATH={home_in_container}/system/thirdparty/install_Release/lib:$LD_LIBRARY_PATH '
             f'{home_in_container}/build/Release/bin/df_demo '
             f'--flagfile {home_in_container}/system/configs/slam_run.flags '
             f'--source_url=hdf5:///data/input_data.hdf5 '
             f'--run_log_dir=/data/output '
             f'--run_dir_name=run '
             f'--enable_gui=false '
             f'--quit_on_finish=true '
             f'--v={min(args.verbose, 1)}')
        ]

        if args.verbose > 0:
            print(f"[SAGE-SLAM] Running Docker container...")

        result = subprocess.run(docker_cmd, capture_output=not bool(args.verbose))

        if result.returncode != 0:
            print(f"[SAGE-SLAM] Docker execution failed (exit code {result.returncode})")
            if result.stderr:
                print(result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr)
            sys.exit(1)

        # Parse output poses
        run_output_dir = os.path.join(output_dir, 'run')
        if os.path.isdir(run_output_dir):
            trajectory = parse_sage_output(run_output_dir)
        else:
            trajectory = parse_sage_output(output_dir)

        # Write trajectory CSV
        if len(trajectory) > 0:
            tracked_timestamps = timestamps[:len(trajectory)]
            write_trajectory_csv(trajectory, tracked_timestamps, trajectory_output)
        else:
            print("[SAGE-SLAM] Warning: No poses recovered from output")

    elapsed = time.time() - start_time
    if args.verbose > 0:
        print(f"[SAGE-SLAM] Completed in {elapsed:.2f}s")
        if os.path.exists(trajectory_output):
            with open(trajectory_output, 'r') as f:
                n_poses = sum(1 for _ in f) - 1
            print(f"[SAGE-SLAM] Tracked {n_poses}/{len(timestamps)} frames")


if __name__ == '__main__':
    main()
