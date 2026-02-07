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

    def is_installed(self):
        return (True, 'is installed') if self.is_cloned() else (False, 'not installed (auto install available)')


class ONESLAM_baseline_dev(ONESLAM_baseline):
    def __init__(self):
        super().__init__(baseline_name='oneslam-dev', baseline_folder='OneSLAM-DEV')

    def is_installed(self):
        run_script = os.path.join(self.baseline_path, 'run_slam.py')
        is_installed = os.path.isfile(run_script)
        return (True, 'is installed') if is_installed else (False, 'not installed (auto install available)')
