import os
import csv
import yaml
import shutil
import numpy as np
from pathlib import Path

from Datasets.DatasetVSLAMLab import DatasetVSLAMLab
from utilities import downloadFile, decompressFile

SCRIPT_LABEL = f"\033[95m[{os.path.basename(__file__)}]\033[0m "


class C3VD_dataset(DatasetVSLAMLab):
    """C3VD: Colonoscopy 3D Video Dataset.

    22 video sequences captured with a clinical HD colonoscope on high-fidelity
    silicone colon phantoms.  Each sequence includes:
      - RGB frames
      - Depth maps (0-100 mm, 16-bit)
      - 6-DoF camera poses (ground truth from 2D-3D registration)
      - Surface normals, optical flow, occlusion maps, coverage maps
      - 3D mesh models (Wavefront OBJ)

    Reference:
        Bobrow et al., "Colonoscopy 3D video dataset with paired depth from
        2D-3D registration", Medical Image Analysis, 2023.
        https://durrlab.github.io/C3VD/
    """

    def __init__(self, benchmark_path):
        super().__init__('c3vd', benchmark_path)

        with open(self.yaml_file, 'r') as file:
            data = yaml.safe_load(file)

        self.url_download_root = data['url_download_root']
        self.sequence_nicknames = [s.replace('_', ' ') for s in self.sequence_names]

    def download_sequence_data(self, sequence_name):
        """Download C3VD sequence data.

        C3VD data is distributed via the project website.  Users may need to
        download manually and place in the benchmark directory.
        """
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        os.makedirs(sequence_path, exist_ok=True)

        # C3VD requires manual download from https://durrlab.github.io/C3VD/
        # Check if data already exists
        rgb_path = os.path.join(sequence_path, 'color')
        if not os.path.exists(rgb_path):
            alt_rgb = os.path.join(sequence_path, 'rgb')
            if not os.path.exists(alt_rgb):
                print(f"{SCRIPT_LABEL}C3VD data must be downloaded manually from {self.url_download_root}")
                print(f"{SCRIPT_LABEL}Place sequence '{sequence_name}' in: {sequence_path}")
                print(f"{SCRIPT_LABEL}Expected structure: {sequence_path}/color/ , {sequence_path}/depth/ , {sequence_path}/pose/")

    def create_rgb_folder(self, sequence_name):
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        rgb_0_path = os.path.join(sequence_path, 'rgb_0')

        # C3VD stores images in 'color/' folder
        color_path = os.path.join(sequence_path, 'color')
        if os.path.exists(color_path) and not os.path.exists(rgb_0_path):
            os.rename(color_path, rgb_0_path)

    def create_rgb_csv(self, sequence_name):
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        rgb_0_path = os.path.join(sequence_path, 'rgb_0')
        rgb_csv = os.path.join(sequence_path, 'rgb.csv')

        if not os.path.exists(rgb_0_path):
            return

        rgb_files = sorted([f for f in os.listdir(rgb_0_path)
                           if os.path.isfile(os.path.join(rgb_0_path, f))
                           and f.lower().endswith(('.png', '.jpg', '.jpeg'))])

        # Check for depth data
        depth_0_path = os.path.join(sequence_path, 'depth_0')
        has_depth = os.path.exists(depth_0_path)

        with open(rgb_csv, 'w', newline='') as file:
            writer = csv.writer(file)
            if has_depth:
                depth_files = sorted([f for f in os.listdir(depth_0_path)
                                     if os.path.isfile(os.path.join(depth_0_path, f))])
                writer.writerow(['ts_rgb0 (s)', 'path_rgb0', 'ts_depth0 (s)', 'path_depth0'])
                for iRGB, (rgb_file, depth_file) in enumerate(zip(rgb_files, depth_files)):
                    ts = float(iRGB) / self.rgb_hz
                    writer.writerow([f"{ts:.5f}", f"rgb_0/{rgb_file}", f"{ts:.5f}", f"depth_0/{depth_file}"])
            else:
                writer.writerow(['ts_rgb0 (s)', 'path_rgb0'])
                for iRGB, filename in enumerate(rgb_files):
                    ts = float(iRGB) / self.rgb_hz
                    writer.writerow([f"{ts:.5f}", f"rgb_0/{filename}"])

    def create_calibration_yaml(self, sequence_name):
        """Create calibration YAML from C3VD camera parameters.

        C3VD uses a clinical HD colonoscope with known intrinsics.
        Default parameters based on the C3VD dataset documentation.
        """
        sequence_path = os.path.join(self.dataset_path, sequence_name)

        # Try to read calibration from a metadata file if present
        calib_file = os.path.join(sequence_path, 'camera_params.txt')
        if os.path.exists(calib_file):
            with open(calib_file, 'r') as f:
                lines = f.readlines()
            fx, fy, cx, cy = 0, 0, 0, 0
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    if 'fx' in parts[0]:
                        fx = float(parts[1])
                    elif 'fy' in parts[0]:
                        fy = float(parts[1])
                    elif 'cx' in parts[0]:
                        cx = float(parts[1])
                    elif 'cy' in parts[0]:
                        cy = float(parts[1])
        else:
            # Default C3VD intrinsics (from dataset documentation)
            # 1920x1080 resolution colonoscope
            fx, fy = 1128.0, 1128.0
            cx, cy = 960.0, 540.0

        camera0 = {"model": "Pinhole", "fx": fx, "fy": fy, "cx": cx, "cy": cy}
        rgbd = {"depth0_factor": 1000.0}  # C3VD depth in mm, factor to convert to metres
        self.write_calibration_yaml(sequence_name=sequence_name, camera0=camera0, rgbd=rgbd)

    def create_groundtruth_csv(self, sequence_name):
        """Convert C3VD ground truth poses to VSLAMLAB CSV format.

        C3VD provides 6-DoF camera poses per frame.  The pose files contain
        4x4 transformation matrices (camera-to-world).
        """
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        pose_dir = os.path.join(sequence_path, 'pose')
        groundtruth_csv = os.path.join(sequence_path, 'groundtruth.csv')

        if not os.path.exists(pose_dir):
            return

        pose_files = sorted([f for f in os.listdir(pose_dir)
                            if f.endswith('.txt') or f.endswith('.npy')])
        if len(pose_files) == 0:
            return

        with open(groundtruth_csv, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['ts', 'tx', 'ty', 'tz', 'qx', 'qy', 'qz', 'qw'])

            for i, pose_file in enumerate(pose_files):
                ts = float(i) / self.rgb_hz
                pose_path = os.path.join(pose_dir, pose_file)

                try:
                    if pose_file.endswith('.npy'):
                        T = np.load(pose_path)
                    else:
                        T = np.loadtxt(pose_path)

                    if T.shape == (4, 4):
                        tx, ty, tz = T[0, 3], T[1, 3], T[2, 3]
                        R = T[:3, :3]
                        qw, qx, qy, qz = _rotation_matrix_to_quaternion(R)
                        writer.writerow([f"{ts:.5f}", f"{tx:.6f}", f"{ty:.6f}", f"{tz:.6f}",
                                        f"{qx:.6f}", f"{qy:.6f}", f"{qz:.6f}", f"{qw:.6f}"])
                except Exception:
                    continue

    def create_imu_csv(self, sequence_name):
        # C3VD does not include IMU data
        pass

    def create_depth_folder(self, sequence_name):
        """Rename C3VD depth folder to VSLAMLAB standard."""
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        depth_0_path = os.path.join(sequence_path, 'depth_0')
        depth_path = os.path.join(sequence_path, 'depth')
        if os.path.exists(depth_path) and not os.path.exists(depth_0_path):
            os.rename(depth_path, depth_0_path)

    def remove_unused_files(self, sequence_name):
        pass

    def download_process(self, sequence_name):
        """Override to also set up depth folder."""
        super().download_process(sequence_name)
        self.create_depth_folder(sequence_name)


def _rotation_matrix_to_quaternion(R):
    """Convert 3x3 rotation matrix to quaternion (w, x, y, z)."""
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return w, x, y, z
