#!/usr/bin/env python3
"""Greedy forward selection for OneSLAM parameter combinations on camcalib.

Starts with local_ba_size=10 (best single param), then greedily adds the
parameter that gives the best improvement, repeating until no improvement.

Usage:
    pixi run -e vslamlab python tune_oneslam_camcalib_combo.py [--dry-run]
"""

import copy
import csv
import os
import shutil
import subprocess
import time
import yaml
from datetime import datetime
from pathlib import Path

VSLAM_LAB = Path(__file__).parent.resolve()
ONESLAM_DEV = VSLAM_LAB / "Baselines" / "OneSLAM-DEV"
EVALUATION = Path(os.path.expanduser("~/VSLAM-LAB-Evaluation"))
SETTINGS_YAML = ONESLAM_DEV / "vslamlab_oneslam-dev_settings.yaml"
TUNING_DIR = VSLAM_LAB / "tuning_camcalib_combo"
RESULTS_CSV = TUNING_DIR / "combo_results.csv"
RESULTS_MD = VSLAM_LAB / "ONESLAM_CAMCALIB_COMBO.md"

DEFAULT_RGB_IDX = [0, 541]

EXP_TEMPLATE = {
    "Config": "config_camcalib.yaml",
    "NumRuns": 1,
    "Parameters": {"verbose": 1, "mode": "mono", "rgb_idx": DEFAULT_RGB_IDX},
    "Module": "oneslam-dev",
}

BASELINE_SETTINGS = {
    "lumen_mask_low_threshold": 0.05,
    "lumen_mask_high_threshold": 0.95,
    "ransac_localization": True,
    "update_localized_pose": False,
    "depth_scale": 3.0,
    "depth_estimator": "constant",
    "keyframe_subsample": 4,
    "keyframe_decision": "subsample",
    "section_length": 13,
    "past_frame_size": 5,
    "tracking_ba_iterations": 20,
    "local_ba_size": 30,
    "global_ba_iterations": 0,
    "point_sampler": "uniform",
    "pose_guesser": "last_pose",
    "tracked_point_num_min": 200,
    "tracked_point_num_max": 2000,
    "localization_track_num": 50,
    "minimum_new_points": 0,
    "point_resample_cooldown": 1,
    "cotracker_model": "cotracker_stride_4_wind_8",
    "cotracker_window_size": 8,
    "img_width": -1,
    "img_height": -1,
}

# Candidate parameter changes (param_name -> list of values to try)
# Includes optimal values from single-param tuning + nearby values
CANDIDATES = {
    "local_ba_size":          [5, 8, 10, 12, 15],
    "depth_scale":            [0.5, 1.0, 2.0, 3.0, 5.0],
    "point_sampler":          ["uniform", "orb", "sift", "r2d2"],
    "keyframe_subsample":     [2, 3, 4, 6],
    "section_length":         [8, 10, 13, 16],
    "tracking_ba_iterations": [3, 5, 10, 15, 20],
    "tracked_point_num_min":  [50, 100, 150, 200],
}


def m_to_mm(v):
    return v * 1000.0 if v is not None else None


def create_settings_yaml(settings, path):
    with open(path, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)


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
                       capture_output=False, text=True, timeout=1800, env=env)
    except subprocess.TimeoutExpired:
        print("  TIMEOUT during run")
    print(f"  Evaluating: {cmd_eval}")
    try:
        subprocess.run(cmd_eval, shell=True, cwd=str(VSLAM_LAB),
                       capture_output=False, text=True, timeout=300, env=env)
    except Exception:
        pass


def get_ate_rmse_mm(exp_name):
    ate_csv = EVALUATION / exp_name / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "ate.csv"
    if not ate_csv.exists():
        return None
    import pandas as pd
    df = pd.read_csv(ate_csv)
    if df.empty or "rmse" not in df.columns:
        return None
    return m_to_mm(df["rmse"].values[0])


def get_ate_stats_mm(exp_name):
    ate_csv = EVALUATION / exp_name / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "ate.csv"
    if not ate_csv.exists():
        return None, None, None
    import pandas as pd
    df = pd.read_csv(ate_csv)
    if df.empty:
        return None, None, None
    rmse = m_to_mm(df["rmse"].values[0]) if "rmse" in df.columns else None
    mean = m_to_mm(df["mean"].values[0]) if "mean" in df.columns else None
    median = m_to_mm(df["median"].values[0]) if "median" in df.columns else None
    return rmse, mean, median


def get_run_time(exp_name):
    log_csv = EVALUATION / exp_name / "vslamlab_exp_log.csv"
    if not log_csv.exists():
        return None
    import pandas as pd
    df = pd.read_csv(log_csv)
    if df.empty or "TIME" not in df.columns:
        return None
    return df["TIME"].values[0]


