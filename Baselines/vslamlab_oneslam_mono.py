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
import cv2
import numpy as np


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
    """Read camera intrinsics and distortion from VSLAMLAB calibration YAML."""
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
    w = calib.get('Camera0.w', calib.get('Camera0.width', calib.get('width', 640)))
    h = calib.get('Camera0.h', calib.get('Camera0.height', calib.get('height', 480)))

    # Read distortion coefficients (k1, k2, p1, p2, k3)
    k1 = calib.get('Camera0.k1', 0.0)
    k2 = calib.get('Camera0.k2', 0.0)
    p1 = calib.get('Camera0.p1', 0.0)
    p2 = calib.get('Camera0.p2', 0.0)
    k3 = calib.get('Camera0.k3', 0.0)
    dist_coeffs = np.array([k1, k2, p1, p2, k3])

    return fx, fy, cx, cy, w, h, dist_coeffs


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


def create_oneslam_data_dir(sequence_path, image_paths, fx, fy, cx, cy, w, h,
                            dist_coeffs, work_dir, verbose=0):
    """Create a data directory in OneSLAM's expected format.

    OneSLAM expects:
        data_root/
            images/
                00000000.jpg
                00000001.jpg
                ...
            calibration.json

    If distortion coefficients are non-zero, images are undistorted and
    intrinsics are updated to the optimal new camera matrix.
    """
    images_dir = os.path.join(work_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    has_distortion = np.any(np.abs(dist_coeffs) > 1e-8)

    # Pre-compute undistortion maps if needed
    new_fx, new_fy, new_cx, new_cy = fx, fy, cx, cy
    if has_distortion:
        camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
        new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
            camera_matrix, dist_coeffs, (int(w), int(h)), alpha=0.0)
        map1, map2 = cv2.initUndistortRectifyMap(
            camera_matrix, dist_coeffs, None, new_camera_matrix,
            (int(w), int(h)), cv2.CV_32FC1)
        new_fx = new_camera_matrix[0, 0]
        new_fy = new_camera_matrix[1, 1]
        new_cx = new_camera_matrix[0, 2]
        new_cy = new_camera_matrix[1, 2]
        if verbose > 0:
            print(f"[OneSLAM] Undistorting images: dist={dist_coeffs}")
            print(f"[OneSLAM] Original intrinsics: fx={fx:.1f} fy={fy:.1f} cx={cx:.1f} cy={cy:.1f}")
            print(f"[OneSLAM] New intrinsics: fx={new_fx:.1f} fy={new_fy:.1f} cx={new_cx:.1f} cy={new_cy:.1f}")

    for i, img_rel_path in enumerate(image_paths):
        src = os.path.join(sequence_path, img_rel_path)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(src)[1]
        dst = os.path.join(images_dir, f"{i:08d}{ext}")
        if os.path.exists(dst):
            continue

        if has_distortion:
            img = cv2.imread(src)
            undistorted = cv2.remap(img, map1, map2, cv2.INTER_LINEAR)
            cv2.imwrite(dst, undistorted)
        else:
            os.symlink(os.path.abspath(src), dst)

    # Create calibration.json for OneSLAM (pinhole, no distortion)
    calib = {
        "intrinsics": {
            "fx": new_fx,
            "fy": new_fy,
            "cx": new_cx,
            "cy": new_cy,
        },
        "model": "pinhole",
        "width": int(w),
        "height": int(h)
    }
    calib_path = os.path.join(work_dir, 'calibration.json')
    with open(calib_path, 'w') as f:
        json.dump(calib, f, indent=2)

    return work_dir


