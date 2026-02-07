import os.path

from huggingface_hub import hf_hub_download

from utilities import print_msg
from path_constants import VSLAMLAB_BASELINES
from Baselines.BaselineVSLAMLab import BaselineVSLAMLab

SCRIPT_LABEL = f"\033[95m[{os.path.basename(__file__)}]\033[0m "


class SAGESLAM_baseline(BaselineVSLAMLab):
    """SAGE-SLAM: SLAM with Appearance and Geometry Prior for Endoscopy (ICRA 2022).

    SAGE-SLAM combines learning-based appearance priors with optimizable geometry
    priors and factor graph optimization for monocular endoscopic SLAM.  It
    simultaneously tracks the endoscope and reconstructs dense 3D geometry.

    Reference:
        Liu et al., "SAGE-SLAM: SLAM with Appearance and Geometry Prior for
        Endoscopy", ICRA 2022.  https://arxiv.org/abs/2202.09487
    GitHub:
        https://github.com/lppllppl920/SAGE-SLAM
    """

    def __init__(self, baseline_name='sageslam', baseline_folder='SAGE-SLAM'):
        default_parameters = {
            'verbose': 1,
            'mode': 'mono',
            'enable_gui': 'false',
        }

        super().__init__(baseline_name, baseline_folder, default_parameters)
        self.color = 'crimson'
        self.name_label = 'SAGE-SLAM'
        self.modes = ['mono']

    def build_execute_command(self, exp_it, exp, dataset, sequence_name):
        return super().build_execute_command_python(exp_it, exp, dataset, sequence_name)

    def git_clone(self):
        super().git_clone()
        self.sageslam_download_weights()

    def is_installed(self):
        return (True, 'is installed') if self.is_cloned() else (False, 'not installed (auto install available)')

    def sageslam_download_weights(self):
        """Download pre-trained model weights for SAGE-SLAM."""
        pretrained_dir = os.path.join(self.baseline_path, 'pretrained')
        os.makedirs(pretrained_dir, exist_ok=True)

        files = [
            os.path.join(pretrained_dir, "sage_slam_model.pth"),
        ]

        for file in files:
            file_name = os.path.basename(file)
            if not os.path.exists(file):
                print_msg(f"\n{SCRIPT_LABEL}", f"Download weights: {file}", 'info')
                try:
                    _ = hf_hub_download(
                        repo_id='vslamlab/sageslam_weights',
                        filename=file_name,
                        repo_type='model',
                        local_dir=pretrained_dir
                    )
                except Exception as e:
                    print_msg(f"\n{SCRIPT_LABEL}",
                              f"Could not download weights (may need manual setup): {e}", 'warning')


class SAGESLAM_baseline_dev(SAGESLAM_baseline):
    def __init__(self):
        super().__init__(baseline_name='sageslam-dev', baseline_folder='SAGE-SLAM-DEV')

    def is_installed(self):
        build_dir = os.path.join(self.baseline_path, 'build', 'Release', 'bin')
        is_installed = os.path.isdir(build_dir)
        return (True, 'is installed') if is_installed else (False, 'not installed (auto install available)')
