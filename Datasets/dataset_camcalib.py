import os
import yaml
import numpy as np

from Datasets.DatasetVSLAMLab import DatasetVSLAMLab
from Datasets.dataset_utilities import undistort_fisheye

SCRIPT_LABEL = f"\033[95m[{os.path.basename(__file__)}]\033[0m "


class CAMCALIB_dataset(DatasetVSLAMLab):
    """CAMCALIB: Camera Calibration Endoscopy Dataset.

    Endoscopic surgical sequences with electromagnetic (EM) tracked ground
    truth trajectories.  Each sequence includes:
      - RGB frames (JPEG, 1392x1380)
      - Camera calibration (fisheye with k1-k4 distortion)
      - 6-DoF ground truth poses from EM tracking

    Data is pre-formatted and stored locally in the benchmark directory.
    No download step is required.  Fisheye images are undistorted to pinhole
    on first use (following the same pattern as dataset_vitum and dataset_hilti2022).
    """

    def __init__(self, benchmark_path):
        super().__init__('camcalib', benchmark_path)

        with open(self.yaml_file, 'r') as file:
            data = yaml.safe_load(file)

        self.url_download_root = data.get('url_download_root', '')
        self.sequence_nicknames = [s.replace('_', ' ') for s in self.sequence_names]

    def download_sequence_data(self, sequence_name):
        # Data is already present locally; no download needed.
        pass

    def create_rgb_folder(self, sequence_name):
        # rgb_0/ folder already exists in the dataset.
        pass

    def create_rgb_csv(self, sequence_name):
        # rgb.csv already exists in the dataset.
        pass

    def create_imu_csv(self, sequence_name):
        # No IMU data available.
        pass

    def create_calibration_yaml(self, sequence_name):
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        calibration_yaml = os.path.join(sequence_path, 'calibration.yaml')

        # Read existing calibration to check camera type
        with open(calibration_yaml, 'r') as f:
            content = f.read()
        if content.startswith('%YAML'):
            content = '\n'.join(content.split('\n')[1:])
        calib = yaml.safe_load(content)

        camera_type = calib.get('Camera.type', 'Pinhole')
        if camera_type.lower() != 'fisheye':
            return  # Already pinhole, nothing to do

        # Fisheye calibration: undistort images and rewrite as pinhole
        fx = calib['Camera0.fx']
        fy = calib['Camera0.fy']
        cx = calib['Camera0.cx']
        cy = calib['Camera0.cy']
        k1 = calib.get('Camera0.k1', 0.0)
        k2 = calib.get('Camera0.k2', 0.0)
        k3 = calib.get('Camera0.k3', 0.0)
        k4 = calib.get('Camera0.k4', 0.0)

        camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        distortion_coeffs = np.array([k1, k2, k3, k4])

        rgb_csv = os.path.join(sequence_path, 'rgb.csv')
        print(f"{SCRIPT_LABEL}Undistorting images with fisheye model: {sequence_path}")
        new_fx, new_fy, new_cx, new_cy = undistort_fisheye(
            rgb_csv, sequence_path, camera_matrix, distortion_coeffs)

        # Rewrite calibration.yaml as pinhole (no distortion)
        camera0 = {"model": "Pinhole", "fx": new_fx, "fy": new_fy,
                    "cx": new_cx, "cy": new_cy}
        self.write_calibration_yaml(sequence_name, camera0=camera0)
        print(f"{SCRIPT_LABEL}Calibration updated: fisheye -> Pinhole "
              f"(fx={new_fx:.1f}, fy={new_fy:.1f}, cx={new_cx:.1f}, cy={new_cy:.1f})")

    def create_groundtruth_csv(self, sequence_name):
        # groundtruth.csv already exists in the dataset.
        pass

    def remove_unused_files(self, sequence_name):
        pass
