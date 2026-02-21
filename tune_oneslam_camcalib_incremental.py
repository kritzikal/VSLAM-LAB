#!/usr/bin/env python3
"""Incremental parameter tuning for OneSLAM on camcalib dataset.

Starts from baseline and adds one optimal parameter at a time (ordered by
single-parameter improvement), measuring how improvements compound.

Usage:
    pixi run -e vslamlab python tune_oneslam_camcalib_incremental.py [--dry-run]
"""

import copy
import csv
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
EVALUATION = Path(os.path.expanduser("~/VSLAM-LAB-Evaluation"))
SETTINGS_YAML = ONESLAM_DEV / "vslamlab_oneslam-dev_settings.yaml"
TUNING_DIR = VSLAM_LAB / "tuning_camcalib_incremental"
RESULTS_CSV = TUNING_DIR / "incremental_results.csv"
RESULTS_MD = VSLAM_LAB / "ONESLAM_CAMCALIB_INCREMENTAL.md"

DEFAULT_RGB_IDX = [0, 541]

EXP_TEMPLATE = {
    "Config": "config_camcalib.yaml",
    "NumRuns": 1,
    "Parameters": {"verbose": 1, "mode": "mono", "rgb_idx": DEFAULT_RGB_IDX},
    "Module": "oneslam-dev",
}

# Baseline settings
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

# Optimal parameters ordered by single-parameter improvement (best first)
INCREMENTAL_STEPS = [
    ("local_ba_size",          10,     "-60.7%"),
    ("depth_scale",            1.0,    "-58.5%"),
    ("point_sampler",          "r2d2", "-54.8%"),
    ("keyframe_subsample",     6,      "-36.5%"),
    ("section_length",         8,      "-33.4%"),
    ("tracking_ba_iterations", 5,      "-29.7%"),
    ("tracked_point_num_min",  50,     "-29.1%"),
]


def m_to_mm(val_m):
    return val_m * 1000.0


def create_settings_yaml(settings, output_path):
    with open(output_path, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)


def create_exp_yaml(exp_name, output_path):
    config = {exp_name: copy.deepcopy(EXP_TEMPLATE)}
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def run_experiment(exp_yaml_path):
    cmd = f"pixi run -e vslamlab vslamlab {exp_yaml_path} --overwrite"
    print(f"\n{'='*60}")
    print(f"Running: {cmd}")
    print(f"{'='*60}")
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    subprocess.run(cmd, shell=True, cwd=str(VSLAM_LAB),
                   capture_output=False, text=True, timeout=1800, env=env)
    return True


def evaluate_experiment(exp_yaml_path):
    cmd = f"pixi run -e vslamlab evaluate {exp_yaml_path} --overwrite"
    print(f"Evaluating: {cmd}")
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    subprocess.run(cmd, shell=True, cwd=str(VSLAM_LAB),
                   capture_output=False, text=True, timeout=300, env=env)


def get_ate_rmse(exp_name):
    ate_csv = EVALUATION / exp_name / "CAMCALIB" / "2-2" / "vslamlab_evaluation" / "ate.csv"
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
    """Run a single configuration and return results dict."""
    print(f"\n{'#'*60}")
    print(f"Config: {exp_name}")
    print(f"{'#'*60}")

    if dry_run:
        return {"exp_name": exp_name, "ate_rmse_mm": "DRY_RUN"}

    # Write settings
    settings_dir = TUNING_DIR / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / f"{exp_name}_settings.yaml"
    create_settings_yaml(settings, settings_path)
    shutil.copy2(settings_path, SETTINGS_YAML)

    # Write experiment YAML
    configs_dir = TUNING_DIR / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    exp_yaml_path = configs_dir / f"exp_{exp_name}.yaml"
    create_exp_yaml(exp_name, exp_yaml_path)

    start = time.time()
    try:
        run_experiment(str(exp_yaml_path))
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT: {exp_name}")
    elapsed = time.time() - start

    try:
        evaluate_experiment(str(exp_yaml_path))
    except Exception:
        pass

    rmse_m, mean_m, median_m = get_ate_rmse(exp_name)
    run_time = get_run_time(exp_name)

    rmse_mm = m_to_mm(rmse_m) if rmse_m is not None else None
    mean_mm = m_to_mm(mean_m) if mean_m is not None else None
    median_mm = m_to_mm(median_m) if median_m is not None else None

    result = {
        "exp_name": exp_name,
        "ate_rmse_mm": f"{rmse_mm:.2f}" if rmse_mm else "FAIL",
        "ate_mean_mm": f"{mean_mm:.2f}" if mean_mm else "N/A",
        "ate_median_mm": f"{median_mm:.2f}" if median_mm else "N/A",
        "run_time": f"{run_time:.1f}" if run_time else "N/A",
        "elapsed": f"{elapsed:.1f}",
    }
    print(f"\nResult: ATE RMSE = {result['ate_rmse_mm']} mm, Time = {result['run_time']}s")
    return result


