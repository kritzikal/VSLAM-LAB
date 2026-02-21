#!/usr/bin/env python3
"""Parameter tuning script for OneSLAM on camcalib dataset.

Systematically tests one parameter at a time, running OneSLAM via the
VSLAM-LAB pipeline and recording ATE RMSE for each configuration.

Usage:
    pixi run -e vslamlab python tune_oneslam_camcalib.py [--param PARAM_NAME] [--dry-run]
"""

import argparse
import copy
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

# Paths
VSLAM_LAB = Path(__file__).parent.resolve()
ONESLAM_DEV = VSLAM_LAB / "Baselines" / "OneSLAM-DEV"
BENCHMARK = Path(os.path.expanduser("~/VSLAM-LAB-Benchmark"))
EVALUATION = Path(os.path.expanduser("~/VSLAM-LAB-Evaluation"))
SETTINGS_YAML = ONESLAM_DEV / "vslamlab_oneslam-dev_settings.yaml"
TUNING_DIR = VSLAM_LAB / "tuning_camcalib"
RESULTS_MD = VSLAM_LAB / "ONESLAM_CAMCALIB_TUNING.md"
RESULTS_CSV = TUNING_DIR / "tuning_results.csv"

# Default frame range: frames 0-541
DEFAULT_RGB_IDX = [0, 541]

# Experiment config template
EXP_TEMPLATE = {
    "Config": "config_camcalib.yaml",
    "NumRuns": 1,
    "Parameters": {"verbose": 1, "mode": "mono", "rgb_idx": DEFAULT_RGB_IDX},
    "Module": "oneslam-dev",
}

# Baseline settings (safe defaults for camcalib)
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

# Parameters to sweep (one at a time, all others at baseline)
PARAM_SWEEP = {
    "keyframe_subsample": [2, 4, 6, 8],
    "depth_scale": [1.0, 3.0, 5.0, 10.0],
    "tracking_ba_iterations": [5, 10, 20, 30],
    "local_ba_size": [5, 10, 20, 30],
    "section_length": [8, 13, 16],
    "tracked_point_num_min": [50, 100, 200, 400],
    "point_sampler": ["uniform", "sift", "orb", "r2d2"],
    "pose_guesser": ["last_pose", "constant_velocity"],
    "global_ba_iterations": [0, 5, 10],
    "cotracker_model": [
        "cotracker_stride_4_wind_8",
        "cotracker_stride_4_wind_12",
    ],
}

# CoTracker model -> window size mapping
COTRACKER_WINDOW_MAP = {
    "cotracker_stride_4_wind_8": 8,
    "cotracker_stride_4_wind_12": 12,
    "cotracker_stride_8_wind_16": 16,
}


def m_to_mm(val_m):
    """Convert meters to millimeters."""
    return val_m * 1000.0


def create_settings_yaml(settings, output_path):
    """Write OneSLAM settings to a YAML file."""
    with open(output_path, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)


def create_exp_yaml(exp_name, output_path, rgb_idx=None):
    """Create a VSLAM-LAB experiment YAML file."""
    exp = copy.deepcopy(EXP_TEMPLATE)
    if rgb_idx:
        exp["Parameters"]["rgb_idx"] = rgb_idx
    config = {exp_name: exp}
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def run_experiment(exp_yaml_path, overwrite=True):
    """Run a VSLAM-LAB experiment (run + evaluate, skip comparison)."""
    overwrite_flag = "--overwrite" if overwrite else ""

    # Run the experiment
    cmd = f"pixi run -e vslamlab vslamlab {exp_yaml_path} {overwrite_flag}"
    print(f"\n{'='*60}")
    print(f"Running: {cmd}")
    print(f"{'='*60}")

    # Use Popen so we can kill stuck comparison steps
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"  # prevent matplotlib from trying to open a GUI
    result = subprocess.run(
        cmd, shell=True, cwd=str(VSLAM_LAB),
        capture_output=False, text=True, timeout=1800, env=env
    )
    return True  # Don't rely on return code; check ATE later


def evaluate_experiment(exp_yaml_path, overwrite=True):
    """Evaluate a VSLAM-LAB experiment."""
    overwrite_flag = "--overwrite" if overwrite else ""
    cmd = f"pixi run -e vslamlab evaluate {exp_yaml_path} {overwrite_flag}"
    print(f"Evaluating: {cmd}")
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    result = subprocess.run(
        cmd, shell=True, cwd=str(VSLAM_LAB),
        capture_output=False, text=True, timeout=300, env=env
    )
    return result.returncode == 0


