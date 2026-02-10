#!/usr/bin/env python3
"""Endoscopy SLAM Benchmarking Pipeline

Orchestrates the full endoscopy benchmarking workflow using VSLAMLAB:
  1. Downloads endoscopy datasets (Hamlyn, C3VD, EndoSLAM)
  2. Installs SLAM baselines (SAGE-SLAM, OneSLAM, MASt3R-SLAM)
  3. Runs experiments across all dataset/baseline combinations
  4. Evaluates trajectories against ground truth (ATE, tracked frames)
  5. Generates comparison visualizations and tables

Usage:
    # Full benchmark (3 runs per baseline per sequence)
    pixi run -e vslamlab vslamlab configs/exp_endoscopy_benchmark.yaml

    # Quick test (1 run, first 200 frames)
    pixi run -e vslamlab vslamlab configs/exp_endoscopy_quick.yaml

    # Evaluate completed experiments
    pixi run -e vslamlab evaluate configs/exp_endoscopy_benchmark.yaml

    # Generate comparison plots and tables
    pixi run -e vslamlab compare configs/exp_endoscopy_benchmark.yaml

    # Or run this script directly for a guided workflow:
    python run_endoscopy_benchmark.py [--quick] [--skip-download]

Datasets:
    Hamlyn    - Laparoscopic/endoscopic stereo (vslamlab/Hamlyn_Rectified_Dataset)
    C3VD      - Colonoscopy with 6-DoF GT (https://durrlab.github.io/C3VD/)
    EndoSLAM  - GI-tract with robotic arm GT (https://data.mendeley.com/datasets/cd2rtzm23r)

Baselines:
    MASt3R-SLAM  - Foundation model SLAM (Leroy et al., 2024)
    SAGE-SLAM    - Endoscopy SLAM with priors (Liu et al., ICRA 2022)
    OneSLAM      - Generalized endoscopy SLAM (Teufel et al., IPCAI 2024)

Metrics (computed by VSLAMLAB built-in functions):
    Accuracy    - ATE RMSE (m) via evo library
    Robustness  - Tracked frames / total frames ratio
    Runtime     - Processing time (ms/frame and total seconds)
    Memory      - Peak GPU, RAM, SWAP usage (GB)
"""

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BENCHMARK_CONFIGS = {
    'full': 'configs/exp_endoscopy_benchmark.yaml',
    'quick': 'configs/exp_endoscopy_quick.yaml',
}

COMPARISON_CONFIG = 'configs/comp_endoscopy.yaml'


def run_pixi_command(env, task, *args):
    """Run a pixi command and return success status."""
    cmd = f"pixi run -e {env} {task}"
    if args:
        cmd += ' ' + ' '.join(str(a) for a in args)
    print(f"\n{'='*70}")
    print(f"  Running: {cmd}")
    print(f"{'='*70}\n")
    result = subprocess.run(cmd, shell=True, cwd=SCRIPT_DIR)
    return result.returncode == 0


def print_banner(text):
    """Print a formatted banner."""
    width = max(len(text) + 4, 60)
    print(f"\n{'#'*width}")
    print(f"# {text.center(width-4)} #")
    print(f"{'#'*width}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Endoscopy SLAM Benchmarking Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--quick', action='store_true',
                        help='Run quick benchmark (1 run, 200 frames)')
    parser.add_argument('--skip-download', action='store_true',
                        help='Skip dataset download step')
    parser.add_argument('--evaluate-only', action='store_true',
                        help='Only run evaluation on existing results')
    parser.add_argument('--compare-only', action='store_true',
                        help='Only run comparison/visualization')
    parser.add_argument('--exp-yaml', type=str, default=None,
                        help='Custom experiment YAML file')
    args = parser.parse_args()

    # Select config
    if args.exp_yaml:
        exp_yaml = args.exp_yaml
    elif args.quick:
        exp_yaml = BENCHMARK_CONFIGS['quick']
    else:
        exp_yaml = BENCHMARK_CONFIGS['full']

    print_banner('Endoscopy SLAM Benchmark')
    print(f"  Experiment config: {exp_yaml}")
    print(f"  Comparison config: {COMPARISON_CONFIG}")
    print(f"  Working directory: {SCRIPT_DIR}")

    # Step 1: Run experiments (download + install + execute)
    if not args.evaluate_only and not args.compare_only:
        print_banner('Step 1/3: Running SLAM Experiments')
        success = run_pixi_command('vslamlab', 'vslamlab', exp_yaml)
        if not success:
            print("\nExperiment execution encountered errors.")
            print("Check log files in the experiment output directory.")
            # Continue to evaluation even if some experiments failed

    # Step 2: Evaluate trajectories
    if not args.compare_only:
        print_banner('Step 2/3: Evaluating Trajectories')
        success = run_pixi_command('vslamlab', 'evaluate', exp_yaml)
        if not success:
            print("\nEvaluation encountered errors.")

    # Step 3: Generate comparisons
    print_banner('Step 3/3: Generating Comparisons')

    # Set the comparison config to include all endoscopy metrics
    os.environ['VSLAMLAB_COMPARISONS_YAML'] = os.path.join(SCRIPT_DIR, COMPARISON_CONFIG)
    success = run_pixi_command('vslamlab', 'compare', exp_yaml)

    if success:
        print_banner('Benchmark Complete')
        print("  Results are saved in the VSLAM-LAB-Evaluation directory.")
        print("  Comparison plots and tables are in the 'figures/' subdirectory.")
        print("\n  Key output files:")
        print("    - *_boxplot.pdf         : ATE accuracy boxplots")
        print("    - *_radar.pdf           : Relative accuracy radar chart")
        print("    - trajectories.pdf      : 2D trajectory overlays")
        print("    - *_table.tex           : LaTeX tables for papers")
        print("    - memory_usage_table.tex: Memory usage breakdown")
    else:
        print("\nComparison generation encountered errors.")
        print("Make sure experiments and evaluation completed successfully first.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