def save_results_csv(results, fieldnames, csv_path):
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def generate_md(results):
    """Generate the incremental tuning MD report."""
    ts = datetime.now().strftime("%Y-%m-%d")
    baseline_rmse = float(results[0]["ate_rmse_mm"]) if results[0]["ate_rmse_mm"] != "FAIL" else None

    md = []
    md.append("# OneSLAM Incremental Parameter Tuning: camcalib Dataset")
    md.append(f"\n**Generated:** {ts}")
    md.append("**Dataset:** camcalib / 2-2 (frames 0-541, 1374x1371 px, 30 Hz endoscopy)")
    md.append("**Method:** OneSLAM-DEV (monocular)")
    md.append("**Metric:** ATE RMSE in mm (with Sim3 alignment via `evo_ape -as`)")
    md.append("**Methodology:** Start from baseline, add one optimal parameter at a time (ordered by single-parameter improvement)")
    md.append("")
    md.append("---")
    md.append("")

    # Methodology
    md.append("## Methodology")
    md.append("")
    md.append("Parameters are added incrementally in order of their single-parameter improvement:")
    md.append("")
    for i, (pname, pval, single_imp) in enumerate(INCREMENTAL_STEPS, 1):
        md.append(f"{i}. `{pname}` = `{pval}` (single-param improvement: {single_imp})")
    md.append("")
    md.append("Each step **keeps all previously applied changes** and adds one more.")
    md.append("This reveals parameter interactions and whether improvements compound or conflict.")
    md.append("")
    md.append("---")
    md.append("")

    # Results table
    md.append("## Results")
    md.append("")
    md.append("| Step | Parameter Changed | Value | ATE RMSE (mm) | ATE Mean (mm) | vs Baseline | vs Previous | Cumulative Changes |")
    md.append("|------|-------------------|-------|---------------|---------------|-------------|-------------|-------------------|")

    prev_rmse = baseline_rmse
    cumulative = []
    for i, r in enumerate(results):
        rmse_str = r["ate_rmse_mm"]
        mean_str = r.get("ate_mean_mm", "N/A")

        if i == 0:
            param_changed = "(baseline)"
            value = "-"
            vs_baseline = "-"
            vs_prev = "-"
            cum_str = "none"
        else:
            pname, pval, _ = INCREMENTAL_STEPS[i - 1]
            param_changed = f"`{pname}`"
            value = f"`{pval}`"
            cumulative.append(f"{pname}={pval}")
            cum_str = ", ".join(cumulative)

            if rmse_str != "FAIL" and baseline_rmse:
                rmse_val = float(rmse_str)
                vs_baseline = f"{((rmse_val - baseline_rmse) / baseline_rmse) * 100:+.1f}%"
                if prev_rmse:
                    vs_prev = f"{((rmse_val - prev_rmse) / prev_rmse) * 100:+.1f}%"
                else:
                    vs_prev = "N/A"
            else:
                vs_baseline = "FAIL"
                vs_prev = "FAIL"

        md.append(f"| {i} | {param_changed} | {value} | **{rmse_str}** | {mean_str} | {vs_baseline} | {vs_prev} | {cum_str} |")

        if rmse_str != "FAIL":
            prev_rmse = float(rmse_str)
        else:
            prev_rmse = None

    md.append("")
    md.append("---")
    md.append("")

    # Analysis
    md.append("## Analysis")
    md.append("")

    # Find best step
    valid = [(i, r) for i, r in enumerate(results) if r["ate_rmse_mm"] != "FAIL"]
    if valid:
        best_i, best_r = min(valid, key=lambda x: float(x[1]["ate_rmse_mm"]))
        best_rmse = float(best_r["ate_rmse_mm"])
        md.append(f"**Best result:** Step {best_i} with ATE RMSE = **{best_rmse:.2f} mm**")
        if baseline_rmse:
            total_imp = ((best_rmse - baseline_rmse) / baseline_rmse) * 100
            md.append(f"  (total improvement: **{total_imp:+.1f}%** vs baseline {baseline_rmse:.2f} mm)")
        md.append("")

        if best_i < len(results) - 1:
            md.append(f"Note: Adding parameters beyond step {best_i} degraded performance,")
            md.append(f"suggesting parameter interactions or overfitting to this sequence.")
            md.append("")

    # Parameter interaction notes
    md.append("### Parameter Interactions")
    md.append("")
    md.append("Key observations from incremental stacking:")
    md.append("")

    for i in range(1, len(results)):
        if results[i]["ate_rmse_mm"] == "FAIL":
            pname, pval, single_imp = INCREMENTAL_STEPS[i - 1]
            md.append(f"- **Step {i} (`{pname}={pval}`):** FAILED - this parameter conflicts with previously applied changes")
            continue

        cur_rmse = float(results[i]["ate_rmse_mm"])
        if prev_rmse is not None and i > 0 and results[i-1]["ate_rmse_mm"] != "FAIL":
            prev_step_rmse = float(results[i-1]["ate_rmse_mm"])
            delta = cur_rmse - prev_step_rmse
            pname, pval, single_imp = INCREMENTAL_STEPS[i - 1]
            if delta < -0.5:
                md.append(f"- **Step {i} (`{pname}={pval}`):** Improved by {abs(delta):.2f} mm - compounds well with previous changes")
            elif delta > 0.5:
                md.append(f"- **Step {i} (`{pname}={pval}`):** Worsened by {delta:.2f} mm - conflicts with previous changes (single-param was {single_imp})")
            else:
                md.append(f"- **Step {i} (`{pname}={pval}`):** Marginal effect ({delta:+.2f} mm) - largely redundant with previous changes")

    md.append("")
    md.append("---")
    md.append("")

    # Recommended config
    if valid:
        best_step = best_i
        md.append("## Recommended Configuration")
        md.append("")
        md.append(f"Based on incremental tuning, the optimal configuration uses changes from steps 0-{best_step}:")
        md.append("")
        md.append("| Parameter | Value |")
        md.append("|-----------|-------|")
        rec_settings = copy.deepcopy(BASELINE_SETTINGS)
        for j in range(best_step):
            pname, pval, _ = INCREMENTAL_STEPS[j]
            rec_settings[pname] = pval
        for k in sorted(rec_settings):
            baseline_val = BASELINE_SETTINGS[k]
            cur_val = rec_settings[k]
            marker = " **<-- tuned**" if cur_val != baseline_val else ""
            md.append(f"| `{k}` | `{cur_val}`{marker} |")
        md.append("")

    md.append("## Notes")
    md.append("")
    md.append("- Parameters applied incrementally in order of single-parameter improvement")
    md.append("- ATE RMSE computed with Sim3 alignment (`evo_ape -as`) and reported in mm")
    md.append("- Lower ATE RMSE is better")
    md.append("- Frame range: 0-541 of camcalib sequence 2-2")
    md.append(f"- Total steps tested: {len(results)}")
    md.append("")

    with open(RESULTS_MD, "w") as f:
        f.write("\n".join(md))
    print(f"\nReport saved to {RESULTS_MD}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Incremental OneSLAM tuning on camcalib")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    TUNING_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    csv_fields = ["step", "exp_name", "param_changed", "param_value",
                   "ate_rmse_mm", "ate_mean_mm", "ate_median_mm",
                   "run_time", "elapsed", "cumulative_changes"]

    # Step 0: baseline
    print("\n" + "=" * 60)
    print("STEP 0: BASELINE")
    print("=" * 60)
    settings = copy.deepcopy(BASELINE_SETTINGS)
    result = run_config("incr_000_baseline", settings, dry_run=args.dry_run)
    result["step"] = 0
    result["param_changed"] = "baseline"
    result["param_value"] = "-"
    result["cumulative_changes"] = "none"
    results.append(result)

    # Steps 1-7: add one optimal parameter at a time
    cumulative = []
    for step, (pname, pval, single_imp) in enumerate(INCREMENTAL_STEPS, 1):
        print(f"\n{'='*60}")
        print(f"STEP {step}: Add {pname} = {pval}  (single-param: {single_imp})")
        print(f"Previous changes: {cumulative if cumulative else 'none'}")
        print(f"{'='*60}")

        settings[pname] = pval
        cumulative.append(f"{pname}={pval}")

        # Validate constraints
        if settings["keyframe_subsample"] >= settings["section_length"]:
            print(f"WARNING: keyframe_subsample ({settings['keyframe_subsample']}) >= "
                  f"section_length ({settings['section_length']}), adjusting section_length")
            settings["section_length"] = settings["keyframe_subsample"] + 2

        safe_val = str(pval).replace(".", "p")
        exp_name = f"incr_{step:03d}_{pname}_{safe_val}"
        result = run_config(exp_name, settings, dry_run=args.dry_run)
        result["step"] = step
        result["param_changed"] = pname
        result["param_value"] = str(pval)
        result["cumulative_changes"] = ", ".join(cumulative)
        results.append(result)

    # Save CSV
    save_results_csv(results, csv_fields, RESULTS_CSV)
    print(f"\nCSV saved to {RESULTS_CSV}")

    # Generate MD report
    generate_md(results)

    print(f"\nIncremental tuning complete. {len(results)} steps tested.")


if __name__ == "__main__":
    main()
