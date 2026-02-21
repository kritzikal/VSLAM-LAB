#!/usr/bin/env python3
"""Generate trajectory comparison plots and motion analysis for OneSLAM camcalib tuning."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.spatial.transform import Rotation

EVAL_DIR = Path("/home/kritzikal/VSLAM-LAB-Evaluation")
OUT_DIR = Path("/home/kritzikal/VSLAM-LAB/tuning_oneslam_camcalib/plots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Ground truth file (same for all configs)
GT_FILE = EVAL_DIR / "tune_000_baseline_default" / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "00000_gt.tum"


def load_tum(path):
    """Load TUM trajectory file, skipping header lines."""
    ts, xyz = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            try:
                t = float(parts[0])
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                ts.append(t)
                xyz.append([x, y, z])
            except (ValueError, IndexError):
                continue
    return np.array(ts), np.array(xyz)


def load_tum_with_quat(path):
    """Load TUM trajectory file with quaternions."""
    ts, xyz, quats = [], [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            try:
                t = float(parts[0])
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                qx, qy, qz, qw = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
                ts.append(t)
                xyz.append([x, y, z])
                quats.append([qx, qy, qz, qw])
            except (ValueError, IndexError):
                continue
    return np.array(ts), np.array(xyz), np.array(quats)


# ============================================================
# Top OneSLAM configurations to plot
# ============================================================
configs = {
    "baseline": {
        "dir": "tune_000_baseline_default",
        "label": "Baseline (17.22 mm)",
        "ate": 17.22,
        "tracked": 136,
        "color": "#e74c3c",  # red
    },
    "local_ba_10": {
        "dir": "tune_014_local_ba_size_10",
        "label": "local_ba=10 (6.76 mm)",
        "ate": 6.76,
        "tracked": 136,
        "color": "#2ecc71",  # green
    },
    "depth_scale_1": {
        "dir": "tune_005_depth_scale_1p0",
        "label": "depth_scale=1.0 (7.14 mm)",
        "ate": 7.14,
        "tracked": 136,
        "color": "#3498db",  # blue
    },
    "r2d2": {
        "dir": "combo_r1_local_ba_size10_point_sampler_r2d2",
        "label": "ba=10+r2d2 (5.67 mm)",
        "ate": 5.67,
        "tracked": 136,
        "color": "#9b59b6",  # purple
    },
    "ba10_iter15": {
        "dir": "combo_r1_local_ba_size10_tracking_ba_iterations_15",
        "label": "ba=10+iter15 (6.47 mm)",
        "ate": 6.47,
        "tracked": 136,
        "color": "#f39c12",  # orange
    },
}

# ============================================================
# 1. Individual trajectory plots (2D XY top-down)
# ============================================================
print("Generating individual trajectory plots...")
gt_ts, gt_xyz = load_tum(GT_FILE)
gt_xyz_mm = gt_xyz * 1000  # convert to mm

for name, cfg in configs.items():
    traj_file = EVAL_DIR / cfg["dir"] / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "00000_KeyFrameTrajectory.tum"
    if not traj_file.exists():
        print(f"  Skipping {name}: no trajectory file")
        continue

    est_ts, est_xyz = load_tum(traj_file)
    est_xyz_mm = est_xyz * 1000

    fig, ax = plt.subplots(1, 1, figsize=(6, 5))
    ax.plot(gt_xyz_mm[:, 0], gt_xyz_mm[:, 1], 'k-', linewidth=1.5, alpha=0.5, label='Ground Truth')
    ax.plot(gt_xyz_mm[0, 0], gt_xyz_mm[0, 1], 'ko', markersize=8)
    ax.plot(est_xyz_mm[:, 0], est_xyz_mm[:, 1], '-', color=cfg["color"], linewidth=1.5, zorder=5, label=cfg["label"])
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_title(f'OneSLAM: {cfg["label"]}')
    ax.legend(fontsize=8)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"traj_{name}.png", dpi=150)
    plt.close(fig)
    print(f"  Saved traj_{name}.png")


# ============================================================
# 2. Combined trajectory comparison (2x3 grid)
# ============================================================
print("Generating combined trajectory comparison...")
fig, axes = plt.subplots(2, 3, figsize=(15, 10))
axes_flat = axes.flatten()

# First panel: ground truth only
ax = axes_flat[0]
ax.plot(gt_xyz_mm[:, 0], gt_xyz_mm[:, 1], 'k-', linewidth=1.5)
ax.plot(gt_xyz_mm[0, 0], gt_xyz_mm[0, 1], 'go', markersize=8, label='Start')
ax.set_title('Ground Truth (EM tracker)', fontsize=11, fontweight='bold')
ax.set_xlabel('X (mm)')
ax.set_ylabel('Y (mm)')
ax.legend(fontsize=8)
ax.set_aspect('equal')
ax.grid(True, alpha=0.3)

# Remaining panels: each config
for i, (name, cfg) in enumerate(configs.items()):
    ax = axes_flat[i + 1]
    traj_file = EVAL_DIR / cfg["dir"] / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "00000_KeyFrameTrajectory.tum"
    if not traj_file.exists():
        ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
        ax.set_title(cfg["label"])
        continue

    est_ts, est_xyz = load_tum(traj_file)
    est_xyz_mm = est_xyz * 1000

    ax.plot(gt_xyz_mm[:, 0], gt_xyz_mm[:, 1], 'k-', linewidth=1.0, alpha=0.4, label='GT')
    ax.plot(est_xyz_mm[:, 0], est_xyz_mm[:, 1], '-', color=cfg["color"], linewidth=1.5, zorder=5, label='Est')
    ax.set_title(cfg["label"], fontsize=10, fontweight='bold')
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.legend(fontsize=7)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)

fig.suptitle('OneSLAM Trajectory Comparison — camcalib 2-2', fontsize=14, fontweight='bold', y=0.98)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(OUT_DIR / "comparison_trajectories.png", dpi=150)
plt.close(fig)
print("  Saved comparison_trajectories.png")


# ============================================================
# 3. Accuracy vs Tracking metrics bar chart
# ============================================================
print("Generating metrics comparison...")

# Collect all combos for the bar chart
all_configs = []
for dir_path in sorted(EVAL_DIR.glob("combo_r1_local_ba_size10_*")):
    ate_file = dir_path / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "ate.csv"
    if ate_file.exists():
        with open(ate_file) as f:
            lines = f.readlines()
            if len(lines) >= 2:
                parts = lines[1].strip().split(',')
                rmse_m = float(parts[1])
                tracked = int(parts[8])
                name = dir_path.name.replace("combo_r1_local_ba_size10_", "ba10+")
                all_configs.append({"name": name, "ate_mm": rmse_m * 1000, "tracked": tracked})

# Add baseline and tune_014 (local_ba_size=10)
all_configs.insert(0, {"name": "baseline", "ate_mm": 17.22, "tracked": 136})
all_configs.insert(1, {"name": "ba10_only", "ate_mm": 6.76, "tracked": 136})

# Sort by ATE
all_configs.sort(key=lambda x: x["ate_mm"])

# Take top 10
top_configs = all_configs[:10]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

names = [c["name"] for c in top_configs]
ates = [c["ate_mm"] for c in top_configs]
tracked = [c["tracked"] for c in top_configs]
x = np.arange(len(names))

colors = ['#2ecc71' if a < 7 else '#f39c12' if a < 10 else '#e74c3c' for a in ates]

bars1 = ax1.bar(x, ates, color=colors, edgecolor='white')
ax1.set_ylabel('ATE RMSE (mm)')
ax1.set_title('Top 10 OneSLAM Configs — Accuracy', fontsize=12, fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels(names, rotation=45, ha='right', fontsize=8)
ax1.axhline(y=17.22, color='red', linestyle='--', alpha=0.5, label='Baseline (17.22 mm)')
ax1.legend()
for bar, val in zip(bars1, ates):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
             f'{val:.1f}', ha='center', va='bottom', fontsize=8)

bars2 = ax2.bar(x, tracked, color='#3498db', edgecolor='white')
ax2.set_ylabel('Tracked Frames')
ax2.set_title('Top 10 OneSLAM Configs — Tracking Coverage', fontsize=12, fontweight='bold')
ax2.set_xticks(x)
ax2.set_xticklabels(names, rotation=45, ha='right', fontsize=8)
ax2.axhline(y=136, color='gray', linestyle='--', alpha=0.5, label='Baseline (136 frames)')
ax2.legend()
for bar, val in zip(bars2, tracked):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
             str(val), ha='center', va='bottom', fontsize=8)

fig.tight_layout()
fig.savefig(OUT_DIR / "comparison_metrics.png", dpi=150)
plt.close(fig)
print("  Saved comparison_metrics.png")


# ============================================================
# 4. Ground truth motion analysis (reuse from SAGE-SLAM but
#    generate OneSLAM-specific versions)
# ============================================================
print("Generating ground truth motion analysis...")

gt_ts_full, gt_xyz_full, gt_quats_full = load_tum_with_quat(GT_FILE)
gt_xyz_mm_full = gt_xyz_full * 1000
dt = 1.0 / 30.0  # 30 Hz

# Time relative to start
t_rel = gt_ts_full - gt_ts_full[0]

# Inter-frame displacement
disp = np.linalg.norm(np.diff(gt_xyz_mm_full, axis=0), axis=1)

# Speed
speed = disp / dt

# Acceleration
accel = np.abs(np.diff(speed)) / dt

# Angular velocity from quaternions
ang_vel = []
for i in range(len(gt_quats_full) - 1):
    r1 = Rotation.from_quat(gt_quats_full[i])
    r2 = Rotation.from_quat(gt_quats_full[i + 1])
    r_diff = r1.inv() * r2
    angle = r_diff.magnitude()
    ang_vel.append(np.degrees(angle) / dt)
ang_vel = np.array(ang_vel)

# OneSLAM boundary: frame 541 at 30 Hz = 18.0s
oneslam_boundary = 18.0
oneslam_idx = np.searchsorted(t_rel, oneslam_boundary)

# --- Figure 1: Motion Profile ---
fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)

# Displacement
ax = axes[0]
ax.plot(t_rel[1:], disp, 'b-', linewidth=0.5, alpha=0.7)
ax.axvline(x=oneslam_boundary, color='red', linestyle='--', linewidth=1.5, label=f'OneSLAM boundary ({oneslam_boundary}s)')
ax.set_ylabel('Displacement (mm)')
ax.set_title('Inter-frame Displacement')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Speed
ax = axes[1]
ax.plot(t_rel[1:], speed, 'g-', linewidth=0.5, alpha=0.7)
ax.axvline(x=oneslam_boundary, color='red', linestyle='--', linewidth=1.5)
ax.axhline(y=np.median(speed[:oneslam_idx-1]), color='orange', linestyle=':', alpha=0.7, label=f'Median (proc): {np.median(speed[:oneslam_idx-1]):.1f} mm/s')
ax.set_ylabel('Speed (mm/s)')
ax.set_title('Linear Speed')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Acceleration
ax = axes[2]
ax.plot(t_rel[2:], accel, 'r-', linewidth=0.5, alpha=0.7)
ax.axvline(x=oneslam_boundary, color='red', linestyle='--', linewidth=1.5)
ax.set_ylabel('Acceleration (mm/s²)')
ax.set_title('Linear Acceleration')
ax.grid(True, alpha=0.3)

# Angular velocity
ax = axes[3]
ax.plot(t_rel[1:], ang_vel, 'm-', linewidth=0.5, alpha=0.7)
ax.axvline(x=oneslam_boundary, color='red', linestyle='--', linewidth=1.5)
ax.axhline(y=np.median(ang_vel[:oneslam_idx-1]), color='orange', linestyle=':', alpha=0.7, label=f'Median (proc): {np.median(ang_vel[:oneslam_idx-1]):.1f} deg/s')
ax.set_ylabel('Angular Vel. (deg/s)')
ax.set_xlabel('Time (s)')
ax.set_title('Angular Velocity')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

fig.suptitle('Ground Truth Motion Profile — camcalib 2-2 (EM tracker, 30 Hz)', fontsize=13, fontweight='bold')
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(OUT_DIR / "gt_motion_profile.png", dpi=150)
plt.close(fig)
print("  Saved gt_motion_profile.png")


# --- Figure 2: Motion Analysis (3D + distributions) ---
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 3D trajectory colored by speed (use LineCollection for colored line)
from mpl_toolkits.mplot3d.art3d import Line3DCollection
ax = fig.add_subplot(2, 2, 1, projection='3d')
axes[0, 0].remove()
pts_3d = gt_xyz_mm_full[1:, :3]
segments_3d = np.array([[pts_3d[i], pts_3d[i+1]] for i in range(len(pts_3d)-1)])
lc3d = Line3DCollection(segments_3d, cmap='plasma', linewidths=1.5, alpha=0.8)
lc3d.set_array(speed[:-1])
ax.add_collection3d(lc3d)
ax.set_xlim(pts_3d[:, 0].min(), pts_3d[:, 0].max())
ax.set_ylim(pts_3d[:, 1].min(), pts_3d[:, 1].max())
ax.set_zlim(pts_3d[:, 2].min(), pts_3d[:, 2].max())
ax.set_xlabel('X (mm)')
ax.set_ylabel('Y (mm)')
ax.set_zlabel('Z (mm)')
ax.set_title('3D Trajectory (colored by speed)', fontsize=10)
plt.colorbar(lc3d, ax=ax, label='Speed (mm/s)', shrink=0.6)

# XY top-down colored by speed (use LineCollection for colored line)
from matplotlib.collections import LineCollection
ax = axes[0, 1]
pts_2d = gt_xyz_mm_full[1:, :2]
segments_2d = np.array([[pts_2d[i], pts_2d[i+1]] for i in range(len(pts_2d)-1)])
lc2d = LineCollection(segments_2d, cmap='plasma', linewidths=1.5, alpha=0.8)
lc2d.set_array(speed[:-1])
ax.add_collection(lc2d)
ax.autoscale()
sc = lc2d  # for colorbar
ax.set_xlabel('X (mm)')
ax.set_ylabel('Y (mm)')
ax.set_title('XY Top-Down (colored by speed)')
ax.set_aspect('equal')
plt.colorbar(sc, ax=ax, label='Speed (mm/s)')

# Speed distribution
ax = axes[1, 0]
proc_speed = speed[:oneslam_idx-1]
full_speed = speed
ax.hist(proc_speed, bins=50, alpha=0.7, color='#2ecc71', label=f'Processed (0-18s)\nMean: {proc_speed.mean():.1f} mm/s\nMedian: {np.median(proc_speed):.1f} mm/s')
ax.hist(full_speed, bins=50, alpha=0.4, color='#95a5a6', label=f'Full (0-51s)\nMean: {full_speed.mean():.1f} mm/s\nMedian: {np.median(full_speed):.1f} mm/s')
ax.set_xlabel('Speed (mm/s)')
ax.set_ylabel('Count')
ax.set_title('Speed Distribution')
ax.legend(fontsize=8)

# Angular velocity distribution
ax = axes[1, 1]
proc_ang = ang_vel[:oneslam_idx-1]
full_ang = ang_vel
ax.hist(proc_ang, bins=50, alpha=0.7, color='#9b59b6', label=f'Processed (0-18s)\nMean: {proc_ang.mean():.1f} deg/s\nMedian: {np.median(proc_ang):.1f} deg/s')
ax.hist(full_ang, bins=50, alpha=0.4, color='#95a5a6', label=f'Full (0-51s)\nMean: {full_ang.mean():.1f} deg/s\nMedian: {np.median(full_ang):.1f} deg/s')
ax.set_xlabel('Angular Velocity (deg/s)')
ax.set_ylabel('Count')
ax.set_title('Angular Velocity Distribution')
ax.legend(fontsize=8)

fig.suptitle('Ground Truth Motion Analysis — camcalib 2-2', fontsize=13, fontweight='bold')
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(OUT_DIR / "gt_motion_analysis.png", dpi=150)
plt.close(fig)
print("  Saved gt_motion_analysis.png")


# --- Figure 3: 3D trajectory with OneSLAM estimate overlay ---
print("Generating 3D overlay plot...")
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')

# Ground truth (full, faded beyond boundary)
ax.plot(gt_xyz_mm_full[:oneslam_idx, 0], gt_xyz_mm_full[:oneslam_idx, 1], gt_xyz_mm_full[:oneslam_idx, 2],
        'k-', linewidth=1.0, alpha=0.6, label='GT (processed)')
ax.plot(gt_xyz_mm_full[oneslam_idx:, 0], gt_xyz_mm_full[oneslam_idx:, 1], gt_xyz_mm_full[oneslam_idx:, 2],
        'k-', linewidth=0.5, alpha=0.2, label='GT (beyond boundary)')

# Best config: combo_r1 + r2d2
best_traj = EVAL_DIR / "combo_r1_local_ba_size10_point_sampler_r2d2" / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "00000_KeyFrameTrajectory.tum"
if best_traj.exists():
    est_ts, est_xyz = load_tum(best_traj)
    est_xyz_mm = est_xyz * 1000
    ax.plot(est_xyz_mm[:, 0], est_xyz_mm[:, 1], est_xyz_mm[:, 2],
            '-', color='#9b59b6', linewidth=1.5, zorder=5, label='ba10+r2d2 (5.67 mm)', alpha=0.8)

# local_ba_10 only
ba10_traj = EVAL_DIR / "tune_014_local_ba_size_10" / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "00000_KeyFrameTrajectory.tum"
if ba10_traj.exists():
    est_ts, est_xyz = load_tum(ba10_traj)
    est_xyz_mm = est_xyz * 1000
    ax.plot(est_xyz_mm[:, 0], est_xyz_mm[:, 1], est_xyz_mm[:, 2],
            '-', color='#2ecc71', linewidth=1.5, zorder=4, label='ba10 only (6.76 mm)', alpha=0.6)

ax.set_xlabel('X (mm)')
ax.set_ylabel('Y (mm)')
ax.set_zlabel('Z (mm)')
ax.set_title('OneSLAM Best Configs vs Ground Truth — 3D', fontsize=12, fontweight='bold')
ax.legend(fontsize=9)
fig.tight_layout()
fig.savefig(OUT_DIR / "traj_3d_comparison.png", dpi=150)
plt.close(fig)
print("  Saved traj_3d_comparison.png")


# ============================================================
# 5. Save motion stats CSV (same data as SAGE-SLAM)
# ============================================================
print("Saving motion stats CSV...")
proc_disp = disp[:oneslam_idx-1]
proc_speed = speed[:oneslam_idx-1]
proc_accel = accel[:oneslam_idx-2]
proc_ang = ang_vel[:oneslam_idx-1]

stats = [
    ("Duration", f"{oneslam_boundary:.1f}", f"{t_rel[-1]:.1f}", "s"),
    ("Num frames", f"{oneslam_idx}", f"{len(gt_ts_full)}", ""),
    ("Total path length", f"{proc_disp.sum():.1f}", f"{disp.sum():.1f}", "mm"),
    ("Mean speed", f"{proc_speed.mean():.2f}", f"{speed.mean():.2f}", "mm/s"),
    ("Median speed", f"{np.median(proc_speed):.2f}", f"{np.median(speed):.2f}", "mm/s"),
    ("95th pct speed", f"{np.percentile(proc_speed, 95):.2f}", f"{np.percentile(speed, 95):.2f}", "mm/s"),
    ("Max speed", f"{proc_speed.max():.2f}", f"{speed.max():.2f}", "mm/s"),
    ("Mean acceleration", f"{proc_accel.mean():.1f}", f"{accel.mean():.1f}", "mm/s²"),
    ("Max acceleration", f"{proc_accel.max():.1f}", f"{accel.max():.1f}", "mm/s²"),
    ("Mean angular velocity", f"{proc_ang.mean():.2f}", f"{ang_vel.mean():.2f}", "deg/s"),
    ("Median angular velocity", f"{np.median(proc_ang):.2f}", f"{np.median(ang_vel):.2f}", "deg/s"),
    ("Max angular velocity", f"{proc_ang.max():.2f}", f"{ang_vel.max():.2f}", "deg/s"),
    ("Workspace X range", f"{gt_xyz_mm_full[:oneslam_idx, 0].ptp():.1f}", f"{gt_xyz_mm_full[:, 0].ptp():.1f}", "mm"),
    ("Workspace Y range", f"{gt_xyz_mm_full[:oneslam_idx, 1].ptp():.1f}", f"{gt_xyz_mm_full[:, 1].ptp():.1f}", "mm"),
    ("Workspace Z range", f"{gt_xyz_mm_full[:oneslam_idx, 2].ptp():.1f}", f"{gt_xyz_mm_full[:, 2].ptp():.1f}", "mm"),
]

with open(OUT_DIR / "gt_motion_stats.csv", "w") as f:
    f.write("metric,processed_0_18s,full_0_51s,unit\n")
    for metric, proc, full, unit in stats:
        f.write(f"{metric},{proc},{full},{unit}\n")
print("  Saved gt_motion_stats.csv")

print("\nAll plots generated successfully!")
