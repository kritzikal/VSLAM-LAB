import os.path

from utilities import print_msg
from path_constants import VSLAMLAB_BASELINES
from Baselines.BaselineVSLAMLab import BaselineVSLAMLab

SCRIPT_LABEL = f"\033[95m[{os.path.basename(__file__)}]\033[0m "


class SAGESLAM_baseline(BaselineVSLAMLab):
    """SAGE-SLAM: SLAM with Appearance and Geometry Prior for Endoscopy (ICRA 2022).

    SAGE-SLAM combines learning-based appearance priors with optimizable geometry
    priors and factor graph optimization for monocular endoscopic SLAM.  It
    simultaneously tracks the endoscope and reconstructs dense 3D geometry.

    Pretrained weights are bundled with the SAGE-SLAM repository itself
    (in the pretrained/ and representation/ directories), so no separate
    download step is needed after git clone.

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
        self._check_weights()

    def is_installed(self):
        return (True, 'is installed') if self.is_cloned() else (False, 'not installed (auto install available)')

    def _check_weights(self):
        """Verify that pretrained weights exist after cloning.

        SAGE-SLAM ships weights inside the repo (pretrained/ and representation/
        directories).  This method checks they are present and warns if not.
        """
        pretrained_dir = os.path.join(self.baseline_path, 'pretrained')
        representation_dir = os.path.join(self.baseline_path, 'representation')

        has_pretrained = os.path.isdir(pretrained_dir) and len(os.listdir(pretrained_dir)) > 0
        has_representation = os.path.isdir(representation_dir) and len(os.listdir(representation_dir)) > 0

        if has_pretrained:
            print_msg(f"{SCRIPT_LABEL}", "Pretrained weights found in repo", 'info')
        else:
            print_msg(f"{SCRIPT_LABEL}",
                      "Pretrained weights NOT found. SAGE-SLAM ships weights "
                      "inside the repo (pretrained/ directory). If missing, "
                      "re-clone from https://github.com/lppllppl920/SAGE-SLAM "
                      "or generate data using DenseReconstruction-Pytorch.",
                      'warning')


class SAGESLAM_baseline_dev(SAGESLAM_baseline):
    def __init__(self):
        super().__init__(baseline_name='sageslam-dev', baseline_folder='SAGE-SLAM-DEV')

    def is_installed(self):
        build_dir = os.path.join(self.baseline_path, 'build', 'Release', 'bin')
        is_installed = os.path.isdir(build_dir)
        return (True, 'is installed') if is_installed else (False, 'not installed (auto install available)')
