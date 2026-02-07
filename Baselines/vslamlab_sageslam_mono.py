"""VSLAMLAB wrapper for SAGE-SLAM monocular execution.

This script bridges the VSLAMLAB pipeline interface with SAGE-SLAM.
It should be placed in the SAGE-SLAM-DEV directory after cloning.

Usage (called by VSLAMLAB pipeline via pixi):
    python vslamlab_sageslam_mono.py --sequence_path <path> --calibration_yaml <path>
        --rgb_csv <path> --exp_folder <path> --exp_it <int> --settings_yaml <path>
        --verbose <int> --mode mono --enable_gui false
"""

import argparse
import csv
import os
import sys
import time
import yaml
import numpy as np

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
    # Handle OpenCV YAML format (%YAML:1.0)
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
        header = next(reader)
        for row in reader:
            timestamps.append(float(row[0]))
            image_paths.append(row[1])
    return timestamps, image_paths


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


def main():
    args = parse_args()

    if args.verbose > 0:
        print(f"[SAGE-SLAM] Running on sequence: {args.sequence_path}")

    # Read inputs
    fx, fy, cx, cy = read_calibration(args.calibration_yaml)
    timestamps, image_paths = read_rgb_csv(args.rgb_csv)

    # Resolve full image paths
    full_image_paths = [os.path.join(args.sequence_path, p) for p in image_paths]

    # Output trajectory path
    exp_it_str = str(args.exp_it).zfill(5)
    trajectory_output = os.path.join(args.exp_folder, f"{exp_it_str}_KeyFrameTrajectory.csv")

    start_time = time.time()

    try:
        # Import SAGE-SLAM components
        # SAGE-SLAM uses HDF5 input; we need to create a temporary HDF5 or
        # use the image-based interface if available
        import cv2

        # Try importing SAGE-SLAM's core module
        try:
            from sage_slam import SageSLAM
            slam = SageSLAM(fx=fx, fy=fy, cx=cx, cy=cy, enable_gui=(args.enable_gui == 'true'))

            trajectory = []
            tracked_timestamps = []

            for i, (ts, img_path) in enumerate(zip(timestamps, full_image_paths)):
                if not os.path.exists(img_path):
                    continue
                image = cv2.imread(img_path)
                if image is None:
                    continue

                pose = slam.process_frame(image, ts)
                if pose is not None:
                    trajectory.append(pose)
                    tracked_timestamps.append(ts)

                if args.verbose > 0 and (i + 1) % 50 == 0:
                    print(f"[SAGE-SLAM] Processed {i + 1}/{len(timestamps)} frames")

            slam.shutdown()
            write_trajectory_csv(trajectory, tracked_timestamps, trajectory_output)

        except ImportError:
            # Fallback: run SAGE-SLAM via command-line interface
            print("[SAGE-SLAM] Python API not available, using CLI fallback")

            # Build SAGE-SLAM command
            sage_cmd = _build_sage_cli_command(args, fx, fy, cx, cy, full_image_paths)
            import subprocess
            result = subprocess.run(sage_cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"[SAGE-SLAM] CLI execution failed: {result.stderr}")
                sys.exit(1)

            # Convert SAGE-SLAM output to VSLAMLAB format
            _convert_sage_output(args.exp_folder, exp_it_str, timestamps)

    except Exception as e:
        print(f"[SAGE-SLAM] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start_time
    if args.verbose > 0:
        print(f"[SAGE-SLAM] Completed in {elapsed:.2f}s")
        if os.path.exists(trajectory_output):
            with open(trajectory_output, 'r') as f:
                n_poses = sum(1 for _ in f) - 1
            print(f"[SAGE-SLAM] Tracked {n_poses}/{len(timestamps)} frames")


def _build_sage_cli_command(args, fx, fy, cx, cy, image_paths):
    """Build SAGE-SLAM CLI command as fallback."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(script_dir, 'build', 'Release')
    executable = os.path.join(build_dir, 'bin', 'df_demo')

    if not os.path.exists(executable):
        raise FileNotFoundError(f"SAGE-SLAM executable not found: {executable}")

    cmd = (f"LD_LIBRARY_PATH={script_dir}/system/thirdparty/install_Release/lib:$LD_LIBRARY_PATH "
           f"MESA_GL_VERSION_OVERRIDE=3.3 "
           f"{executable} "
           f"--flagfile {script_dir}/system/configs/slam_run.flags "
           f"--enable_gui=false "
           f"--v=0")
    return cmd


def _convert_sage_output(exp_folder, exp_it_str, timestamps):
    """Convert SAGE-SLAM native output to VSLAMLAB trajectory CSV."""
    # SAGE-SLAM outputs poses in its own format; convert to VSLAMLAB CSV
    trajectory_output = os.path.join(exp_folder, f"{exp_it_str}_KeyFrameTrajectory.csv")
    sage_output_dir = os.path.join(exp_folder, 'sage_output')

    if not os.path.exists(sage_output_dir):
        print("[SAGE-SLAM] No output directory found")
        return

    # Look for pose files
    pose_files = sorted([f for f in os.listdir(sage_output_dir) if 'pose' in f.lower()])
    if len(pose_files) == 0:
        return

    trajectory = []
    tracked_timestamps = []
    for i, pf in enumerate(pose_files):
        try:
            T = np.loadtxt(os.path.join(sage_output_dir, pf))
            if T.shape == (4, 4):
                trajectory.append(T)
                tracked_timestamps.append(timestamps[i] if i < len(timestamps) else float(i) / 30.0)
        except Exception:
            continue

    write_trajectory_csv(trajectory, tracked_timestamps, trajectory_output)


if __name__ == '__main__':
    main()
