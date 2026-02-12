"""Local camera calibration dataset for VSLAM-LAB.

This dataset expects sequences to be pre-placed in the benchmark directory
in VSLAM-LAB format. Use check_dataset_vslamlab.py --fix to convert raw
data before registering it here.

Expected layout:
    <BENCHMARK_PATH>/CAMCALIB/<sequence_name>/
        rgb_0/          # images (.jpg or .png)
        rgb.csv         # ts_rgb0 (s),path_rgb0
        calibration.yaml
        groundtruth.csv # (optional)
"""

import os

from Datasets.DatasetVSLAMLab import DatasetVSLAMLab


class CAMCALIB_dataset(DatasetVSLAMLab):
    def __init__(self, benchmark_path):
        super().__init__('camcalib', benchmark_path)
        self.sequence_nicknames = [s.replace('_', ' ') for s in self.sequence_names]

    # Data is pre-placed; nothing to download.
    def download_sequence_data(self, sequence_name):
        sequence_path = os.path.join(self.dataset_path, sequence_name)
        if not os.path.isdir(sequence_path):
            raise FileNotFoundError(
                f"Sequence directory not found: {sequence_path}\n"
                f"Place your data there and run: python check_dataset_vslamlab.py {sequence_path} --fix"
            )

    def create_rgb_folder(self, sequence_name):
        return

    def create_rgb_csv(self, sequence_name):
        return

    def create_imu_csv(self, sequence_name):
        return

    def create_calibration_yaml(self, sequence_name):
        return

    def create_groundtruth_csv(self, sequence_name):
        return

    def remove_unused_files(self, sequence_name):
        return
