#!/usr/bin/env python3
"""Single-parameter ablation study for SAGE-SLAM on camcalib dataset.

Tests one parameter at a time against the default configuration.
Modifies slam_run.flags before each run, then restores the original.

Usage:
    pixi run -e vslamlab python tune_sageslam_camcalib.py [--dry-run]
"""

import copy
import csv
import os
import re
import shutil
import subprocess
import time
import yaml
from datetime import datetime
from pathlib import Path

VSLAM_LAB = Path(__file__).parent.resolve()
SAGE_SLAM_DEV = VSLAM_LAB / "Baselines" / "SAGE-SLAM-DEV"
EVALUATION = Path(os.path.expanduser("~/VSLAM-LAB-Evaluation"))
FLAGS_FILE = SAGE_SLAM_DEV / "system" / "configs" / "slam_run.flags"
FLAGS_BACKUP = SAGE_SLAM_DEV / "system" / "configs" / "slam_run.flags.bak"
TUNING_DIR = VSLAM_LAB / "tuning_sageslam_camcalib"
RESULTS_CSV = TUNING_DIR / "ablation_results.csv"
RESULTS_MD = VSLAM_LAB / "SAGESLAM_CAMCALIB_ABLATION.md"

EXP_TEMPLATE = {
    "Config": "config_camcalib.yaml",
    "NumRuns": 1,
    "Parameters": {"verbose": 1, "mode": "mono", "enable_gui": "false", "rgb_idx": [0, 541]},
    "Module": "sageslam-dev",
}

# Default values from slam_run.flags (for reference and reporting)
DEFAULTS = {
    "tracking_max_num_iters": 40,
    "tracking_desc_num_keypoints": 256,
    "new_kf_min_average_motion": 0.08,
    "new_kf_max_area_ratio": 0.85,
    "new_kf_max_inlier_ratio": 0.92,
    "temporal_max_back_connections": 3,
    "factor_iters": 1000,
    "geo_factor_weight": 0.1,
    "refine_mapping_iters": 10,
    "mapping_update_frequency": 2.0,
    "desc_num_keypoints": 512,
    "pho_num_samples": 3072,
    "code_factor_weight": 1.0e-3,
    "tracking_init_damp": 1.0e-4,
}

# Candidate values to test for each parameter
CANDIDATES = {
    "tracking_max_num_iters":      [20, 60, 80, 100],
    "tracking_desc_num_keypoints": [128, 512, 1024],
    "new_kf_min_average_motion":   [0.02, 0.04, 0.12, 0.2],
    "new_kf_max_area_ratio":       [0.7, 0.8, 0.9, 0.95],
    "new_kf_max_inlier_ratio":     [0.8, 0.85, 0.95, 0.98],
    "temporal_max_back_connections": [1, 5, 7],
    "factor_iters":                [500, 2000],
    "geo_factor_weight":           [0.01, 0.05, 0.2, 0.5],
    "refine_mapping_iters":        [5, 20, 30],
    "mapping_update_frequency":    [1.0, 4.0],
    "desc_num_keypoints":          [256, 1024],
    "pho_num_samples":             [1024, 2048, 4096],
    "code_factor_weight":          [1.0e-4, 1.0e-2],
}


def modify_flags_file(param_name, value):
    """Modify a single parameter in slam_run.flags.

    gflags format: --param_name=value
    """
    with open(FLAGS_FILE, "r") as f:
        content = f.read()

    # Format value for flags file
    if isinstance(value, float):
        # Use scientific notation for very small/large values
        if abs(value) < 0.01 or abs(value) > 1000:
            val_str = f"{value:.1e}"
        else:
            val_str = str(value)
    else:
        val_str = str(value)

    pattern = rf"(--{param_name}=).*"
    if re.search(pattern, content):
        new_content = re.sub(pattern, rf"\g<1>{val_str}", content)
    else:
        # Parameter not in file, append it
        new_content = content.rstrip() + f"\n--{param_name}={val_str}\n"

    with open(FLAGS_FILE, "w") as f:
        f.write(new_content)


def restore_flags():
    """Restore the original flags file from backup."""
    if FLAGS_BACKUP.exists():
        shutil.copy2(FLAGS_BACKUP, FLAGS_FILE)


def create_exp_yaml(exp_name, path):
    config = {exp_name: copy.deepcopy(EXP_TEMPLATE)}
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def run_and_eval(exp_yaml_path):
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    cmd_run = f"pixi run -e vslamlab vslamlab {exp_yaml_path} --overwrite"
    cmd_eval = f"pixi run -e vslamlab evaluate {exp_yaml_path} --overwrite"
    print(f"  Running: {cmd_run}")
    try:
        subprocess.run(cmd_run, shell=True, cwd=str(VSLAM_LAB),
                       capture_output=False, text=True, timeout=3600, env=env)
    except subprocess.TimeoutExpired:
        print("  TIMEOUT during run")
    print(f"  Evaluating: {cmd_eval}")
    try:
        subprocess.run(cmd_eval, shell=True, cwd=str(VSLAM_LAB),
                       capture_output=False, text=True, timeout=300, env=env)
    except Exception:
        pass