def smooth_trajectory(positions, smoothing_factor=None):
    """Fit a smoothing spline to the trajectory to remove noise."""
    from scipy.interpolate import UnivariateSpline
    n = len(positions)
    if n < 4:
        return positions
    t = np.arange(n, dtype=float)
    smoothed = np.copy(positions)
    if smoothing_factor is None:
        smoothing_factor = n * 0.5
    for dim in range(positions.shape[1]):
        spline = UnivariateSpline(t, positions[:, dim], s=smoothing_factor)
        smoothed[:, dim] = spline(t)
    return smoothed


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
                tum_poses[frame_idx] = [float(x) for x in parts[1:8]]

    # Sort by frame index and write raw poses (no smoothing)
    sorted_frames = sorted(tum_poses.keys())

    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ts', 'tx', 'ty', 'tz', 'qx', 'qy', 'qz', 'qw'])
        for frame_idx in sorted_frames:
            if frame_idx < len(timestamps):
                ts = timestamps[frame_idx]
            else:
                ts = float(frame_idx) / 30.0
            tx, ty, tz = tum_poses[frame_idx][0:3]
            qx, qy, qz, qw = tum_poses[frame_idx][3:7]
            writer.writerow([f"{ts:.5f}", tx, ty, tz, qx, qy, qz, qw])


def load_oneslam_settings(settings_yaml):
    """Load OneSLAM parameters from a settings YAML file.

    Returns a dict of parameter_name -> value. Missing keys use OneSLAM defaults.
    """
    defaults = {
        'lumen_mask_low_threshold': 0.05,
        'lumen_mask_high_threshold': 0.95,
        'ransac_localization': True,
        'update_localized_pose': False,
        'depth_scale': 3.0,
        'depth_estimator': 'constant',
        'keyframe_subsample': 4,
        'keyframe_decision': 'subsample',
        'section_length': 13,
        'past_frame_size': 5,
        'tracking_ba_iterations': 20,
        'local_ba_size': 10,
        'global_ba_iterations': 0,
        'point_sampler': 'uniform',
        'pose_guesser': 'last_pose',
        'tracked_point_num_min': 200,
        'tracked_point_num_max': 2000,
        'localization_track_num': 50,
        'minimum_new_points': 0,
        'point_resample_cooldown': 1,
        'cotracker_model': 'cotracker_stride_4_wind_8',
        'cotracker_window_size': 8,
        'img_width': -1,
        'img_height': -1,
    }
    if settings_yaml and os.path.exists(settings_yaml):
        with open(settings_yaml, 'r') as f:
            content = f.read()
        if content.startswith('%YAML'):
            content = '\n'.join(content.split('\n')[1:])
        user_settings = yaml.safe_load(content) or {}
        defaults.update(user_settings)
    return defaults


def build_oneslam_cmd(run_script, data_root, output_dir, settings):
    """Build the OneSLAM run_slam.py command from a settings dict."""
    cmd = (f"python {run_script} --data_root {data_root}"
           f" --output_folder {output_dir}"
           f" --lumen_mask_low_threshold {settings['lumen_mask_low_threshold']}"
           f" --lumen_mask_high_threshold {settings['lumen_mask_high_threshold']}"
           f" --depth_scale {settings['depth_scale']}"
           f" --depth_estimator {settings['depth_estimator']}"
           f" --keyframe_subsample {settings['keyframe_subsample']}"
           f" --keyframe_decision {settings['keyframe_decision']}"
           f" --section_length {settings['section_length']}"
           f" --past_frame_size {settings['past_frame_size']}"
           f" --tracking_ba_iterations {settings['tracking_ba_iterations']}"
           f" --local_ba_size {settings['local_ba_size']}"
           f" --global_ba_iterations {settings['global_ba_iterations']}"
           f" --point_sampler {settings['point_sampler']}"
           f" --pose_guesser {settings['pose_guesser']}"
           f" --tracked_point_num_min {settings['tracked_point_num_min']}"
           f" --tracked_point_num_max {settings['tracked_point_num_max']}"
           f" --localization_track_num {settings['localization_track_num']}"
           f" --minimum_new_points {settings['minimum_new_points']}"
           f" --point_resample_cooldown {settings['point_resample_cooldown']}"
           f" --cotracker_model {settings['cotracker_model']}"
           f" --cotracker_window_size {settings['cotracker_window_size']}")
    if settings.get('img_width', -1) > 0:
        cmd += f" --img_width {settings['img_width']}"
    if settings.get('img_height', -1) > 0:
        cmd += f" --img_height {settings['img_height']}"
    if settings.get('ransac_localization', False):
        cmd += " --ransac_localization"
    if settings.get('update_localized_pose', False):
        cmd += " --update_localized_pose"
    return cmd


