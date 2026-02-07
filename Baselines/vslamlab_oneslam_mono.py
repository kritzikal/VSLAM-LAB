"""VSLAMLAB wrapper for OneSLAM monocular execution.

This script bridges the VSLAMLAB pipeline interface with OneSLAM.
It should be placed in the OneSLAM-DEV directory after cloning.

OneSLAM expects:
    - images/ directory with numbered frames (00000000.jpg, ...)
    - calibration.json with pinhole intrinsics
    - optional mask.bmp
    - optional poses_gt.txt (TUM format)

Output:
    - poses_pred.txt (TUM format: ts tx ty tz qx qy qz qw)

Usage (called by VSLAMLAB pipeline via pixi):
    python vslamlab_oneslam_mono.py --sequence_path <path> --calibration_yaml <path>
        --rgb_csv <path> --exp_folder <path> --exp_it <int> --settings_yaml <path>
        --verbose <int> --mode mono
"""

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import time
import yaml


def parse_args():
    parser = argparse.ArgumentParser(description='VSLAMLAB OneSLAM mono wrapper')
    parser.add_argument('--sequence_path', type=str, required=True)
    parser.add_argument('--calibration_yaml', type=str, required=True)
    parser.add_argument('--rgb_csv', type=str, required=True)
    parser.add_argument('--exp_folder', type=str, required=True)
    parser.add_argument('--exp_it', type=int, required=True)
    parser.add_argument('--settings_yaml', type=str, default='')
    parser.add_argument('--verbose', type=int, default=1)
    parser.add_argument('--mode', type=str, default='mono')
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
    w = calib.get('Camera0.width', calib.get('width', 640))
    h = calib.get('Camera0.height', calib.get('height', 480))
    return fx, fy, cx, cy, w, h


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


def create_oneslam_data_dir(sequence_path, image_paths, fx, fy, cx, cy, w, h, work_dir):
    """Create a data directory in OneSLAM's expected format.

    OneSLAM expects:
        data_root/
            images/
                00000000.jpg
                00000001.jpg
                ...
            calibration.json
    """
    images_dir = os.path.join(work_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    # Symlink or copy images with OneSLAM naming convention
    for i, img_rel_path in enumerate(image_paths):
        src = os.path.join(sequence_path, img_rel_path)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(src)[1]
        dst = os.path.join(images_dir, f"{i:08d}{ext}")
        if not os.path.exists(dst):
            os.symlink(os.path.abspath(src), dst)

    # Create calibration.json for OneSLAM (pinhole, no distortion)
    calib = {
        "model": "pinhole",
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        "width": int(w),
        "height": int(h)
    }
    calib_path = os.path.join(work_dir, 'calibration.json')
    with open(calib_path, 'w') as f:
        json.dump(calib, f, indent=2)

    return work_dir


def convert_tum_to_vslamlab_csv(tum_file, timestamps, output_csv):
    """Convert OneSLAM TUM-format output to VSLAMLAB CSV format."""
    # Read TUM format: ts tx ty tz qx qy qz qw
    tum_poses = {}
    with open(tum_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 8:
                frame_idx = int(float(parts[0]))
                tum_poses[frame_idx] = parts[1:8]

    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ts', 'tx', 'ty', 'tz', 'qx', 'qy', 'qz', 'qw'])
        for frame_idx, pose_parts in sorted(tum_poses.items()):
            if frame_idx < len(timestamps):
                ts = timestamps[frame_idx]
            else:
                ts = float(frame_idx) / 30.0
            tx, ty, tz = pose_parts[0], pose_parts[1], pose_parts[2]
            qx, qy, qz, qw = pose_parts[3], pose_parts[4], pose_parts[5], pose_parts[6]
            writer.writerow([f"{ts:.5f}", tx, ty, tz, qx, qy, qz, qw])


def main():
    args = parse_args()

    if args.verbose > 0:
        print(f"[OneSLAM] Running on sequence: {args.sequence_path}")

    # Read inputs
    fx, fy, cx, cy, w, h = read_calibration(args.calibration_yaml)
    timestamps, image_paths = read_rgb_csv(args.rgb_csv)

    # Output trajectory path
    exp_it_str = str(args.exp_it).zfill(5)
    trajectory_output = os.path.join(args.exp_folder, f"{exp_it_str}_KeyFrameTrajectory.csv")

    # Create temporary working directory in OneSLAM's expected format
    work_dir = os.path.join(args.exp_folder, f'oneslam_work_{exp_it_str}')
    os.makedirs(work_dir, exist_ok=True)

    try:
        data_root = create_oneslam_data_dir(
            args.sequence_path, image_paths, fx, fy, cx, cy, w, h, work_dir
        )

        start_time = time.time()

        # Try importing OneSLAM directly
        try:
            from run_slam import run_slam as oneslam_run
            if args.verbose > 0:
                print("[OneSLAM] Using Python API")
            oneslam_run(data_root=data_root)
        except ImportError:
            # Fallback: run OneSLAM via subprocess
            if args.verbose > 0:
                print("[OneSLAM] Using CLI interface")
            import subprocess
            script_dir = os.path.dirname(os.path.abspath(__file__))
            run_script = os.path.join(script_dir, 'run_slam.py')

            if not os.path.exists(run_script):
                print(f"[OneSLAM] run_slam.py not found at {run_script}")
                sys.exit(1)

            cmd = f"python {run_script} --data_root {data_root}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if args.verbose > 0:
                if result.stdout:
                    print(result.stdout[-500:])
            if result.returncode != 0:
                print(f"[OneSLAM] Execution failed: {result.stderr[-500:]}")
                sys.exit(1)

        elapsed = time.time() - start_time

        # Find OneSLAM output poses
        # OneSLAM saves results in experiments/TIMESTAMP/ or in the data_root
        poses_pred = None
        for search_dir in [work_dir, os.path.join(work_dir, 'experiments'), '.']:
            if os.path.isdir(search_dir):
                for root, dirs, files in os.walk(search_dir):
                    for fname in files:
                        if fname == 'poses_pred.txt':
                            poses_pred = os.path.join(root, fname)
                            break
                    if poses_pred:
                        break
            if poses_pred:
                break

        if poses_pred and os.path.exists(poses_pred):
            convert_tum_to_vslamlab_csv(poses_pred, timestamps, trajectory_output)
            if args.verbose > 0:
                with open(trajectory_output, 'r') as f:
                    n_poses = sum(1 for _ in f) - 1
                print(f"[OneSLAM] Completed in {elapsed:.2f}s, tracked {n_poses}/{len(timestamps)} frames")
        else:
            print("[OneSLAM] No output poses found")
            sys.exit(1)

    finally:
        # Clean up working directory (keep symlinks lightweight)
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
