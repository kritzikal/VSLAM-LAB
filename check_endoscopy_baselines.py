#!/usr/bin/env python3
"""Check if endoscopy SLAM baselines are installed with weights.

Usage:
    python check_endoscopy_baselines.py
"""

import os
import sys

BASELINES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Baselines')

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BOLD = '\033[1m'
RESET = '\033[0m'


def check_mast3rslam():
    """Check MASt3R-SLAM installation and weights."""
    name = 'MASt3R-SLAM'
    base = os.path.join(BASELINES_DIR, 'MASt3R-SLAM')
    results = []

    # Check cloned
    cloned = os.path.isdir(base)
    results.append(('Repository cloned', cloned, base))

    # Check weights (3 checkpoint files)
    ckpt_dir = os.path.join(base, 'checkpoints')
    weight_files = [
        'MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric.pth',
        'MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric_retrieval_trainingfree.pth',
        'MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric_retrieval_codebook.pkl',
    ]
    for wf in weight_files:
        path = os.path.join(ckpt_dir, wf)
        exists = os.path.isfile(path)
        size = ''
        if exists:
            mb = os.path.getsize(path) / (1024 * 1024)
            size = f' ({mb:.0f} MB)'
        results.append((f'Weight: {wf}', exists, path + size))

    return name, results


def check_sageslam():
    """Check SAGE-SLAM installation and weights."""
    name = 'SAGE-SLAM'
    base = os.path.join(BASELINES_DIR, 'SAGE-SLAM-DEV')
    results = []

    # Check cloned
    cloned = os.path.isdir(base)
    results.append(('Repository cloned', cloned, base))

    # Check build (cmake output)
    build_dir = os.path.join(base, 'build', 'Release', 'bin')
    results.append(('Built (build/Release/bin)', os.path.isdir(build_dir), build_dir))

    # Check pretrained weights
    pretrained_dir = os.path.join(base, 'pretrained')
    has_pretrained = os.path.isdir(pretrained_dir) and len(os.listdir(pretrained_dir)) > 0
    count = len(os.listdir(pretrained_dir)) if os.path.isdir(pretrained_dir) else 0
    results.append((f'Pretrained weights ({count} files)', has_pretrained, pretrained_dir))

    # Check representation weights
    repr_dir = os.path.join(base, 'representation')
    has_repr = os.path.isdir(repr_dir) and len(os.listdir(repr_dir)) > 0
    count = len(os.listdir(repr_dir)) if os.path.isdir(repr_dir) else 0
    results.append((f'Representation weights ({count} files)', has_repr, repr_dir))

    return name, results


def check_oneslam():
    """Check OneSLAM installation and weights."""
    name = 'OneSLAM'
    base = os.path.join(BASELINES_DIR, 'OneSLAM-DEV')
    results = []

    # Check cloned
    cloned = os.path.isdir(base)
    results.append(('Repository cloned', cloned, base))

    # Check run_slam.py exists
    run_script = os.path.join(base, 'run_slam.py')
    results.append(('run_slam.py exists', os.path.isfile(run_script), run_script))

    # Check CoTracker weights
    cotracker_dir = os.path.join(base, 'trained_models', 'cotracker')
    has_cotracker = False
    cotracker_files = []
    if os.path.isdir(cotracker_dir):
        cotracker_files = [f for f in os.listdir(cotracker_dir) if f.endswith('.pth')]
        has_cotracker = len(cotracker_files) > 0
    results.append((f'CoTracker weights ({len(cotracker_files)} .pth files)', has_cotracker, cotracker_dir))

    # Check R2D2 weights
    r2d2_path = os.path.join(base, 'DBoW', 'r2d2', 'models', 'faster2d2_WASF_N16.pt')
    has_r2d2 = os.path.isfile(r2d2_path)
    size = ''
    if has_r2d2:
        mb = os.path.getsize(r2d2_path) / (1024 * 1024)
        size = f' ({mb:.0f} MB)'
    results.append(('R2D2 weights (faster2d2_WASF_N16.pt)', has_r2d2, r2d2_path + size))

    # Check g2o python package installed (via pip install g2o-python)
    # g2o is installed in the oneslam-dev pixi env, so probe it via subprocess
    import subprocess as _sp
    has_g2o = False
    g2o_loc = 'not installed (run: pixi run -e oneslam-dev install)'
    try:
        r = _sp.run(
            ['pixi', 'run', '-e', 'oneslam-dev', 'python', '-c',
             'import g2o; print(g2o.__file__)'],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(BASELINES_DIR)
        )
        if r.returncode == 0 and r.stdout.strip():
            has_g2o = True
            g2o_loc = r.stdout.strip()
    except Exception:
        pass
    # Fallback: check in current interpreter too
    if not has_g2o:
        try:
            import importlib
            g2o_spec = importlib.util.find_spec('g2o')
            if g2o_spec is not None:
                has_g2o = True
                g2o_loc = g2o_spec.origin or 'found'
        except Exception:
            pass
    results.append(('g2o python package (g2o-python)', has_g2o, g2o_loc))

    return name, results


def print_results(name, results):
    """Print check results for one baseline."""
    all_ok = all(ok for _, ok, _ in results)
    status = f'{GREEN}READY{RESET}' if all_ok else f'{RED}NOT READY{RESET}'
    print(f'\n{BOLD}  {name}{RESET}  [{status}]')
    print(f'  {"─" * 60}')
    for label, ok, path in results:
        icon = f'{GREEN}✓{RESET}' if ok else f'{RED}✗{RESET}'
        print(f'  {icon}  {label}')
        if not ok:
            print(f'      {YELLOW}→ {path}{RESET}')
    return all_ok


def main():
    print(f'\n{BOLD}Endoscopy SLAM Baseline Installation Check{RESET}')
    print(f'{"=" * 50}')
    print(f'  Baselines directory: {BASELINES_DIR}\n')

    checks = [check_mast3rslam, check_sageslam, check_oneslam]
    all_ready = True

    for check_fn in checks:
        name, results = check_fn()
        ok = print_results(name, results)
        if not ok:
            all_ready = False

    print(f'\n{"=" * 50}')
    if all_ready:
        print(f'  {GREEN}{BOLD}All baselines ready for benchmarking.{RESET}')
    else:
        print(f'  {YELLOW}{BOLD}Some baselines need attention (see ✗ above).{RESET}')
        print(f'  Fix tips:')
        print(f'    MASt3R-SLAM : pixi run -e mast3rslam git-clone')
        print(f'    SAGE-SLAM   : pixi run -e sageslam-dev git-clone && pixi run -e sageslam-dev install')
        print(f'    OneSLAM     : pixi run -e oneslam-dev git-clone && pixi run -e oneslam-dev install')
    print()

    return 0 if all_ready else 1


if __name__ == '__main__':
    sys.exit(main())