def m_to_mm(v):
    """Convert meters to millimeters."""
    return v * 1000.0 if v is not None else None


def get_ate_stats(exp_name):
    """Get ATE stats in mm. Raw evo output is in meters, convert to mm."""
    ate_csv = EVALUATION / exp_name / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "ate.csv"
    if not ate_csv.exists():
        return None, None, None, None, None
    import pandas as pd
    df = pd.read_csv(ate_csv)
    if df.empty:
        return None, None, None, None, None
    rmse = m_to_mm(df["rmse"].values[0]) if "rmse" in df.columns else None
    mean = m_to_mm(df["mean"].values[0]) if "mean" in df.columns else None
    median = m_to_mm(df["median"].values[0]) if "median" in df.columns else None
    n_tracked = int(df["num_tracked_frames"].values[0]) if "num_tracked_frames" in df.columns else None
    n_eval = int(df["num_evaluated_frames"].values[0]) if "num_evaluated_frames" in df.columns else None
    return rmse, mean, median, n_tracked, n_eval


def get_run_time(exp_name):
    log_csv = EVALUATION / exp_name / "vslamlab_exp_log.csv"
    if not log_csv.exists():
        return None
    import pandas as pd
    df = pd.read_csv(log_csv)
    if df.empty or "TIME" not in df.columns:
        return None
    return df["TIME"].values[0]


def regenerate_report():
    """Re-read all existing ATE results and regenerate the report + CSV."""
    all_results = []
    run_id = 0
    csv_fields = ["run_id", "param_name", "value", "default", "exp_name",
                   "ate_rmse_mm", "ate_mean_mm", "ate_median_mm",
                   "n_tracked", "n_evaluated", "run_time", "elapsed"]

    # Baseline
    baseline_name = "sage_ablation_baseline"
    rmse, mean, median, n_tracked, n_eval = get_ate_stats(baseline_name)
    run_time = get_run_time(baseline_name)
    baseline_result = {
        "run_id": run_id, "param_name": "baseline", "value": "-", "default": "-",
        "exp_name": baseline_name, "ate_rmse_mm": rmse, "ate_mean_mm": mean,
        "ate_median_mm": median, "n_tracked": n_tracked, "n_evaluated": n_eval,
        "run_time": run_time, "elapsed": 0,
    }
    all_results.append(baseline_result)
    run_id += 1
    baseline_rmse = rmse
    if rmse is not None:
        print(f"BASELINE: ATE RMSE = {rmse:.2f} mm, tracked {n_tracked}/541")
    else:
        print("BASELINE: FAIL")

    for param_name, values in CANDIDATES.items():
        default_val = DEFAULTS[param_name]
        for value in values:
            if value == default_val:
                continue
            val_str = str(value).replace(".", "p").replace("-", "n").replace("+", "")
            exp_name = f"sage_ablation_{param_name}_{val_str}"
            rmse, mean, median, n_tracked, n_eval = get_ate_stats(exp_name)
            run_time = get_run_time(exp_name)
            result = {
                "run_id": run_id, "param_name": param_name, "value": value,
                "default": default_val, "exp_name": exp_name,
                "ate_rmse_mm": rmse, "ate_mean_mm": mean, "ate_median_mm": median,
                "n_tracked": n_tracked, "n_evaluated": n_eval,
                "run_time": run_time, "elapsed": 0,
            }
            all_results.append(result)
            run_id += 1
            if rmse is not None:
                delta = rmse - baseline_rmse if baseline_rmse else 0
                print(f"  {param_name}={value}: {rmse:.2f} mm ({delta:+.2f}), tracked {n_tracked}/541")
            else:
                print(f"  {param_name}={value}: FAIL")

    # Save CSV
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for r in all_results:
            row = {}
            for k in csv_fields:
                v = r.get(k, "")
                if isinstance(v, float) and k.startswith("ate_"):
                    row[k] = f"{v:.2f}" if v is not None else ""
                else:
                    row[k] = v
            writer.writerow(row)
    print(f"CSV saved to {RESULTS_CSV}")

    generate_md(all_results, baseline_rmse)


# Combo tuning: parameter combinations to test
# Phase 2: Tracking reliability experiments
# Root cause: LM optimizer divergence producing NaN poses (284/388 in baseline).
# Best tracking so far: area09_code01 = 253/542 (47%), 0 NaN poses.
# Strategy: stabilize LM optimizer + add geometric constraints + use best base config.
#
# Base config = area09_code01 (best tracking: 253 frames, no NaN)
BASE_TRACKING = {
    "new_kf_max_area_ratio": 0.9,
    "code_factor_weight": 0.01,
}

