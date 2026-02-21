"""
Module: VSLAM-LAB - check_dataset_vslamlab.py
- Description: Validates and fixes an external dataset directory to conform
               to VSLAM-LAB's expected format.

Usage:
    python check_dataset_vslamlab.py <sequence_path> [--fix]

    --fix   Automatically rewrite files in-place to match VSLAM-LAB format.
            Without --fix, the script only reports issues.
"""

import argparse
import csv
import os
import re
import sys

SCRIPT_LABEL = "\033[95m[check_dataset_vslamlab]\033[0m "
OK = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"
FIXED = "\033[93mFIXED\033[0m"


def check_directory_structure(sequence_path):
    """Check that required directories and files exist."""
    issues = []

    rgb_0 = os.path.join(sequence_path, "rgb_0")
    if not os.path.isdir(rgb_0):
        issues.append("Missing directory: rgb_0/")
    else:
        images = [f for f in os.listdir(rgb_0)
                  if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        if not images:
            issues.append("rgb_0/ exists but contains no images (.png/.jpg)")
        else:
            print(f"  rgb_0/           {OK}  ({len(images)} images)")

    for name in ("rgb.csv", "calibration.yaml"):
        path = os.path.join(sequence_path, name)
        if not os.path.isfile(path):
            issues.append(f"Missing file: {name}")
        else:
            print(f"  {name:<18s} {OK}")

    gt = os.path.join(sequence_path, "groundtruth.csv")
    if os.path.isfile(gt):
        print(f"  groundtruth.csv  {OK}")
    else:
        print(f"  groundtruth.csv  \033[93mOPTIONAL (not found)\033[0m")

    return issues


# ---------------------------------------------------------------------------
# rgb.csv
# ---------------------------------------------------------------------------
EXPECTED_RGB_HEADER = ["ts_rgb0 (s)", "path_rgb0"]


def check_rgb_csv(sequence_path, fix):
    """Validate rgb.csv format: comma-separated with correct header."""
    rgb_csv = os.path.join(sequence_path, "rgb.csv")
    if not os.path.isfile(rgb_csv):
        return ["rgb.csv not found"]

    issues = []
    with open(rgb_csv, "r") as f:
        raw = f.read()

    lines = [l for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return ["rgb.csv is empty"]

    # Detect separator and header
    first_line = lines[0]
    has_header = "ts_rgb0" in first_line.lower() or "path_rgb0" in first_line.lower()
    is_comma = "," in first_line
    is_space = not is_comma and " " in first_line

    # Check image extension consistency
    rgb_0 = os.path.join(sequence_path, "rgb_0")
    actual_ext = None
    if os.path.isdir(rgb_0):
        imgs = sorted([f for f in os.listdir(rgb_0)
                       if f.lower().endswith((".png", ".jpg", ".jpeg"))])
        if imgs:
            actual_ext = os.path.splitext(imgs[0])[1]

    if not has_header:
        issues.append("rgb.csv: missing header row (expected: ts_rgb0 (s),path_rgb0)")
    if is_space and not is_comma:
        issues.append("rgb.csv: space-separated instead of comma-separated")

    # Check for extension mismatch in CSV references
    data_start = 1 if has_header else 0
    ext_mismatch = False
    if actual_ext:
        for line in lines[data_start:data_start + 5]:
            parts = line.split(",") if is_comma else line.split()
            if len(parts) >= 2:
                csv_ext = os.path.splitext(parts[1].strip())[1]
                if csv_ext and csv_ext.lower() != actual_ext.lower():
                    ext_mismatch = True
                    issues.append(
                        f"rgb.csv: references '{csv_ext}' but rgb_0/ contains '{actual_ext}' images"
                    )
                    break

    if issues and fix:
        # Rebuild rgb.csv
        rows = []
        for line in lines[data_start:]:
            parts = line.split(",") if is_comma else line.split()
            if len(parts) >= 2:
                ts = parts[0].strip()
                path = parts[1].strip()
                if ext_mismatch and actual_ext:
                    path = os.path.splitext(path)[0] + actual_ext
                rows.append((ts, path))

        with open(rgb_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(EXPECTED_RGB_HEADER)
            for ts, path in rows:
                writer.writerow([ts, path])

        print(f"  rgb.csv format   {FIXED}")
        return []

    return issues


# ---------------------------------------------------------------------------
# calibration.yaml
# ---------------------------------------------------------------------------
KEY_MAP = {
    "Camera.type": "Camera0.model",
    "Camera.fx": "Camera0.fx",
    "Camera.fy": "Camera0.fy",
    "Camera.cx": "Camera0.cx",
    "Camera.cy": "Camera0.cy",
    "Camera.k1": "Camera0.k1",
    "Camera.k2": "Camera0.k2",
    "Camera.k3": "Camera0.k3",
    "Camera.k4": "Camera0.k4",
    "Camera.k5": "Camera0.k5",
    "Camera.k6": "Camera0.k6",
    "Camera.p1": "Camera0.p1",
    "Camera.p2": "Camera0.p2",
    "Camera.width": "Camera0.w",
    "Camera.height": "Camera0.h",
    "Camera.fps": "Camera0.fps",
}

VALUE_MAP = {
    "PinHole": "Pinhole",
    "pinhole": "Pinhole",
    "PINHOLE": "Pinhole",
    "Fisheye": "Fisheye",
    "fisheye": "Fisheye",
}

REMOVE_KEYS = {"Camera.RGB"}


def check_calibration_yaml(sequence_path, fix):
    """Validate calibration.yaml key names."""
    calib_path = os.path.join(sequence_path, "calibration.yaml")
    if not os.path.isfile(calib_path):
        return ["calibration.yaml not found"]

    with open(calib_path, "r") as f:
        raw_lines = f.readlines()

    issues = []
    new_lines = []
    changed = False

    for line in raw_lines:
        stripped = line.strip()

        # Keep YAML header and comments/blanks
        if stripped.startswith("%YAML") or stripped.startswith("#") or not stripped:
            new_lines.append(line)
            continue

        # Check for keys to remove
        key_match = re.match(r"^(\S+)\s*:\s*(.*)", stripped)
        if not key_match:
            new_lines.append(line)
            continue

        key, val = key_match.group(1), key_match.group(2).strip().strip('"').strip("'")

        if key in REMOVE_KEYS:
            issues.append(f"calibration.yaml: unsupported key '{key}' (will remove)")
            changed = True
            continue

        if key in KEY_MAP:
            new_key = KEY_MAP[key]
            issues.append(f"calibration.yaml: '{key}' -> '{new_key}'")
            new_val = VALUE_MAP.get(val, val)
            if new_val != val:
                issues.append(f"calibration.yaml: value '{val}' -> '{new_val}'")
            new_lines.append(f"{new_key}: {new_val}\n")
            changed = True
        else:
            new_lines.append(line)

    if changed and fix:
        with open(calib_path, "w") as f:
            f.writelines(new_lines)
        print(f"  calibration.yaml {FIXED}")
        return []

    return issues


# ---------------------------------------------------------------------------
# groundtruth.csv
# ---------------------------------------------------------------------------
EXPECTED_GT_HEADER = ["ts", "tx", "ty", "tz", "qx", "qy", "qz", "qw"]

GT_HEADER_MAP = {
    "timestamp": "ts",
    "x": "tx",
    "y": "ty",
    "z": "tz",
}


def check_groundtruth_csv(sequence_path, fix):
    """Validate groundtruth.csv header names."""
    gt_path = os.path.join(sequence_path, "groundtruth.csv")
    if not os.path.isfile(gt_path):
        return []  # groundtruth is optional

    with open(gt_path, "r") as f:
        reader = csv.reader(f)
        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            return ["groundtruth.csv is empty"]
        rows = list(reader)

    issues = []
    new_header = []
    header_changed = False

    for col in header:
        mapped = GT_HEADER_MAP.get(col, col)
        if mapped != col:
            issues.append(f"groundtruth.csv: column '{col}' -> '{mapped}'")
            header_changed = True
        new_header.append(mapped)

    if new_header != EXPECTED_GT_HEADER:
        expected_str = ",".join(EXPECTED_GT_HEADER)
        got_str = ",".join(new_header)
        if got_str != expected_str:
            issues.append(
                f"groundtruth.csv: header mismatch (expected: {expected_str}, got: {got_str})"
            )

    if header_changed and fix:
        with open(gt_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(new_header)
            writer.writerows(rows)
        print(f"  groundtruth.csv  {FIXED}")
        return []

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Check (and optionally fix) a dataset directory for VSLAM-LAB compatibility."
    )
    parser.add_argument("sequence_path", help="Path to the sequence directory to check")
    parser.add_argument(
        "--fix", action="store_true",
        help="Automatically rewrite files in-place to match VSLAM-LAB format",
    )
    args = parser.parse_args()

    sequence_path = os.path.abspath(args.sequence_path)
    if not os.path.isdir(sequence_path):
        print(f"{SCRIPT_LABEL}Error: '{sequence_path}' is not a directory")
        sys.exit(1)

    print(f"{SCRIPT_LABEL}Checking: {sequence_path}")
    print(f"{SCRIPT_LABEL}Mode: {'fix' if args.fix else 'check only'}\n")

    # 1. Structure
    print("Directory structure:")
    struct_issues = check_directory_structure(sequence_path)

    # 2. File formats
    print("\nFile format checks:")
    rgb_issues = check_rgb_csv(sequence_path, args.fix)
    calib_issues = check_calibration_yaml(sequence_path, args.fix)
    gt_issues = check_groundtruth_csv(sequence_path, args.fix)

    all_issues = struct_issues + rgb_issues + calib_issues + gt_issues

    print()
    if all_issues:
        print(f"{SCRIPT_LABEL}{FAIL} Found {len(all_issues)} issue(s):\n")
        for issue in all_issues:
            print(f"  - {issue}")
        if not args.fix:
            print(f"\n{SCRIPT_LABEL}Run with --fix to automatically repair format issues.")
        sys.exit(1)
    else:
        print(f"{SCRIPT_LABEL}{OK} Dataset is VSLAM-LAB compatible.")


if __name__ == "__main__":
    main()