def run_config(exp_name, settings, dry_run=False):
    if dry_run:
        return None

    settings_dir = TUNING_DIR / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / f"{exp_name}_settings.yaml"
    create_settings_yaml(settings, settings_path)
    shutil.copy2(settings_path, SETTINGS_YAML)

    configs_dir = TUNING_DIR / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    exp_yaml_path = configs_dir / f"exp_{exp_name}.yaml"
    create_exp_yaml(exp_name, exp_yaml_path)

    start = time.time()
    run_and_eval(str(exp_yaml_path))
    elapsed = time.time() - start

    rmse, mean, median = get_ate_stats_mm(exp_name)
    run_time = get_run_time(exp_name)

    return {
        "exp_name": exp_name,
        "ate_rmse_mm": rmse,
        "ate_mean_mm": mean,
        "ate_median_mm": median,
        "run_time": run_time,
        "elapsed": elapsed,
    }


def settings_valid(settings):
    """Check parameter constraints."""
    if settings["keyframe_subsample"] >= settings["section_length"]:
        return False
    return True


def describe_changes(settings):
    """Return a list of (param, value) that differ from baseline."""
    changes = []
    for k in sorted(CANDIDATES.keys()):
        if settings[k] != BASELINE_SETTINGS[k]:
            changes.append((k, settings[k]))
    return changes


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    TUNING_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    run_id = 0
    csv_fields = ["run_id", "round", "exp_name", "changes", "ate_rmse_mm",
                   "ate_mean_mm", "ate_median_mm", "run_time", "elapsed"]

    # Start with local_ba_size=10 as our anchor (known best: 6.76 mm)
    current_settings = copy.deepcopy(BASELINE_SETTINGS)
    current_settings["local_ba_size"] = 10
    current_best_rmse = 6.76  # known from previous testing
    current_changes = [("local_ba_size", 10)]

    print("=" * 70)
    print(f"STARTING POINT: local_ba_size=10, ATE RMSE = {current_best_rmse:.2f} mm")
    print("=" * 70)

    # Which parameters are still candidates for addition
    remaining_params = [p for p in CANDIDATES if p != "local_ba_size"]

    round_num = 0
    while remaining_params:
        round_num += 1
        print(f"\n{'='*70}")
        print(f"ROUND {round_num}: Testing {len(remaining_params)} candidate params")
        print(f"Current best: {current_best_rmse:.2f} mm")
        print(f"Current changes: {current_changes}")
        print(f"Candidates: {remaining_params}")
        print(f"{'='*70}")

        round_results = []

        for param_name in remaining_params:
            for value in CANDIDATES[param_name]:
                # Skip if this is the baseline value (no change)
                if value == current_settings[param_name]:
                    continue

                test_settings = copy.deepcopy(current_settings)
                test_settings[param_name] = value

                if not settings_valid(test_settings):
                    print(f"  SKIP: {param_name}={value} (constraint violation)")
                    continue

                safe_val = str(value).replace(".", "p")
                changes_str = "_".join(f"{p}{v}" for p, v in current_changes)
                exp_name = f"combo_r{round_num}_{changes_str}_{param_name}_{safe_val}"
                exp_name = exp_name.replace(".", "p")

                print(f"\n  Testing: {param_name} = {value}")
                print(f"    (on top of: {current_changes})")

                result = run_config(exp_name, test_settings, dry_run=args.dry_run)
                if result is None:
                    continue

                rmse = result["ate_rmse_mm"]
                result["run_id"] = run_id
                result["round"] = round_num
                result["changes"] = str(current_changes + [(param_name, value)])
                run_id += 1

                if rmse is not None:
                    delta = rmse - current_best_rmse
                    print(f"  Result: ATE RMSE = {rmse:.2f} mm ({delta:+.2f} mm vs current best)")
                    round_results.append((param_name, value, rmse, result))
                else:
                    print(f"  Result: FAIL")
                    round_results.append((param_name, value, 999.0, result))

                all_results.append(result)

        if not round_results:
            print(f"\nNo valid candidates in round {round_num}. Stopping.")
            break

        # Find best result this round
        round_results.sort(key=lambda x: x[2])
        best_param, best_val, best_rmse, best_result = round_results[0]

        print(f"\n{'='*70}")
        print(f"ROUND {round_num} BEST: {best_param} = {best_val} -> {best_rmse:.2f} mm")

        if best_rmse < current_best_rmse:
            improvement = current_best_rmse - best_rmse
            print(f"  IMPROVEMENT: {improvement:.2f} mm better than {current_best_rmse:.2f} mm")
            current_best_rmse = best_rmse
            current_settings[best_param] = best_val
            current_changes.append((best_param, best_val))
            remaining_params.remove(best_param)
            print(f"  New config: {current_changes}")
        else:
            print(f"  NO IMPROVEMENT (best was {best_rmse:.2f} vs current {current_best_rmse:.2f})")
            print(f"  Stopping greedy search.")
            break

        # Also print top 3 for context
        print(f"\n  Top results this round:")
        for i, (p, v, r, _) in enumerate(round_results[:5]):
            delta = r - current_best_rmse
            print(f"    {i+1}. {p}={v}: {r:.2f} mm ({delta:+.2f})")

        print(f"{'='*70}")

    # Save all results to CSV
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for r in all_results:
            row = {k: r.get(k, "") for k in csv_fields}
            if row["ate_rmse_mm"] is not None and row["ate_rmse_mm"] != "":
                row["ate_rmse_mm"] = f"{row['ate_rmse_mm']:.2f}" if isinstance(row["ate_rmse_mm"], float) else row["ate_rmse_mm"]
            if row["ate_mean_mm"] is not None and row["ate_mean_mm"] != "":
                row["ate_mean_mm"] = f"{row['ate_mean_mm']:.2f}" if isinstance(row["ate_mean_mm"], float) else row["ate_mean_mm"]
            if row["ate_median_mm"] is not None and row["ate_median_mm"] != "":
                row["ate_median_mm"] = f"{row['ate_median_mm']:.2f}" if isinstance(row["ate_median_mm"], float) else row["ate_median_mm"]
            writer.writerow(row)

    # Generate MD report
    generate_md(all_results, current_changes, current_best_rmse)

    print(f"\n{'='*70}")
    print(f"FINAL BEST: ATE RMSE = {current_best_rmse:.2f} mm")
    print(f"CONFIG: {current_changes}")
    print(f"{'='*70}")