COMBO_CONFIGS = {
    # === PHASE 1: LM OPTIMIZER STABILIZATION ===
    # Test tracking_init_damp (LM damping initialization)
    "track_damp_5e5": {
        **BASE_TRACKING,
        "tracking_init_damp": 5.0e-5,
    },
    "track_damp_5e4": {
        **BASE_TRACKING,
        "tracking_init_damp": 5.0e-4,
    },
    "track_damp_1e3": {
        **BASE_TRACKING,
        "tracking_init_damp": 1.0e-3,
    },
    # Test tracking convergence thresholds
    "track_grad_1e5": {
        **BASE_TRACKING,
        "tracking_min_grad_thresh": 1.0e-5,
    },
    "track_grad_1e3": {
        **BASE_TRACKING,
        "tracking_min_grad_thresh": 1.0e-3,
    },
    "track_param_1e3": {
        **BASE_TRACKING,
        "tracking_min_param_inc_thresh": 1.0e-3,
    },
    "track_param_1e1": {
        **BASE_TRACKING,
        "tracking_min_param_inc_thresh": 1.0e-1,
    },
    # Test Jacobian update sensitivity
    "track_jac_1e3": {
        **BASE_TRACKING,
        "tracking_jac_update_err_inc_threshold": 1.0e-3,
    },
    "track_jac_5e2": {
        **BASE_TRACKING,
        "tracking_jac_update_err_inc_threshold": 5.0e-2,
    },

    # === PHASE 2: GEOMETRIC CONSTRAINTS ===
    # Increase reprojection weight in tracker
    "track_reproj_05": {
        **BASE_TRACKING,
        "tracker_reproj_factor_weight": 0.5,
    },
    "track_reproj_02": {
        **BASE_TRACKING,
        "tracker_reproj_factor_weight": 0.2,
    },
    # Increase match geometry weight in tracker
    "track_geom_05": {
        **BASE_TRACKING,
        "tracker_match_geom_factor_weight": 0.5,
    },
    # TEASER++ outlier rejection
    "track_teaser_pmc": {
        **BASE_TRACKING,
        "teaser_tracker_inlier_selection_mode": "pmc_exact",
    },
    "track_teaser_noise10": {
        **BASE_TRACKING,
        "teaser_noise_bound_multiplier": 10.0,
    },

    # === PHASE 3: BACKEND STABILITY ===
    # iSAM solver parameters
    "track_isam_wildfire_1e4": {
        **BASE_TRACKING,
        "isam_wildfire_threshold": 1.0e-4,
    },
    "track_isam_relin_true": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
    },
    # More aggressive keyframe descriptor threshold
    "track_desc_inlier_02": {
        **BASE_TRACKING,
        "new_kf_max_desc_inlier_ratio": 0.2,
    },
    "track_desc_inlier_06": {
        **BASE_TRACKING,
        "new_kf_max_desc_inlier_ratio": 0.6,
    },

    # === PHASE 4: BEST COMBOS FROM PHASES 1-3 ===
    # Conservative LM + stronger geometric constraints
    "track_stable_conservative": {
        **BASE_TRACKING,
        "tracking_init_damp": 5.0e-4,
        "tracker_reproj_factor_weight": 0.5,
        "tracking_min_grad_thresh": 1.0e-5,
    },
    # More iterations + conservative optimizer
    "track_stable_iters": {
        **BASE_TRACKING,
        "tracking_max_num_iters": 80,
        "tracking_init_damp": 5.0e-4,
    },
    # Full stabilization: conservative LM + geometry + backend
    "track_full_stable": {
        **BASE_TRACKING,
        "tracking_init_damp": 5.0e-4,
        "tracker_reproj_factor_weight": 0.5,
        "isam_wildfire_threshold": 1.0e-4,
        "tracking_min_grad_thresh": 1.0e-5,
    },
    # Best tracking base + inlier085 (was 146 tracked)
    "track_base_inlier085": {
        **BASE_TRACKING,
        "new_kf_max_inlier_ratio": 0.85,
        "pho_num_samples": 2048,
    },

    # === PHASE 5: Combine best tracking findings ===
    # isam_relin (140 tracked) + damp_5e4 (123 tracked)
    "track_relin_damp5e4": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracking_init_damp": 5.0e-4,
    },
    # isam_relin + stable_conservative (117 tracked, 4.98mm)
    "track_relin_conservative": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracking_init_damp": 5.0e-4,
        "tracker_reproj_factor_weight": 0.5,
        "tracking_min_grad_thresh": 1.0e-5,
    },
    # isam_relin + damp_5e4 + grad_1e5 (both helped tracking)
    "track_relin_damp_grad": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracking_init_damp": 5.0e-4,
        "tracking_min_grad_thresh": 1.0e-5,
    },
    # isam_relin + reproj_02 (80 tracked, 4.94mm - gentle geometric constraint)
    "track_relin_reproj02": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracker_reproj_factor_weight": 0.2,
    },
    # isam_relin + damp + reproj02 (combine all gentle improvements)
    "track_relin_damp_reproj02": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracking_init_damp": 5.0e-4,
        "tracker_reproj_factor_weight": 0.2,
    },
    # Kitchen sink: all winners together
    "track_relin_damp_grad_reproj02": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracking_init_damp": 5.0e-4,
        "tracking_min_grad_thresh": 1.0e-5,
        "tracker_reproj_factor_weight": 0.2,
    },
    # isam_relin + jac_5e2 (81 tracked, 4.33mm)
    "track_relin_jac5e2": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracking_jac_update_err_inc_threshold": 5.0e-2,
    },
    # Full combination: relin + damp + grad + jac + reproj
    "track_ultimate": {
        **BASE_TRACKING,
        "isam_partial_relin_check": "true",
        "tracking_init_damp": 5.0e-4,
        "tracking_min_grad_thresh": 1.0e-5,
        "tracking_jac_update_err_inc_threshold": 5.0e-2,
        "tracker_reproj_factor_weight": 0.2,
    },
}

