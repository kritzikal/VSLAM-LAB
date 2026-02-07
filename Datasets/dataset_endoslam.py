import os
import csv
import yaml
import numpy as np
from pathlib import Path

from Datasets.DatasetVSLAMLab import DatasetVSLAMLab

SCRIPT_LABEL = f"\033[95m[{os.path.basename(__file__)}]\033[0m "


class ENDOSLAM_dataset(DatasetVSLAMLab):
    """EndoSLAM Dataset for endoscopic SLAM benchmarking.

    35 sub-datasets from 8 ex-vivo porcine GI-tract organs with ground truth
    6-DoF poses recorded by a Franka Emika Panda robotic arm (0.1 mm repeatability)
    and high-precision 3D surface models from 3D scanners.

    Reference:
        Ozyoruk et al., "EndoSLAM dataset and an unsupervised monocular visual
        odometry and depth estimation approach for endoscopic videos", Medical
        Image Analysis, 2021.
        https://github.com/CapsuleEndoscope/EndoSLAM
    """

    def __init__(self, benchmark_path):
        super().__init__('endoslam', benchmark_path)

        with open(self.yaml_file, 'r') as file:
            data = yaml.safe_load(file)

        self.url_download_root = data['url_download_root']
        self.sequence_nicknames = [s.replace('_', ' ').replace('HighCam', 'HC')
                                   .replace('Traj', 'T').replace('Colon', 'Col')
                                   .replace('SmallIntestine', 'SI')
                                   .replace('Stomach', 'Sto')
                                   for s in self.sequence_names]

    def download_sequence_data(self, sequence_name):
        """Download EndoSLAM sequence data.

        EndoSLAM data is hosted on Mendeley Data.  The download requires
        manual steps; users must place data in the benchmark directory.
        """
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        os.makedirs(sequence_path, exist_ok=True)

        # Check if data already exists
        images_path = os.path.join(sequence_path, 'Frames')
        if not os.path.exists(images_path):
            alt_path = os.path.join(sequence_path, 'rgb_0')
            if not os.path.exists(alt_path):
                print(f"{SCRIPT_LABEL}EndoSLAM data must be downloaded manually from:")
                print(f"{SCRIPT_LABEL}  {self.url_download_root}")
                print(f"{SCRIPT_LABEL}Place sequence '{sequence_name}' in: {sequence_path}")
                print(f"{SCRIPT_LABEL}Expected structure: {sequence_path}/Frames/ and {sequence_path}/Poses/")

    def create_rgb_folder(self, sequence_name):
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        rgb_0_path = os.path.join(sequence_path, 'rgb_0')

        # EndoSLAM stores images in 'Frames/' folder
        frames_path = os.path.join(sequence_path, 'Frames')
        if os.path.exists(frames_path) and not os.path.exists(rgb_0_path):
            os.rename(frames_path, rgb_0_path)

    def create_rgb_csv(self, sequence_name):
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        rgb_0_path = os.path.join(sequence_path, 'rgb_0')
        rgb_csv = os.path.join(sequence_path, 'rgb.csv')

        if not os.path.exists(rgb_0_path):
            return

        rgb_files = sorted([f for f in os.listdir(rgb_0_path)
                           if os.path.isfile(os.path.join(rgb_0_path, f))
                           and f.lower().endswith(('.png', '.jpg', '.jpeg'))])

        with open(rgb_csv, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['ts_rgb0 (s)', 'path_rgb0'])
            for iRGB, filename in enumerate(rgb_files):
                ts = float(iRGB) / self.rgb_hz
                writer.writerow([f"{ts:.5f}", f"rgb_0/{filename}"])

    def create_calibration_yaml(self, sequence_name):
        """Create calibration YAML from EndoSLAM camera parameters.

        EndoSLAM uses several cameras; HighCam is 720p HD endoscope camera.
        Default intrinsics are based on the dataset documentation.
        """
        sequence_path = os.path.join(self.dataset_path, sequence_name)

        # Try reading a calibration file if available
        calib_file = os.path.join(sequence_path, 'calibration.txt')
        if os.path.exists(calib_file):
            with open(calib_file, 'r') as f:
                lines = f.readlines()
            vals = lines[0].strip().split()
            if len(vals) >= 4:
                fx, fy, cx, cy = float(vals[0]), float(vals[1]), float(vals[2]), float(vals[3])
            else:
                fx, fy = 284.5, 284.5
                cx, cy = 426.0, 240.0
        else:
            # Default HighCam intrinsics (720p: 852x480)
            fx, fy = 284.5, 284.5
            cx, cy = 426.0, 240.0

        camera0 = {"model": "Pinhole", "fx": fx, "fy": fy, "cx": cx, "cy": cy}
        self.write_calibration_yaml(sequence_name=sequence_name, camera0=camera0)

    def create_groundtruth_csv(self, sequence_name):
        """Convert EndoSLAM ground truth poses to VSLAMLAB CSV format.

        EndoSLAM ground truth poses are recorded by a Franka Emika Panda
        robotic arm at 1 kHz.  Pose files contain 4x4 transformation matrices.
        """
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        groundtruth_csv = os.path.join(sequence_path, 'groundtruth.csv')

        # EndoSLAM stores poses in various formats; try common ones
        pose_dir = os.path.join(sequence_path, 'Poses')
        pose_file_txt = os.path.join(sequence_path, 'groundtruth.txt')
        pose_file_npy = os.path.join(sequence_path, 'poses.npy')

        if os.path.exists(pose_file_npy):
            poses = np.load(pose_file_npy)
            self._write_poses_from_array(poses, groundtruth_csv)
        elif os.path.exists(pose_file_txt):
            self._convert_tum_to_csv(pose_file_txt, groundtruth_csv)
        elif os.path.exists(pose_dir):
            self._convert_pose_dir_to_csv(pose_dir, groundtruth_csv)

    def _write_poses_from_array(self, poses, groundtruth_csv):
        """Write poses from numpy array of 4x4 matrices."""
        with open(groundtruth_csv, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['ts', 'tx', 'ty', 'tz', 'qx', 'qy', 'qz', 'qw'])
            for i in range(poses.shape[0]):
                T = poses[i]
                ts = float(i) / self.rgb_hz
                tx, ty, tz = T[0, 3], T[1, 3], T[2, 3]
                R = T[:3, :3]
                qw, qx, qy, qz = _rotation_matrix_to_quaternion(R)
                writer.writerow([f"{ts:.5f}", f"{tx:.6f}", f"{ty:.6f}", f"{tz:.6f}",
                                f"{qx:.6f}", f"{qy:.6f}", f"{qz:.6f}", f"{qw:.6f}"])

    def _convert_tum_to_csv(self, tum_file, groundtruth_csv):
        """Convert TUM-format ground truth to VSLAMLAB CSV."""
        with open(tum_file, 'r') as fin, open(groundtruth_csv, 'w', newline='') as fout:
            writer = csv.writer(fout)
            writer.writerow(['ts', 'tx', 'ty', 'tz', 'qx', 'qy', 'qz', 'qw'])
            for line in fin:
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                writer.writerow(s.split())

    def _convert_pose_dir_to_csv(self, pose_dir, groundtruth_csv):
        """Convert directory of pose files to VSLAMLAB CSV."""
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
        # EndoSLAM does not include IMU data
        pass

    def remove_unused_files(self, sequence_name):
        pass


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