def generate_md(all_results, best_changes, best_rmse):
    ts = datetime.now().strftime("%Y-%m-%d")
    md = []
    md.append("# OneSLAM Combination Tuning: camcalib Dataset")
    md.append(f"\n**Generated:** {ts}")
    md.append("**Dataset:** camcalib / 2-2 (frames 0-541, 1374x1371 px, 30 Hz)")
    md.append("**Method:** OneSLAM-DEV (monocular)")
    md.append("**Metric:** ATE RMSE in mm (Sim3 alignment via `evo_ape -as`)")
    md.append("**Strategy:** Greedy forward selection starting from `local_ba_size=10`")
    md.append("")
    md.append("---")
    md.append("")

    md.append("## Best Configuration Found")
    md.append("")
    md.append(f"**ATE RMSE: {best_rmse:.2f} mm** (baseline: 17.22 mm, improvement: {((17.22 - best_rmse) / 17.22) * 100:.1f}%)")
    md.append("")
    md.append("| Parameter | Value | Baseline |")
    md.append("|-----------|-------|----------|")
    for pname, pval in best_changes:
        md.append(f"| `{pname}` | **`{pval}`** | `{BASELINE_SETTINGS[pname]}` |")
    md.append("")
    md.append("---")
    md.append("")

    # All results table
    md.append("## All Tested Combinations")
    md.append("")
    md.append("| # | Changes | ATE RMSE (mm) | ATE Mean (mm) | Run Time (s) |")
    md.append("|---|---------|---------------|---------------|--------------|")

    for r in sorted(all_results, key=lambda x: x.get("ate_rmse_mm") or 999):
        rmse = r.get("ate_rmse_mm")
        mean = r.get("ate_mean_mm")
        rtime = r.get("run_time")
        rmse_s = f"{rmse:.2f}" if rmse else "FAIL"
        mean_s = f"{mean:.2f}" if mean else "N/A"
        rtime_s = f"{rtime:.0f}" if rtime else "N/A"
        md.append(f"| {r.get('run_id', '')} | {r.get('changes', '')} | {rmse_s} | {mean_s} | {rtime_s} |")

    md.append("")
    md.append("## Recommended Settings YAML")
    md.append("")
    md.append("```yaml")
    rec = copy.deepcopy(BASELINE_SETTINGS)
    for pname, pval in best_changes:
        rec[pname] = pval
    for k in sorted(rec):
        md.append(f"{k}: {rec[k]}")
    md.append("```")
    md.append("")

    with open(RESULTS_MD, "w") as f:
        f.write("\n".join(md))
    print(f"\nReport saved to {RESULTS_MD}")


if __name__ == "__main__":
    main()
