#!/usr/bin/env python3
"""Plot endoscopy SLAM trajectories overlaid on a single graph.

Reads trajectory CSVs from VSLAMLAB evaluation folders and plots all
baselines for each sequence on one figure. Works without ground truth.

Usage:
    python plot_endoscopy_trajectories.py [--eval-dir PATH] [--save FILE]
"""

import argparse
import glob
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

# Baseline display config
BASELINE_STYLES = {
    'mast3rslam': {'color': '#1f77b4', 'label': 'MASt3R-SLAM', 'lw': 2.0},
    'droidslam':  {'color': '#d62728', 'label': 'DROID-SLAM',  'lw': 2.0},
    'sageslam':   {'color': '#dc143c', 'label': 'SAGE-SLAM',   'lw': 2.0},
    'oneslam':    {'color': '#1e90ff', 'label': 'OneSLAM',     'lw': 2.0},
}

def find_trajectory_csvs(eval_dir):
    """Find all trajectory CSVs grouped by (experiment, dataset, sequence)."""
    results = {}
    for exp_dir in sorted(glob.glob(os.path.join(eval_dir, 'exp_*'))):
        exp_name = os.path.basename(exp_dir)
        # Detect baseline from experiment name
        baseline = None
        for key in BASELINE_STYLES:
            if key in exp_name:
                baseline = key
                break
        if baseline is None:
            continue

        # Walk dataset/sequence directories
        for dataset_dir in sorted(glob.glob(os.path.join(exp_dir, '*'))):
            if not os.path.isdir(dataset_dir):
                continue
            dataset_name = os.path.basename(dataset_dir)
            for seq_dir in sorted(glob.glob(os.path.join(dataset_dir, '*'))):
                if not os.path.isdir(seq_dir):
                    continue
                seq_name = os.path.basename(seq_dir)
                # Find trajectory CSVs
                traj_files = sorted(glob.glob(os.path.join(seq_dir, '*_KeyFrameTrajectory.csv')))
                if traj_files:
                    key = (dataset_name, seq_name)
                    if key not in results:
                        results[key] = {}
                    results[key][baseline] = traj_files

    return results


def read_trajectory(csv_path):
    """Read a VSLAMLAB trajectory CSV and return xyz positions."""
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return None
        # Handle both comma and space delimited
        if len(df.columns) == 1:
            df = pd.read_csv(csv_path, sep=' ')
        if 'tx' in df.columns:
            return df[['tx', 'ty', 'tz']].values
        elif len(df.columns) >= 4:
            return df.iloc[:, 1:4].values
    except Exception:
        pass
    return None


def plot_trajectories(all_trajs, save_path=None):
    """Plot all trajectories overlaid per sequence."""
    n_sequences = len(all_trajs)
    if n_sequences == 0:
        print("No trajectories found.")
        return

    n_cols = min(n_sequences, 3)
    n_rows = (n_sequences + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows))
    if n_sequences == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if n_sequences > 1 else [axes]

    legend_entries = {}

    for idx, ((dataset, seq), baselines) in enumerate(sorted(all_trajs.items())):
        ax = axes[idx]

        for baseline, traj_files in sorted(baselines.items()):
            style = BASELINE_STYLES.get(baseline, {'color': 'gray', 'label': baseline, 'lw': 1.5})

            for traj_file in traj_files:
                xyz = read_trajectory(traj_file)
                if xyz is None or len(xyz) < 2:
                    continue

                # Project 3D trajectory to 2D via PCA
                if xyz.shape[0] >= 2:
                    pca = PCA(n_components=2)
                    xy = pca.fit_transform(xyz)
                else:
                    xy = xyz[:, :2]

                line, = ax.plot(xy[:, 0], xy[:, 1],
                               color=style['color'],
                               linewidth=style['lw'],
                               alpha=0.8)

                # Mark start and end
                ax.plot(xy[0, 0], xy[0, 1], 'o', color=style['color'], markersize=6)
                ax.plot(xy[-1, 0], xy[-1, 1], 's', color=style['color'], markersize=6)

                if baseline not in legend_entries:
                    legend_entries[baseline] = (line, style['label'])

        ax.set_title(f"{dataset} / {seq}", fontsize=12, fontweight='bold')
        ax.set_xlabel('PCA Component 1')
        ax.set_ylabel('PCA Component 2')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal', adjustable='datalim')

    # Hide unused subplots
    for idx in range(n_sequences, len(axes)):
        axes[idx].set_visible(False)

    # Single legend for all subplots
    if legend_entries:
        handles = [entry[0] for entry in legend_entries.values()]
        labels = [entry[1] for entry in legend_entries.values()]
        fig.legend(handles, labels, loc='lower center', ncol=len(legend_entries),
                   fontsize=12, frameon=True, fancybox=True)

    plt.suptitle('Endoscopy SLAM Trajectory Comparison', fontsize=14, fontweight='bold')
    plt.tight_layout(rect=[0, 0.08, 1, 0.95])

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {save_path}")

    plt.show()


def main():
    parser = argparse.ArgumentParser(description='Plot endoscopy SLAM trajectories')
    parser.add_argument('--eval-dir', type=str,
                        default=os.path.expanduser('~/VSLAM-LAB-Evaluation'),
                        help='Path to VSLAMLAB evaluation directory')
    parser.add_argument('--save', type=str, default=None,
                        help='Save plot to file (e.g. trajectories.pdf)')
    args = parser.parse_args()

    if not os.path.isdir(args.eval_dir):
        print(f"Evaluation directory not found: {args.eval_dir}")
        sys.exit(1)

    all_trajs = find_trajectory_csvs(args.eval_dir)
    print(f"Found trajectories for {len(all_trajs)} sequence(s):")
    for (dataset, seq), baselines in sorted(all_trajs.items()):
        baseline_names = [BASELINE_STYLES.get(b, {}).get('label', b) for b in baselines]
        print(f"  {dataset}/{seq}: {', '.join(baseline_names)}")

    plot_trajectories(all_trajs, save_path=args.save)


if __name__ == '__main__':
    main()
