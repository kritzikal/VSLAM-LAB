# CLAUDE.md - VSLAM-LAB Codebase Guide

## Project Overview

VSLAM-LAB is a comprehensive Visual SLAM benchmarking framework that provides a unified interface for running, evaluating, and comparing 20+ SLAM/SfM baselines across 33+ datasets. It manages reproducible experiments via YAML configurations and uses [pixi](https://prefix.dev/) for environment and dependency management.

**Key domains:** monocular SLAM, stereo SLAM, RGB-D SLAM, visual-inertial SLAM, structure-from-motion, depth estimation, and endoscopy-specific SLAM.

## Repository Structure

```
VSLAM-LAB/
├── Baselines/                  # SLAM baseline implementations (20+ systems)
│   ├── BaselineVSLAMLab.py     # Abstract base class for all baselines
│   ├── get_baseline.py         # Factory function (registry pattern)
│   ├── baseline_utilities.py   # CSV logging helpers
│   ├── baseline_*.py           # Concrete baseline implementations
│   ├── kinematic_constraints/  # Endoscopy kinematic constraint module
│   └── extra-files/            # Support scripts (depth estimation, feature extraction)
│
├── Datasets/                   # Dataset implementations (33+ sources)
│   ├── DatasetVSLAMLab.py      # Abstract base class for all datasets
│   ├── get_dataset.py          # Factory function (registry pattern)
│   ├── dataset_utilities.py    # Image processing, CSV utilities
│   ├── dataset_calibration.py  # Calibration YAML generation helpers
│   ├── dataset_*.py            # Concrete dataset implementations
│   └── extra-files/            # Templates, converters (video, rosbag)
│
├── Run/                        # Execution orchestration
│   ├── run_functions.py        # run_sequence() - core execution pipeline
│   ├── downsample_rgb_frames.py # Frame selection / downsampling
│   └── ablations.py            # Parameter variation experiments
│
├── Evaluate/                   # Evaluation and comparison
│   ├── evaluate_functions.py   # evaluate_sequence() - main evaluation pipeline
│   ├── evo_functions.py        # EVO toolkit integration (ATE, RPE metrics)
│   ├── align_trajectories.py   # Horn method trajectory alignment
│   ├── compare_functions.py    # Cross-experiment comparison
│   ├── metrics.py              # Custom metrics (RMSE ATE, recall)
│   ├── plot_functions.py       # Visualization (boxplots, radar, trajectories)
│   ├── evaluate_ablation_study.py # Ablation analysis and reporting
│   └── clean_experiment.py     # Data cleanup utility
│
├── configs/                    # YAML configuration files
│   ├── config_*.yaml           # Dataset/sequence selection configs
│   ├── exp_*.yaml              # Experiment definitions
│   └── comp_*.yaml             # Comparison group definitions
│
├── docs/                       # Documentation and diagrams
│
├── pixi.toml                   # Environment manager (19 environments, tasks, deps)
├── pixi.lock                   # Locked dependency versions
├── vslamlab_gui.py             # CLI entry point / command dispatcher (30+ commands)
├── vslamlab_utilities.py       # Core pipeline logic (run/evaluate/compare orchestration)
├── utilities.py                # General helpers (YAML, file I/O, trajectory I/O)
├── path_constants.py           # Directory paths and global constants
├── run_endoscopy_benchmark.py  # Specialized endoscopy benchmark orchestrator
├── check_cuda.py               # GPU/CUDA diagnostic tool
└── git-clone.sh                # Helper script for baseline cloning
```

## Architecture and Design Patterns

### Factory Pattern (Registries)
- **Baselines:** `Baselines/get_baseline.py` maps string names to baseline classes via a `switcher` dict.
- **Datasets:** `Datasets/get_dataset.py` maps string names to dataset classes via a `switcher` dict.
- When adding a new baseline or dataset, register it in the corresponding `get_*.py` file.

### Template Method Pattern
- **`BaselineVSLAMLab`** defines the baseline lifecycle: `git_clone()` -> `install()` -> `build_execute_command()` -> `execute()`.
- **`DatasetVSLAMLab`** defines the download pipeline via `download_process()`: `download_sequence_data()` -> `create_rgb_folder()` -> `create_rgb_csv()` -> `create_imu_csv()` -> `create_calibration_yaml()` -> `create_groundtruth_csv()` -> `remove_unused_files()`.
- Concrete implementations override these abstract methods.

### Baseline Types
- **C++ baselines** (ORB-SLAM2/3, COLMAP, GLOMAP, DSO, etc.): Use `build_execute_command_cpp()` with `key:value` parameter format.
- **Python baselines** (DROID-SLAM, DPVO, MonoGS, MASt3R-SLAM, etc.): Use `build_execute_command_python()` with `--key value` parameter format.
- **Dev variants** (`*-dev`): Build from source locally instead of using conda packages. Check for compiled artifacts.

### Execution Pipeline
```
pixi run vslamlab <exp_yaml>
  1. validate_experiment_yaml()     # Check YAML syntax and semantics
  2. get_experiment_resources()     # Auto-install baselines, download datasets
  3. run_exp()                      # Execute baselines on sequences
  4. evaluate_exp()                 # Compute ATE/RPE via EVO
  5. compare_exp()                  # Generate comparison plots/tables
```

## Key Conventions

### Configuration Files

**Config files** (`configs/config_*.yaml`) define dataset-sequence selections:
```yaml
eth:
  - table_3
  - cables_1
rgbdtum:
  - rgbd_dataset_freiburg1_xyz
```

**Experiment files** (`configs/exp_*.yaml`) define experiments:
```yaml
exp_demo_droidslam:
  Config: config_vslamlab.yaml      # Which config file to use
  NumRuns: 1                         # Repetitions per sequence
  Parameters: {verbose: 1, mode: mono}
  Module: droidslam                  # Baseline module name
```

### Standardized Data Formats

All datasets normalize to this directory structure:
```
<BENCHMARK_PATH>/<DATASET_NAME>/<sequence_name>/
├── rgb_0/              # Monocular or left stereo images (*.png)
├── rgb_1/              # (Optional) Right stereo images
├── depth_0/            # (Optional) Depth maps
├── rgb.csv             # Timestamps + image paths
├── imu.csv             # (Optional) IMU measurements: ts,wx,wy,wz,ax,ay,az
├── calibration.yaml    # Camera intrinsics, distortion, IMU params
└── groundtruth.csv     # Ground truth: ts,tx,ty,tz,qx,qy,qz,qw
```

Baseline output goes to:
```
<exp_folder>/<DATASET>/<sequence_name>/
├── XXXXX_KeyFrameTrajectory.txt    # Estimated trajectory per run
├── system_output_XXXXX.txt         # Stdout/stderr log
└── VSLAMLAB-evaluation/            # EVO metrics, aligned trajectories
```

### Path Constants (`path_constants.py`)

Key directories (configurable via pixi tasks):
- `VSLAM_LAB_DIR`: Project root
- `VSLAMLAB_BENCHMARK`: Downloaded dataset storage (default: `../VSLAM-LAB-Benchmark`)
- `VSLAMLAB_EVALUATION`: Evaluation output (default: `../VSLAM-LAB-Evaluation`)
- `VSLAMLAB_BASELINES`: Baseline installations (default: `../VSLAM-LAB-Baselines`)

### Naming Conventions
- Baseline files: `baseline_<name>.py` with class `<NAME>_baseline(BaselineVSLAMLab)`
- Dataset files: `dataset_<name>.py` with class `<NAME>_dataset(DatasetVSLAMLab)`
- Config yamls: `config_<description>.yaml` for dataset selection
- Experiment yamls: `exp_<description>.yaml` for experiment definition
- Dev baselines: append `-dev` to baseline name (e.g., `droidslam-dev`)

## Development Workflow

### Environment Management (pixi)

VSLAM-LAB uses pixi with 19 isolated environments:
```bash
# Core environment
pixi run -e vslamlab <task>

# Baseline-specific environments
pixi run -e droidslam <task>
pixi run -e mast3rslam-dev <task>

# All commands use --frozen flag in production
pixi run --frozen -e <env> <command>
```

### Common pixi Tasks
```bash
# Run full pipeline
pixi run vslamlab configs/exp_vslamlab.yaml

# Quick demo
pixi run demo droidslam eth table_3 mono

# Info commands
pixi run print-baselines
pixi run print-datasets
pixi run baseline-info droidslam

# Resource management
pixi run validate-experiment-yaml configs/exp_*.yaml
pixi run get-experiment-resources configs/exp_*.yaml
pixi run check-experiment-state configs/exp_*.yaml

# Individual pipeline stages
pixi run run-exp configs/exp_*.yaml
pixi run evaluate-exp configs/exp_*.yaml
pixi run compare-exp configs/exp_*.yaml

# Installation
pixi run install-baseline droidslam
pixi run download-dataset eth
```

### Adding a New Baseline

1. Create `Baselines/baseline_<name>.py` inheriting from `BaselineVSLAMLab`
2. Implement: `__init__()`, `build_execute_command()`, `is_installed()`, `git_clone()`
3. Register in `Baselines/get_baseline.py` switcher dict
4. Add pixi environment in `pixi.toml` with dependencies and `execute-*` tasks
5. Optionally create HuggingFace settings YAML at `vslamlab/<name>`

### Adding a New Dataset

1. Create `Datasets/dataset_<name>.py` inheriting from `DatasetVSLAMLab`
2. Create `Datasets/dataset_<name>.yaml` with sequence definitions
3. Implement all abstract methods: `download_sequence_data()`, `create_rgb_folder()`, `create_rgb_csv()`, `create_imu_csv()`, `create_calibration_yaml()`, `create_groundtruth_csv()`, `remove_unused_files()`
4. Register in `Datasets/get_dataset.py` switcher dict
5. Use `Datasets/extra-files/dataset_template.py` as a starting point

## Testing and Validation

- **No formal test suite** (pytest/unittest). Validation is done through:
  - `pixi run validate-experiment-yaml` for config validation
  - `pixi run check-experiment-resources` for dependency verification
  - `check_cuda.py` for GPU/CUDA diagnostics
  - `Baselines/kinematic_constraints/test_constraints.py` for constraint unit tests
- **Experiment tracking:** CSV logs per experiment record success, metrics, resource usage
- **Evaluation:** Uses the [evo](https://github.com/MichaelGrupp/evo) library for ATE/RPE trajectory metrics

## Baseline Inventory

| Baseline | Type | Lang | Modes |
|----------|------|------|-------|
| ORB-SLAM2 | Feature-based | C++ | mono, rgbd, stereo |
| ORB-SLAM3 | Visual-Inertial | C++ | mono-vi |
| DROID-SLAM | Deep Learning | Python | mono, rgbd, stereo |
| DPVO | Deep Visual Odometry | Python | mono |
| MonoGS | Gaussian Splatting | Python | mono |
| DSO | Direct Sparse | C++ | mono |
| AnyFeature | Multi-Feature | C++ | mono |
| OKVIS2 | Visual-Inertial | C++ | mono-vi |
| PyCuVSLAM | CUDA RGB-D | Python | rgbd |
| COLMAP | SfM | C++ | mono |
| GLOMAP | Global SfM | C++ | mono |
| GenSfM | Generalized SfM | C++ | mono |
| DUSt3R | Dense Matching | Python | mono |
| MASt3R | Dense Matching | Python | mono |
| MASt3R-SLAM | Foundation SLAM | Python | mono |
| DepthPro | Depth Estimation | Python | mono |
| VGGT | Visual Geometry | Python | mono |
| SAGE-SLAM | Endoscopy SLAM | Python | mono |
| OneSLAM | Endoscopy SLAM | Python | mono |
| Constrained SLAM | Wrapper | Python | (inherits base) |

## Dataset Categories

- **Standard benchmarks:** ETH, TUM RGB-D, KITTI, EuRoC, Replica, NuIM, TartanAir
- **Structure-from-Motion:** ETH3D, ScanNet++, LaMAR
- **Underwater:** LizardIsland, ReefSLAM, Squidle, NTNU ARL UW, SweetCorals, Yandiwanba
- **Endoscopy:** Hamlyn, C3VD, EndoSLAM
- **Specialized:** Antarctica, Caves, Rover, HILTI, MonoTUM, MadMax, Drunkards
- **Custom:** Videos (generic video-to-frames), ARIEL, S3LI

## Important Implementation Details

- **Memory monitoring:** `BaselineVSLAMLab.execute()` runs a background thread that monitors RAM (95% threshold), GPU, and SWAP (80% threshold), killing processes that exceed limits.
- **Weight management:** Neural network weights are downloaded from HuggingFace Hub and cached locally in baseline directories.
- **Trajectory format:** Output trajectories use TUM format (`timestamp tx ty tz qx qy qz qw`) or KITTI format, written as CSV.
- **Process execution:** All baselines run as subprocesses via pixi with stdout/stderr captured to log files.
- **Ablation system:** `Run/ablations.py` supports parameter sweeps by modifying YAML settings per iteration and optionally adding Gaussian noise to images.
- **Endoscopy pipeline:** `run_endoscopy_benchmark.py` is a self-contained orchestrator for endoscopy-specific benchmarking (Hamlyn, C3VD, EndoSLAM datasets with MASt3R-SLAM, DROID-SLAM, SAGE-SLAM, OneSLAM baselines).