def main():
    args = parse_args()

    if args.verbose > 0:
        print(f"[OneSLAM] Running on sequence: {args.sequence_path}")

    # Load OneSLAM settings from settings_yaml (or use defaults)
    settings = load_oneslam_settings(args.settings_yaml)
    if args.verbose > 0:
        print(f"[OneSLAM] Settings: {settings}")

    # Read inputs
    fx, fy, cx, cy, w, h, dist_coeffs = read_calibration(args.calibration_yaml)
    timestamps, image_paths = read_rgb_csv(args.rgb_csv)

    # Output trajectory path
    exp_it_str = str(args.exp_it).zfill(5)
    trajectory_output = os.path.join(args.exp_folder, f"{exp_it_str}_KeyFrameTrajectory.csv")

    # Create temporary working directory in OneSLAM's expected format
    work_dir = os.path.join(args.exp_folder, f'oneslam_work_{exp_it_str}')
    # Output directory MUST be separate from data_root to avoid recursive
    # copy in slam.save_data() (copytree of data_root into exp_root/dataset/)
    output_dir = os.path.join(args.exp_folder, f'oneslam_output_{exp_it_str}')
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        data_root = create_oneslam_data_dir(
            args.sequence_path, image_paths, fx, fy, cx, cy, w, h,
            dist_coeffs, work_dir, verbose=args.verbose
        )

        start_time = time.time()

        # Run OneSLAM via subprocess
        # NOTE: run_slam.py has module-level argparse (no __name__ guard),
        # so it cannot be imported — always use subprocess.
        if args.verbose > 0:
            print("[OneSLAM] Using CLI interface")
        import subprocess
        script_dir = os.path.dirname(os.path.abspath(__file__))
        run_script = os.path.join(script_dir, 'run_slam.py')

        if not os.path.exists(run_script):
            print(f"[OneSLAM] run_slam.py not found at {run_script}")
            sys.exit(1)

        cmd = build_oneslam_cmd(run_script, data_root, output_dir, settings)
        if args.verbose > 0:
            print(f"[OneSLAM] Command: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if args.verbose > 0:
            if result.stdout:
                print(result.stdout[-2000:])

        elapsed = time.time() - start_time

        # Save full debug output for diagnosis
        debug_log = os.path.join(args.exp_folder, f'oneslam_debug_{exp_it_str}.log')
        with open(debug_log, 'w') as dbg:
            dbg.write(f"=== STDOUT ===\n{result.stdout}\n")
            dbg.write(f"=== STDERR ===\n{result.stderr}\n")
            dbg.write(f"=== RETURN CODE: {result.returncode} ===\n")

        if result.returncode != 0:
            print(f"[OneSLAM] Warning: process exited with code {result.returncode}")
            print(f"[OneSLAM] Last stderr: {result.stderr[-500:]}")
            print(f"[OneSLAM] Full debug log: {debug_log}")

        # Find OneSLAM output poses (search even if returncode != 0,
        # as OneSLAM may complete the main loop but crash during cleanup)
        poses_pred = None
        for search_dir in [output_dir, work_dir, os.path.join(work_dir, 'experiments'), '.']:
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
            # Save raw poses for debugging
            import shutil as _shutil
            _shutil.copy2(poses_pred, os.path.join(args.exp_folder, 'poses_pred_raw.txt'))
            convert_tum_to_vslamlab_csv(poses_pred, timestamps, trajectory_output)
            if args.verbose > 0:
                with open(trajectory_output, 'r') as f:
                    n_poses = sum(1 for _ in f) - 1
                print(f"[OneSLAM] Completed in {elapsed:.2f}s, tracked {n_poses}/{len(timestamps)} frames")
        else:
            print("[OneSLAM] No output poses found")
            sys.exit(1)

    finally:
        # Clean up working directories
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