COMBO_DIR = VSLAM_LAB / "tuning_sageslam_camcalib" / "combo"
COMBO_CSV = COMBO_DIR / "combo_results.csv"
COMBO_MD = VSLAM_LAB / "SAGESLAM_CAMCALIB_COMBO.md"


def run_combo_tuning(dry_run=False):
    """Run combo parameter experiments for SAGE-SLAM."""
    COMBO_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    csv_fields = ["run_id", "combo_name", "changes", "ate_rmse_mm", "ate_mean_mm",
                   "ate_median_mm", "n_tracked", "n_evaluated", "run_time", "elapsed"]

    # Run baseline first
    print("=" * 70)
    print("COMBO BASELINE: Running SAGE-SLAM with default parameters")
    print("=" * 70)

    restore_flags()
    baseline_name = "sage_combo_baseline"

    # Check if baseline already has results
    rmse, mean, median, n_tracked, n_eval = get_ate_stats(baseline_name)
    if rmse is not None and not dry_run:
        print(f"  BASELINE (cached): ATE RMSE = {rmse:.2f} mm, tracked {n_tracked}/541")
        baseline_result = {
            "run_id": 0, "combo_name": "baseline", "changes": "defaults",
            "ate_rmse_mm": rmse, "ate_mean_mm": mean, "ate_median_mm": median,
            "n_tracked": n_tracked, "n_evaluated": n_eval,
            "run_time": get_run_time(baseline_name), "elapsed": 0,
        }
        all_results.append(baseline_result)
        baseline_rmse = rmse
    elif not dry_run:
        configs_dir = COMBO_DIR / "configs"
        configs_dir.mkdir(parents=True, exist_ok=True)
        exp_yaml = configs_dir / f"exp_{baseline_name}.yaml"
        create_exp_yaml(baseline_name, exp_yaml)

        start = time.time()
        run_and_eval(str(exp_yaml))
        elapsed = time.time() - start

        rmse, mean, median, n_tracked, n_eval = get_ate_stats(baseline_name)
        run_time = get_run_time(baseline_name)

        baseline_result = {
            "run_id": 0, "combo_name": "baseline", "changes": "defaults",
            "ate_rmse_mm": rmse, "ate_mean_mm": mean, "ate_median_mm": median,
            "n_tracked": n_tracked, "n_evaluated": n_eval,
            "run_time": run_time, "elapsed": elapsed,
        }
        all_results.append(baseline_result)
        baseline_rmse = rmse
        if rmse is not None:
            print(f"\n  BASELINE: ATE RMSE = {rmse:.2f} mm, tracked {n_tracked}/541")
        else:
            print(f"\n  BASELINE: FAIL")
    else:
        baseline_rmse = 4.79

    # Run each combo (skip already-completed experiments)
    run_id = 1
    skipped = 0
    for combo_name, param_changes in COMBO_CONFIGS.items():
        changes_str = ", ".join(f"{k}={v}" for k, v in param_changes.items())
        exp_name = f"sage_combo_{combo_name}"

        # Check if this experiment already has results
        existing_rmse, existing_mean, existing_median, existing_tracked, existing_eval = get_ate_stats(exp_name)
        if existing_rmse is not None:
            print(f"\n  SKIP: {combo_name} (already completed: {existing_rmse:.2f} mm, {existing_tracked} tracked)")
            result = {
                "run_id": run_id, "combo_name": combo_name, "changes": changes_str,
                "ate_rmse_mm": existing_rmse, "ate_mean_mm": existing_mean,
                "ate_median_mm": existing_median, "n_tracked": existing_tracked,
                "n_evaluated": existing_eval, "run_time": get_run_time(exp_name), "elapsed": 0,
            }
            all_results.append(result)
            run_id += 1
            skipped += 1
            continue

        print(f"\n{'='*70}")
        print(f"COMBO: {combo_name}")
        print(f"  Changes: {changes_str}")
        print(f"{'='*70}")

        if dry_run:
            print(f"  [DRY RUN] Would run {combo_name}")
            continue

        restore_flags()
        for param_name, value in param_changes.items():
            modify_flags_file(param_name, value)

        configs_dir = COMBO_DIR / "configs"
        configs_dir.mkdir(parents=True, exist_ok=True)
        exp_yaml = configs_dir / f"exp_{exp_name}.yaml"
        create_exp_yaml(exp_name, exp_yaml)

        start = time.time()
        run_and_eval(str(exp_yaml))
        elapsed = time.time() - start

        rmse, mean, median, n_tracked, n_eval = get_ate_stats(exp_name)
        run_time = get_run_time(exp_name)

        result = {
            "run_id": run_id, "combo_name": combo_name, "changes": changes_str,
            "ate_rmse_mm": rmse, "ate_mean_mm": mean, "ate_median_mm": median,
            "n_tracked": n_tracked, "n_evaluated": n_eval,
            "run_time": run_time, "elapsed": elapsed,
        }
        all_results.append(result)
        run_id += 1

        if rmse is not None and baseline_rmse is not None:
            delta = rmse - baseline_rmse
            print(f"  Result: ATE RMSE = {rmse:.2f} mm ({delta:+.2f}), tracked {n_tracked}/541")
        else:
            print(f"  Result: FAIL (tracked {n_tracked}/541)" if n_tracked else "  Result: FAIL")

    print(f"\nSkipped {skipped} already-completed experiments")

    restore_flags()
    print("\nRestored original slam_run.flags")

    # Save CSV
    with open(COMBO_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for r in all_results:
            row = {}
            for k in csv_fields:
                v = r.get(k, "")
                if isinstance(v, float) and k.startswith("ate_"):
                    row[k] = f"{v:.2f}" if v is not None else ""
                else:
                    row[k] = v
            writer.writerow(row)
    print(f"CSV saved to {COMBO_CSV}")

    # Generate combo MD report
    generate_combo_md(all_results, baseline_rmse)


def generate_combo_md(all_results, baseline_rmse):
    ts = datetime.now().strftime("%Y-%m-%d")
    md = []
    md.append("# SAGE-SLAM Combination Tuning: camcalib Dataset")
    md.append(f"\n**Generated:** {ts}")
    md.append("**Dataset:** camcalib / 2-2 (frames 0-541, 1374x1371 px, 30 Hz endoscopy)")
    md.append("**Method:** SAGE-SLAM-DEV (monocular, Docker)")
    md.append("**Metric:** ATE RMSE in mm (Sim3 alignment via `evo_ape -as`)")
    md.append("**Strategy:** Test parameter combinations based on ablation study findings")
    md.append("")
    md.append("---")
    md.append("")

    md.append("## All Results (sorted by ATE RMSE)")
    md.append("")
    md.append("| # | Combo | ATE RMSE (mm) | vs Baseline | Tracked | Reliable |")
    md.append("|---|-------|---------------|-------------|---------|----------|")

    valid = [r for r in all_results if r["ate_rmse_mm"] is not None]
    sorted_results = sorted(valid, key=lambda x: x["ate_rmse_mm"])
    for i, r in enumerate(sorted_results):
        rmse = r["ate_rmse_mm"]
        tracked = r.get("n_tracked", "N/A")
        reliable = "YES" if (tracked and tracked >= 50) else "NO"
        if baseline_rmse and baseline_rmse > 0:
            delta = ((rmse - baseline_rmse) / baseline_rmse) * 100
            delta_str = f"{delta:+.1f}%"
        else:
            delta_str = "N/A"
        md.append(f"| {i+1} | `{r['combo_name']}` | {rmse:.2f} | {delta_str} | {tracked} | {reliable} |")

    md.append("")
    md.append("---")
    md.append("")

    # Best reliable combo
    reliable = [r for r in valid if r.get("n_tracked") and r["n_tracked"] >= 50]
    if reliable:
        best = min(reliable, key=lambda x: x["ate_rmse_mm"])
        md.append("## Best Reliable Configuration")
        md.append("")
        md.append(f"**Combo:** `{best['combo_name']}`")
        md.append(f"**ATE RMSE:** {best['ate_rmse_mm']:.2f} mm")
        md.append(f"**Tracked:** {best['n_tracked']}/541 frames")
        md.append(f"**Changes:** {best['changes']}")
        md.append("")

    # Best tracking combo (among those not worse than 2x baseline)
    good_tracking = [r for r in valid if r.get("n_tracked") and r["n_tracked"] >= 100
                     and baseline_rmse and r["ate_rmse_mm"] < baseline_rmse * 2]
    if good_tracking:
        best_track = max(good_tracking, key=lambda x: x["n_tracked"])
        md.append("## Best Tracking Configuration (ATE < 2x baseline)")
        md.append("")
        md.append(f"**Combo:** `{best_track['combo_name']}`")
        md.append(f"**ATE RMSE:** {best_track['ate_rmse_mm']:.2f} mm")
        md.append(f"**Tracked:** {best_track['n_tracked']}/541 frames")
        md.append(f"**Changes:** {best_track['changes']}")
        md.append("")

    md.append("---")
    md.append("")
    md.append("## Parameter Details")
    md.append("")
    for r in sorted_results:
        md.append(f"### `{r['combo_name']}`")
        md.append(f"- Changes: {r['changes']}")
        rmse = r['ate_rmse_mm']
        md.append(f"- ATE RMSE: {rmse:.2f} mm" if rmse else "- ATE RMSE: FAIL")
        md.append(f"- Tracked: {r.get('n_tracked', 'N/A')}/541")
        md.append("")

    with open(COMBO_MD, "w") as f:
        f.write("\n".join(md))
    print(f"\nCombo report saved to {COMBO_MD}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="Regenerate report from existing evaluation data")
    parser.add_argument("--combo", action="store_true",
                        help="Run combo parameter tuning")
    args = parser.parse_args()

    if args.report_only:
        regenerate_report()
        return

    if args.combo:
        run_combo_tuning(dry_run=args.dry_run)
        return

    TUNING_DIR.mkdir(parents=True, exist_ok=True)

    # Backup original flags file
    if not FLAGS_BACKUP.exists():
        shutil.copy2(FLAGS_FILE, FLAGS_BACKUP)
        print(f"Backed up flags to {FLAGS_BACKUP}")

    all_results = []
    run_id = 0
    csv_fields = ["run_id", "param_name", "value", "default", "exp_name",
                   "ate_rmse_mm", "ate_mean_mm", "ate_median_mm",
                   "n_tracked", "n_evaluated", "run_time", "elapsed"]

    # First run the baseline (default config)
    print("=" * 70)
    print("BASELINE: Running SAGE-SLAM with default parameters")
    print("=" * 70)

    restore_flags()
    baseline_name = "sage_ablation_baseline"

    if not args.dry_run:
        configs_dir = TUNING_DIR / "configs"
        configs_dir.mkdir(parents=True, exist_ok=True)
        exp_yaml = configs_dir / f"exp_{baseline_name}.yaml"
        create_exp_yaml(baseline_name, exp_yaml)

        start = time.time()
        run_and_eval(str(exp_yaml))
        elapsed = time.time() - start

        rmse, mean, median, n_tracked, n_eval = get_ate_stats(baseline_name)
        run_time = get_run_time(baseline_name)

        baseline_result = {
            "run_id": run_id,
            "param_name": "baseline",
            "value": "-",
            "default": "-",
            "exp_name": baseline_name,
            "ate_rmse_mm": rmse,
            "ate_mean_mm": mean,
            "ate_median_mm": median,
            "n_tracked": n_tracked,
            "n_evaluated": n_eval,
            "run_time": run_time,
            "elapsed": elapsed,
        }
        all_results.append(baseline_result)
        run_id += 1

        baseline_rmse = rmse
        if rmse is not None:
            print(f"\n  BASELINE: ATE RMSE = {rmse:.2f} mm, tracked {n_tracked}/541 frames")
        else:
            print(f"\n  BASELINE: FAIL (no ATE produced, tracked {n_tracked}/541 frames)")
    else:
        baseline_rmse = 7.33  # known from previous run

    # Run single-parameter ablation
    for param_name, values in CANDIDATES.items():
        default_val = DEFAULTS[param_name]
        print(f"\n{'='*70}")
        print(f"PARAMETER: {param_name} (default: {default_val})")
        print(f"  Testing values: {values}")
        print(f"{'='*70}")

        for value in values:
            if value == default_val:
                continue

            # Format experiment name
            val_str = str(value).replace(".", "p").replace("-", "n").replace("+", "")
            exp_name = f"sage_ablation_{param_name}_{val_str}"

            print(f"\n  Testing: {param_name} = {value}")

            if args.dry_run:
                print(f"    [DRY RUN] Would run {exp_name}")
                continue

            # Restore baseline flags, then modify the single parameter
            restore_flags()
            modify_flags_file(param_name, value)

            configs_dir = TUNING_DIR / "configs"
            configs_dir.mkdir(parents=True, exist_ok=True)
            exp_yaml = configs_dir / f"exp_{exp_name}.yaml"
            create_exp_yaml(exp_name, exp_yaml)

            start = time.time()
            run_and_eval(str(exp_yaml))
            elapsed = time.time() - start

            rmse, mean, median, n_tracked, n_eval = get_ate_stats(exp_name)
            run_time = get_run_time(exp_name)

            result = {
                "run_id": run_id,
                "param_name": param_name,
                "value": value,
                "default": default_val,
                "exp_name": exp_name,
                "ate_rmse_mm": rmse,
                "ate_mean_mm": mean,
                "ate_median_mm": median,
                "n_tracked": n_tracked,
                "n_evaluated": n_eval,
                "run_time": run_time,
                "elapsed": elapsed,
            }
            all_results.append(result)
            run_id += 1

            if rmse is not None and baseline_rmse is not None:
                delta = rmse - baseline_rmse
                pct = (delta / baseline_rmse) * 100
                print(f"  Result: ATE RMSE = {rmse:.2f} mm ({delta:+.2f} mm, {pct:+.1f}%), tracked {n_tracked}/541")
            else:
                print(f"  Result: FAIL (tracked {n_tracked}/541)" if n_tracked else "  Result: FAIL")

    # Restore original flags
    restore_flags()
    print("\nRestored original slam_run.flags")

    # Save CSV
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for r in all_results:
            row = {}
            for k in csv_fields:
                v = r.get(k, "")
                if isinstance(v, float) and k.startswith("ate_"):
                    row[k] = f"{v:.2f}" if v is not None else ""
                else:
                    row[k] = v
            writer.writerow(row)
    print(f"CSV saved to {RESULTS_CSV}")

    # Generate MD report
    generate_md(all_results, baseline_rmse)

    print(f"\n{'='*70}")
    print("ABLATION STUDY COMPLETE")
    print(f"{'='*70}")


def generate_md(all_results, baseline_rmse):
    ts = datetime.now().strftime("%Y-%m-%d")
    md = []
    md.append("# SAGE-SLAM Single-Parameter Ablation: camcalib Dataset")
    md.append(f"\n**Generated:** {ts}")
    md.append("**Dataset:** camcalib / 2-2 (541 frames, 1374x1371 px, 30 Hz endoscopy)")
    md.append("**Method:** SAGE-SLAM-DEV (monocular, Docker)")
    md.append("**Metric:** ATE RMSE in mm (Sim3 alignment via `evo_ape -as`)")
    md.append("**Strategy:** One parameter at a time vs default configuration")
    md.append("")
    md.append("---")
    md.append("")

    # Summary of best per parameter
    md.append("## Summary: Best Value per Parameter")
    md.append("")
    md.append("| Parameter | Default | Best Value | ATE RMSE (mm) | vs Baseline | Tracked |")
    md.append("|-----------|---------|------------|---------------|-------------|---------|")

    # Group by parameter
    from collections import defaultdict
    by_param = defaultdict(list)
    for r in all_results:
        if r["param_name"] != "baseline":
            by_param[r["param_name"]].append(r)

    baseline_row = next((r for r in all_results if r["param_name"] == "baseline"), None)
    if baseline_row and baseline_row["ate_rmse_mm"] is not None:
        md.append(f"| *baseline* | - | - | **{baseline_row['ate_rmse_mm']:.2f}** | - | {baseline_row.get('n_tracked', 'N/A')} |")

    param_bests = []
    for param_name in CANDIDATES:
        results = by_param.get(param_name, [])
        valid = [r for r in results if r["ate_rmse_mm"] is not None]
        if not valid:
            md.append(f"| `{param_name}` | `{DEFAULTS[param_name]}` | - | FAIL | - | - |")
            continue
        best = min(valid, key=lambda x: x["ate_rmse_mm"])
        rmse = best["ate_rmse_mm"]
        if baseline_rmse and baseline_rmse > 0:
            delta_pct = ((rmse - baseline_rmse) / baseline_rmse) * 100
            delta_str = f"{delta_pct:+.1f}%"
        else:
            delta_str = "N/A"
        tracked = best.get("n_tracked", "N/A")
        md.append(f"| `{param_name}` | `{DEFAULTS[param_name]}` | **`{best['value']}`** | {rmse:.2f} | {delta_str} | {tracked} |")
        param_bests.append((param_name, best["value"], rmse))

    md.append("")
    md.append("---")
    md.append("")

    # Detailed results per parameter
    md.append("## Detailed Results")
    md.append("")

    for param_name in CANDIDATES:
        results = by_param.get(param_name, [])
        if not results:
            continue

        md.append(f"### `{param_name}` (default: `{DEFAULTS[param_name]}`)")
        md.append("")
        md.append("| Value | ATE RMSE (mm) | ATE Mean (mm) | Tracked | vs Baseline |")
        md.append("|-------|---------------|---------------|---------|-------------|")

        sorted_results = sorted(results, key=lambda x: x["ate_rmse_mm"] if x["ate_rmse_mm"] is not None else 999)
        for r in sorted_results:
            rmse = r["ate_rmse_mm"]
            mean = r["ate_mean_mm"]
            tracked = r.get("n_tracked", "N/A")
            if rmse is not None:
                if baseline_rmse and baseline_rmse > 0:
                    delta = ((rmse - baseline_rmse) / baseline_rmse) * 100
                    delta_str = f"{delta:+.1f}%"
                else:
                    delta_str = "N/A"
                mean_str = f"{mean:.2f}" if mean is not None else "N/A"
                md.append(f"| `{r['value']}` | {rmse:.2f} | {mean_str} | {tracked} | {delta_str} |")
            else:
                md.append(f"| `{r['value']}` | FAIL | - | {tracked} | - |")

        md.append("")

    md.append("---")
    md.append("")

    # Reliability note
    MIN_TRACKED = 50
    md.append("## Reliability Note")
    md.append("")
    md.append(f"Results with fewer than **{MIN_TRACKED} tracked frames** are marked as unreliable.")
    md.append("Low-tracking configs may report artificially low ATE because the alignment")
    md.append("is computed on very few poses that happen to be near the start of the trajectory.")
    md.append("")
    md.append("---")
    md.append("")

    # Top improvements (all)
    md.append("## Top Improvements — All (sorted by ATE RMSE)")
    md.append("")
    md.append("| # | Parameter | Value | ATE RMSE (mm) | vs Baseline | Tracked | Reliable |")
    md.append("|---|-----------|-------|---------------|-------------|---------|----------|")

    valid_results = [r for r in all_results if r["ate_rmse_mm"] is not None and r["param_name"] != "baseline"]
    sorted_all = sorted(valid_results, key=lambda x: x["ate_rmse_mm"])
    for i, r in enumerate(sorted_all[:15]):
        rmse = r["ate_rmse_mm"]
        if baseline_rmse and baseline_rmse > 0:
            delta = ((rmse - baseline_rmse) / baseline_rmse) * 100
            delta_str = f"{delta:+.1f}%"
        else:
            delta_str = "N/A"
        tracked = r.get("n_tracked", "N/A")
        reliable = "YES" if (tracked and tracked >= MIN_TRACKED) else "NO"
        md.append(f"| {i+1} | `{r['param_name']}` | `{r['value']}` | {rmse:.2f} | {delta_str} | {tracked} | {reliable} |")

    md.append("")
    md.append("---")
    md.append("")

    # Top improvements (reliable only: >= MIN_TRACKED frames)
    md.append(f"## Top Improvements — Reliable Only (>={MIN_TRACKED} tracked frames)")
    md.append("")
    md.append("| # | Parameter | Value | ATE RMSE (mm) | vs Baseline | Tracked |")
    md.append("|---|-----------|-------|---------------|-------------|---------|")

    reliable_results = [r for r in valid_results if r.get("n_tracked") and r["n_tracked"] >= MIN_TRACKED]
    sorted_reliable = sorted(reliable_results, key=lambda x: x["ate_rmse_mm"])
    for i, r in enumerate(sorted_reliable[:10]):
        rmse = r["ate_rmse_mm"]
        if baseline_rmse and baseline_rmse > 0:
            delta = ((rmse - baseline_rmse) / baseline_rmse) * 100
            delta_str = f"{delta:+.1f}%"
        else:
            delta_str = "N/A"
        tracked = r.get("n_tracked", "N/A")
        md.append(f"| {i+1} | `{r['param_name']}` | `{r['value']}` | {rmse:.2f} | {delta_str} | {tracked} |")

    md.append("")
    md.append("---")
    md.append("")

    # Combo candidates analysis
    md.append("## Recommended Combo Candidates")
    md.append("")
    md.append("Parameters that improved ATE while maintaining reasonable tracking (>= 50 frames),")
    md.append("ranked by best value per parameter:")
    md.append("")
    md.append("| Priority | Parameter | Value | ATE RMSE (mm) | vs Baseline | Tracked |")
    md.append("|----------|-----------|-------|---------------|-------------|---------|")

    combo_candidates = []
    for param_name in CANDIDATES:
        results = by_param.get(param_name, [])
        reliable = [r for r in results if r["ate_rmse_mm"] is not None
                    and r.get("n_tracked") and r["n_tracked"] >= MIN_TRACKED]
        improved = [r for r in reliable if baseline_rmse and r["ate_rmse_mm"] < baseline_rmse]
        if improved:
            best = min(improved, key=lambda x: x["ate_rmse_mm"])
            combo_candidates.append(best)

    combo_candidates.sort(key=lambda x: x["ate_rmse_mm"])
    for i, r in enumerate(combo_candidates):
        rmse = r["ate_rmse_mm"]
        delta = ((rmse - baseline_rmse) / baseline_rmse) * 100
        md.append(f"| {i+1} | `{r['param_name']}` | `{r['value']}` | {rmse:.2f} | {delta:+.1f}% | {r['n_tracked']} |")

    md.append("")

    with open(RESULTS_MD, "w") as f:
        f.write("\n".join(md))
    print(f"\nReport saved to {RESULTS_MD}")


if __name__ == "__main__":
    main()
