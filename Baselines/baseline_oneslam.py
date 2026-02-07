import os.path

from utilities import print_msg
from path_constants import VSLAMLAB_BASELINES
from Baselines.BaselineVSLAMLab import BaselineVSLAMLab

SCRIPT_LABEL = f"\033[95m[{os.path.basename(__file__)}]\033[0m "


class ONESLAM_baseline(BaselineVSLAMLab):
    """OneSLAM: A generalized monocular SLAM for surgical endoscopy (IPCAI 2024).

    OneSLAM is a generalized monocular SLAM algorithm for surgical endoscopy that
    works out-of-the-box for multiple endoscopic domains (sinus, colonoscopy,
    arthroscopy, laparoscopy).  It leverages Tracking Any Point (TAP) foundation
    models for robust sparse correspondence tracking and local bundle adjustment.

    Weights are obtained during install via two scripts:
      - init_submodules.sh: clones CoTracker + R2D2 submodules (R2D2 ships weights)
      - get_tap_model.sh:   downloads CoTracker checkpoints from dl.fbaipublicfiles.com

    Reference:
        Teufel et al., "OneSLAM to map them all: a generalized approach to SLAM
        for monocular endoscopic imaging based on tracking any point", IPCAI 2024 /
        IJCARS.  https://link.springer.com/article/10.1007/s11548-024-03171-6
    GitHub:
        https://github.com/arcadelab/OneSLAM
    """

    def __init__(self, baseline_name='oneslam', baseline_folder='OneSLAM'):
        default_parameters = {
            'verbose': 1,
            'mode': 'mono',
        }

        super().__init__(baseline_name, baseline_folder, default_parameters)
        self.color = 'dodgerblue'
        self.name_label = 'OneSLAM'
        self.modes = ['mono']

    def build_execute_command(self, exp_it, exp, dataset, sequence_name):
        return super().build_execute_command_python(exp_it, exp, dataset, sequence_name)

    def git_clone(self):
        super().git_clone()
        self._check_weights()

    def is_installed(self):
        return (True, 'is installed') if self.is_cloned() else (False, 'not installed (auto install available)')

    def _check_weights(self):
        """Verify that required model weights exist after clone + install.

        OneSLAM needs two sets of weights:
          1. CoTracker checkpoints in trained_models/cotracker/
             (downloaded by get_tap_model.sh from dl.fbaipublicfiles.com)
          2. R2D2 weights in DBoW/r2d2/models/
             (bundled with the r2d2 git submodule via init_submodules.sh)
        """
        cotracker_dir = os.path.join(self.baseline_path, 'trained_models', 'cotracker')
        r2d2_weights = os.path.join(self.baseline_path, 'DBoW', 'r2d2', 'models', 'faster2d2_WASF_N16.pt')

        has_cotracker = (os.path.isdir(cotracker_dir)
                         and any(f.endswith('.pth') for f in os.listdir(cotracker_dir)))
        has_r2d2 = os.path.isfile(r2d2_weights)

        if has_cotracker and has_r2d2:
            print_msg(f"{SCRIPT_LABEL}", "CoTracker and R2D2 weights found", 'info')
        else:
            missing = []
            if not has_cotracker:
                missing.append("CoTracker (run get_tap_model.sh)")
            if not has_r2d2:
                missing.append("R2D2 (run init_submodules.sh)")
            print_msg(f"{SCRIPT_LABEL}",
                      f"Missing weights: {', '.join(missing)}. "
                      f"Run: pixi run -e oneslam-dev install",
                      'warning')


class ONESLAM_baseline_dev(ONESLAM_baseline):
    def __init__(self):
        super().__init__(baseline_name='oneslam-dev', baseline_folder='OneSLAM-DEV')

    def is_installed(self):
        run_script = os.path.join(self.baseline_path, 'run_slam.py')
        cotracker_dir = os.path.join(self.baseline_path, 'trained_models', 'cotracker')
        has_weights = (os.path.isdir(cotracker_dir)
                       and any(f.endswith('.pth') for f in os.listdir(cotracker_dir)))
        is_installed = os.path.isfile(run_script) and has_weights
        return (True, 'is installed') if is_installed else (False, 'not installed (auto install available)')