def get_ate_rmse(exp_name):
    """Extract ATE RMSE from evaluation results (in meters)."""
    eval_dir = EVALUATION / exp_name / "CAMCALIB" / "2-2" / "vslamlab_evaluation"
    ate_csv = eval_dir / "ate.csv"
    if not ate_csv.exists():
        return None, None, None

    import pandas as pd
    df = pd.read_csv(ate_csv)
    if df.empty:
        return None, None, None

    rmse = df["rmse"].values[0] if "rmse" in df.columns else None
    mean = df["mean"].values[0] if "mean" in df.columns else None
    median = df["median"].values[0] if "median" in df.columns else None
    return rmse, mean, median


def get_tracking_stats(exp_name):
    """Get tracking statistics from experiment log."""
    log_csv = EVALUATION / exp_name / "vslamlab_exp_log.csv"
    if not log_csv.exists():
        return None, None, None

    import pandas as pd
    df = pd.read_csv(log_csv)
    if df.empty:
        return None, None, None

    success = df["SUCCESS"].values[0] if "SUCCESS" in df.columns else None
    run_time = df["TIME"].values[0] if "TIME" in df.columns else None
    comments = df["COMMENTS"].values[0] if "COMMENTS" in df.columns else ""
    return success, run_time, comments


def run_single_config(param_name, param_value, run_id, rgb_idx=None, dry_run=False):
    """Run OneSLAM with a single parameter configuration.

    Returns a dict with results or None if skipped.
    """
    # Build settings
    settings = copy.deepcopy(BASELINE_SETTINGS)
    if param_name != "baseline":
        settings[param_name] = param_value

    # Handle cotracker_model -> window_size coupling
    if param_name == "cotracker_model":
        settings["cotracker_window_size"] = COTRACKER_WINDOW_MAP[param_value]

    # Validate: keyframe_subsample < section_length
    if settings["keyframe_subsample"] >= settings["section_length"]:
        print(f"SKIP: keyframe_subsample ({settings['keyframe_subsample']}) >= section_length ({settings['section_length']})")
        return None

    # Create experiment name
    exp_name = f"tune_{run_id:03d}_{param_name}_{param_value}"
    exp_name = exp_name.replace(".", "p").replace(" ", "_")
    print(f"\n{'#'*60}")
    print(f"Config: {exp_name}")
    print(f"  {param_name} = {param_value}")
    print(f"{'#'*60}")

    if dry_run:
        return {"run_id": run_id, "param_name": param_name,
                "param_value": param_value, "exp_name": exp_name,
                "status": "dry_run"}

    # Create settings YAML
    settings_dir = TUNING_DIR / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / f"{exp_name}_settings.yaml"
    create_settings_yaml(settings, settings_path)

    # Copy settings to the OneSLAM-DEV default location
    shutil.copy2(settings_path, SETTINGS_YAML)

    # Create experiment YAML
    configs_dir = TUNING_DIR / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    exp_yaml_path = configs_dir / f"exp_{exp_name}.yaml"
    create_exp_yaml(exp_name, exp_yaml_path, rgb_idx=rgb_idx)

    # Run experiment (includes evaluation via vslamlab pipeline)
    start_time = time.time()
    try:
        run_experiment(str(exp_yaml_path), overwrite=True)
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT: {exp_name}")
    elapsed = time.time() - start_time

    # The vslamlab pipeline already runs evaluation. Try to also run it
    # explicitly in case the pipeline was interrupted during comparison.
    try:
        evaluate_experiment(str(exp_yaml_path), overwrite=True)
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Always try to get ATE RMSE (evaluation may have succeeded even if
    # the comparison step hung or the pipeline returned non-zero)
    rmse_m, mean_m, median_m = get_ate_rmse(exp_name)

    success_status, run_time_log, comments_log = get_tracking_stats(exp_name)

    # Convert to mm for display
    rmse_mm = m_to_mm(rmse_m) if rmse_m is not None else None
    mean_mm = m_to_mm(mean_m) if mean_m is not None else None
    median_mm = m_to_mm(median_m) if median_m is not None else None

    result = {
        "run_id": run_id,
        "param_name": param_name,
        "param_value": str(param_value),
        "exp_name": exp_name,
        "success": bool(success_status) if success_status is not None else False,
        "run_time": f"{run_time_log:.1f}" if run_time_log else "N/A",
        "ate_rmse_mm": f"{rmse_mm:.2f}" if rmse_mm is not None else "FAIL",
        "ate_mean_mm": f"{mean_mm:.2f}" if mean_mm is not None else "N/A",
        "ate_median_mm": f"{median_mm:.2f}" if median_mm is not None else "N/A",
        "comments": str(comments_log) if comments_log else "",
        "elapsed": f"{elapsed:.1f}",
    }

    print(f"\nResult: ATE RMSE = {result['ate_rmse_mm']} mm, Time = {result['run_time']}s")
    return result


def save_result(result, results_csv):
    """Append a result to the CSV file."""
    file_exists = results_csv.exists()
    fieldnames = ["run_id", "param_name", "param_value", "exp_name",
                  "success", "run_time", "ate_rmse_mm", "ate_mean_mm",
                  "ate_median_mm", "comments", "elapsed"]
    with open(results_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(result)


def generate_results_md(results, output_path):
    """Generate a comprehensive Markdown report from tuning results."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = []
    md.append("# OneSLAM Parameter Tuning: camcalib Dataset")
    md.append(f"\n**Generated:** {timestamp}")
    md.append(f"**Dataset:** camcalib / 2-2 (frames 0-541, 1374x1371, 30 Hz)")
    md.append(f"**Method:** OneSLAM-DEV (monocular)")
    md.append(f"**Metric:** ATE RMSE in mm (with Sim3 alignment)")
    md.append("")

    md.append("## Baseline Configuration")
    md.append("")
    md.append("| Parameter | Value |")
    md.append("|-----------|-------|")
    for k, v in sorted(BASELINE_SETTINGS.items()):
        md.append(f"| `{k}` | `{v}` |")
    md.append("")

    # Find baseline RMSE
    baseline_rmse_mm = None
    for r in results:
        if r["param_name"] == "baseline" and r.get("ate_rmse_mm", "FAIL") != "FAIL":
            baseline_rmse_mm = float(r["ate_rmse_mm"])
            break

    # Find best overall result
    successful = [r for r in results if r.get("ate_rmse_mm", "FAIL") != "FAIL"]
    if successful:
        best = min(successful, key=lambda r: float(r["ate_rmse_mm"]))
        md.append("## Best Result")
        md.append("")
        md.append(f"- **ATE RMSE:** {best['ate_rmse_mm']} mm")
        md.append(f"- **Parameter:** `{best['param_name']}` = `{best['param_value']}`")
        md.append(f"- **Run time:** {best['run_time']}s")
        if baseline_rmse_mm:
            improvement = ((baseline_rmse_mm - float(best['ate_rmse_mm'])) / baseline_rmse_mm) * 100
            md.append(f"- **vs Baseline:** {improvement:+.1f}% improvement")
        md.append("")

    # Group results by parameter
    param_groups = {}
    for r in results:
        pname = r["param_name"]
        if pname not in param_groups:
            param_groups[pname] = []
        param_groups[pname].append(r)

    # Baseline result
    if "baseline" in param_groups:
        md.append("## Baseline Result")
        md.append("")
        br = param_groups["baseline"][0]
        md.append(f"| ATE RMSE (mm) | ATE Mean (mm) | ATE Median (mm) | Run Time (s) |")
        md.append(f"|---------------|---------------|-----------------|--------------|")
        md.append(f"| {br.get('ate_rmse_mm', 'N/A')} | {br.get('ate_mean_mm', 'N/A')} | {br.get('ate_median_mm', 'N/A')} | {br.get('run_time', 'N/A')} |")
        md.append("")

    md.append("## Results by Parameter")
    md.append("")

    for param_name in PARAM_SWEEP:
        if param_name not in param_groups:
            continue
        group = param_groups[param_name]

        md.append(f"### `{param_name}`")
        md.append("")
        md.append(f"Baseline value: `{BASELINE_SETTINGS[param_name]}`")
        md.append("")
        md.append("| Value | ATE RMSE (mm) | ATE Mean (mm) | Run Time (s) | Status |")
        md.append("|-------|---------------|---------------|--------------|--------|")

        for r in group:
            val = r["param_value"]
            rmse = r.get("ate_rmse_mm", "FAIL")
            mean = r.get("ate_mean_mm", "N/A")
            rtime = r.get("run_time", "N/A")
            is_baseline = str(r["param_value"]) == str(BASELINE_SETTINGS[param_name])
            marker = " **(baseline)**" if is_baseline else ""
            status = "OK" if r.get("success") else "FAIL"
            if r.get("comments") and str(r["comments"]) != "nan":
                status += f" - {str(r['comments'])[:50]}"
            md.append(f"| `{val}`{marker} | {rmse} | {mean} | {rtime} | {status} |")

        # Find best for this parameter
        group_ok = [r for r in group if r.get("ate_rmse_mm", "FAIL") != "FAIL"]
        if group_ok:
            best_in_group = min(group_ok, key=lambda r: float(r["ate_rmse_mm"]))
            md.append(f"\nBest: `{param_name}` = `{best_in_group['param_value']}` (RMSE: {best_in_group['ate_rmse_mm']} mm)")
        md.append("")

    # Summary table
    md.append("## Summary: Optimal Values")
    md.append("")
    md.append("| Parameter | Optimal Value | ATE RMSE (mm) | vs Baseline |")
    md.append("|-----------|---------------|---------------|-------------|")

    for param_name in PARAM_SWEEP:
        if param_name not in param_groups:
            continue
        group_ok = [r for r in param_groups[param_name] if r.get("ate_rmse_mm", "FAIL") != "FAIL"]
        if group_ok:
            best_r = min(group_ok, key=lambda r: float(r["ate_rmse_mm"]))
            rmse_val = float(best_r["ate_rmse_mm"])
            if baseline_rmse_mm:
                diff = ((rmse_val - baseline_rmse_mm) / baseline_rmse_mm) * 100
                diff_str = f"{diff:+.1f}%"
            else:
                diff_str = "N/A"
            md.append(f"| `{param_name}` | `{best_r['param_value']}` | {best_r['ate_rmse_mm']} | {diff_str} |")

    md.append("")
    md.append("## Notes")
    md.append("")
    md.append("- Each test changes ONE parameter from baseline, keeping all others fixed")
    md.append("- ATE RMSE computed with Sim3 alignment (evo_ape -as) and reported in mm")
    md.append("- Lower ATE RMSE is better")
    md.append("- Monocular scale ambiguity is handled by Sim3 alignment")
    md.append("- Frame range: 0-541 of camcalib sequence 2-2")

    with open(output_path, "w") as f:
        f.write("\n".join(md))
    print(f"\nResults saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="OneSLAM parameter tuning on camcalib")
    parser.add_argument("--param", type=str, default=None,
                        help="Only tune this specific parameter")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print configs without running")
    parser.add_argument("--rgb-idx", type=int, nargs=2, default=DEFAULT_RGB_IDX,
                        help="Frame range to use (default: 0 541)")
    parser.add_argument("--skip-baseline", action="store_true",
                        help="Skip the baseline run")
    args = parser.parse_args()

    TUNING_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing results if any
    results = []
    if RESULTS_CSV.exists():
        import pandas as pd
        df = pd.read_csv(RESULTS_CSV)
        results = df.to_dict("records")

    run_id = len(results)

    # Run baseline first
    if not args.skip_baseline:
        print("\n" + "=" * 60)
        print("RUNNING BASELINE CONFIGURATION")
        print("=" * 60)
        result = run_single_config(
            "baseline", "default", run_id,
            rgb_idx=args.rgb_idx, dry_run=args.dry_run
        )
        if result:
            results.append(result)
            if not args.dry_run:
                save_result(result, RESULTS_CSV)
            run_id += 1

    # Determine which parameters to sweep
    params_to_test = PARAM_SWEEP
    if args.param:
        if args.param not in PARAM_SWEEP:
            print(f"Unknown parameter: {args.param}")
            print(f"Available: {list(PARAM_SWEEP.keys())}")
            sys.exit(1)
        params_to_test = {args.param: PARAM_SWEEP[args.param]}

    # Run parameter sweep
    for param_name, values in params_to_test.items():
        print(f"\n{'='*60}")
        print(f"SWEEPING PARAMETER: {param_name}")
        print(f"Values: {values}")
        print(f"{'='*60}")

        for value in values:
            result = run_single_config(
                param_name, value, run_id,
                rgb_idx=args.rgb_idx, dry_run=args.dry_run
            )
            if result:
                results.append(result)
                if not args.dry_run:
                    save_result(result, RESULTS_CSV)
                run_id += 1

    # Generate MD report
    generate_results_md(results, RESULTS_MD)
    print(f"\nTuning complete. {len(results)} configurations tested.")
    print(f"Results: {RESULTS_MD}")


if __name__ == "__main__":
    main()
