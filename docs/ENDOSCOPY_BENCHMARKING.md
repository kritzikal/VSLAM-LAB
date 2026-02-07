# Endoscopy SLAM Benchmarking with VSLAMLAB

This document describes how to benchmark SLAM systems for nasal/surgical endoscopy
using the VSLAMLAB pipeline. Two endoscopy-specialized SLAM baselines (SAGE-SLAM and
OneSLAM) are integrated alongside general-purpose baselines (MASt3R-SLAM, DROID-SLAM)
for comprehensive comparison.

## Overview

### SLAM Baselines

| Baseline    | Paper                | Year | Type          | Input  | Key Feature                        |
|-------------|----------------------|------|---------------|--------|------------------------------------|
| SAGE-SLAM   | Liu et al., ICRA     | 2022 | Endoscopy     | Mono   | Appearance + geometry priors       |
| OneSLAM     | Teufel et al., IPCAI | 2024 | Endoscopy     | Mono   | TAP-based tracking, multi-domain   |
| MASt3R-SLAM | Leroy et al.         | 2024 | General       | Mono   | Foundation model dense matching    |
| DROID-SLAM  | Teed & Deng, NeurIPS | 2021 | General       | Mono   | Differentiable dense BA            |

### Datasets with Ground Truth

| Dataset  | Domain       | GT Poses | GT Depth | Sequences | Frames   |
|----------|-------------|----------|----------|-----------|----------|
| C3VD     | Colonoscopy | 6-DoF    | 16-bit   | 22        | 10,015   |
| EndoSLAM | GI-tract    | 6-DoF    | Synthetic| 35        | 42,700+  |
| Hamlyn   | Laparoscopic| Partial  | Stereo   | 2+        | Variable |

### Metrics

All metrics are computed using VSLAMLAB's built-in evaluation functions:

- **Accuracy (ATE)**: Absolute Trajectory Error RMSE in metres, computed via `evo_ape`
- **Robustness**: Ratio of successfully tracked frames to total frames
- **Runtime**: Processing time in ms/frame and total seconds
- **Memory**: Peak GPU, RAM, and SWAP memory usage in GB

## Quick Start

### 1. Prerequisites

Ensure VSLAMLAB is set up with pixi:

```bash
# Set benchmark and evaluation paths
pixi run -e vslamlab set-benchmark-path /path/to/data
pixi run -e vslamlab set-evaluation-path /path/to/results
```

### 2. Quick Test (recommended first)

Run a quick benchmark on Hamlyn sequences (200 frames, 1 run per baseline):

```bash
pixi run -e vslamlab vslamlab configs/exp_endoscopy_quick.yaml
pixi run -e vslamlab evaluate configs/exp_endoscopy_quick.yaml
pixi run -e vslamlab compare configs/exp_endoscopy_quick.yaml
```

### 3. Full Benchmark

Run the full endoscopy benchmark (3 runs per baseline, all sequences):

```bash
pixi run -e vslamlab vslamlab configs/exp_endoscopy_benchmark.yaml
pixi run -e vslamlab evaluate configs/exp_endoscopy_benchmark.yaml
pixi run -e vslamlab compare configs/exp_endoscopy_benchmark.yaml
```

Or use the orchestration script:

```bash
python run_endoscopy_benchmark.py          # Full benchmark
python run_endoscopy_benchmark.py --quick  # Quick test
```

## Dataset Setup

### Hamlyn (automatic download)

Hamlyn sequences are hosted on HuggingFace and download automatically via VSLAMLAB.

### C3VD (manual download required)

1. Visit https://durrlab.github.io/C3VD/
2. Download sequences and place them in `VSLAM-LAB-Benchmark/C3VD/`
3. Expected structure per sequence:
   ```
   C3VD/
   └── cecum_t1_a/
       ├── color/          # RGB frames
       ├── depth/          # Depth maps (16-bit, mm)
       ├── pose/           # 4x4 transformation matrices
       └── camera_params.txt  # Optional intrinsics
   ```
4. The dataset module will automatically:
   - Rename `color/` to `rgb_0/`
   - Create `rgb.csv` with timestamps
   - Convert pose matrices to `groundtruth.csv` (TUM format)
   - Create `calibration.yaml`

### EndoSLAM (manual download required)

1. Visit https://data.mendeley.com/datasets/cd2rtzm23r/1
2. Download the HighCam sequences
3. Place them in `VSLAM-LAB-Benchmark/ENDOSLAM/`
4. Expected structure per sequence:
   ```
   ENDOSLAM/
   └── Colon_Traj1_HighCam/
       ├── Frames/         # RGB frames
       └── Poses/          # Ground truth poses
   ```

## Baseline Setup

### SAGE-SLAM

SAGE-SLAM requires Docker for its full C++ build. The VSLAMLAB integration
supports both a Python API mode and a CLI fallback:

```bash
# Clone and install (dev mode)
pixi run -e sageslam-dev git-clone
pixi run -e sageslam-dev install
```

**Requirements**: NVIDIA GPU with CUDA 12+, ~5 GB VRAM minimum.

**Reference**: Liu et al., "SAGE-SLAM: SLAM with Appearance and Geometry Prior
for Endoscopy", ICRA 2022. https://arxiv.org/abs/2202.09487

### OneSLAM

OneSLAM is Python-based and uses the CoTracker TAP model:

```bash
# Clone and install (dev mode)
pixi run -e oneslam-dev git-clone
pixi run -e oneslam-dev install
```

**Requirements**: NVIDIA GPU with ~5 GB VRAM, ~7 min per sequence on RTX 6000.

**Reference**: Teufel et al., "OneSLAM to map them all", IPCAI 2024.
https://link.springer.com/article/10.1007/s11548-024-03171-6

## Experiment Configuration

### Experiment YAML Structure

```yaml
exp_<name>:
  Config: config_endoscopy.yaml    # Dataset sequences to evaluate
  NumRuns: 3                       # Number of repetitions
  Parameters:
    verbose: 1
    mode: 'mono'
  Module: <baseline-name>         # Baseline module identifier
```

### Available Configs

| File                           | Description                              |
|--------------------------------|------------------------------------------|
| `config_endoscopy.yaml`       | All endoscopy datasets                   |
| `config_endoscopy_gt.yaml`    | Only datasets with ground truth poses    |
| `config_hamlyn_endoscopy.yaml`| Hamlyn sequences only                    |
| `exp_endoscopy_benchmark.yaml`| Full benchmark experiment                |
| `exp_endoscopy_quick.yaml`    | Quick test experiment                    |
| `comp_endoscopy.yaml`         | Comparison config (all metrics enabled)  |

## Evaluation and Comparison

### Built-in Metrics

VSLAMLAB automatically computes:

1. **ATE (Absolute Trajectory Error)**: Aligns estimated trajectory with ground
   truth using Umeyama alignment, then computes RMSE of translational errors.

2. **Tracked Frames**: Number of frames where the SLAM system produced a valid
   pose estimate, indicating robustness.

3. **Processing Time**: Wall-clock time for the complete SLAM execution, reported
   both as total seconds and per-frame milliseconds.

4. **Memory Usage**: Peak incremental GPU, RAM, and SWAP memory during execution,
   measured via nvidia-smi and psutil.

### Comparison Outputs

The comparison step generates (`comp_endoscopy.yaml` enables all):

| Output                      | Description                                     |
|-----------------------------|-------------------------------------------------|
| `rmse_boxplot.pdf`          | ATE RMSE distribution per sequence              |
| `rmse_boxplot_shared_scale.pdf` | Same with shared Y-axis scale             |
| `rmse_radar.pdf`            | Radar chart of relative accuracy                |
| `rmse_cummulated_error.pdf` | Cumulative error distribution                   |
| `trajectories.pdf`          | 2D trajectory overlays (PCA-projected)          |
| `num_frames_boxplot.pdf`    | Tracked/total frame ratios                      |
| `canvas_sequences.png`      | Sample thumbnails from each sequence            |
| `TIME_num_frames_table.tex` | LaTeX: processing time per frame                |
| `TIME_total_table.tex`      | LaTeX: total processing time                    |
| `memory_usage_table.tex`    | LaTeX: GPU/RAM/SWAP breakdown                   |

## Interpreting Results

### Accuracy-Robustness-Runtime Trade-offs

When comparing endoscopy SLAM systems, consider:

1. **Accuracy vs. Robustness**: A system with low ATE but many lost frames may
   be less useful than one with moderate ATE but consistent tracking.

2. **Accuracy vs. Runtime**: Real-time endoscopy requires <33 ms/frame (30 Hz).
   Systems that sacrifice speed for accuracy may not be practical for
   intraoperative use.

3. **Domain Specificity**: SAGE-SLAM and OneSLAM are designed for endoscopy and
   may handle challenges (specular reflections, deformable tissue, limited
   texture) better than general-purpose systems.

4. **Memory Constraints**: Surgical systems often have limited GPU memory.
   Compare peak GPU usage across baselines.

### Endoscopy-Specific Challenges

Endoscopic SLAM faces unique challenges not present in standard benchmarks:
- Specular highlights from wet tissue surfaces
- Deformable scene geometry (breathing, tool interaction)
- Limited field of view and texture
- Rapid camera motion and frequent occlusions
- Scale ambiguity in monocular setups

## Adding New Baselines

Follow the VSLAMLAB baseline integration pattern:

1. Create `Baselines/baseline_<name>.py` extending `BaselineVSLAMLab`
2. Create a wrapper script `vslamlab_<name>_mono.py`
3. Register in `Baselines/get_baseline.py`
4. Add pixi environment in `pixi.toml`

See existing baselines (DROID-SLAM, MASt3R-SLAM) for reference.

## Adding New Datasets

1. Create `Datasets/dataset_<name>.py` extending `DatasetVSLAMLab`
2. Create `Datasets/dataset_<name>.yaml` with sequence names
3. Register in `Datasets/get_dataset.py`
4. Add sequences to the appropriate config YAML

Key requirements:
- `rgb_0/` folder with RGB images
- `rgb.csv` with timestamps and paths
- `calibration.yaml` with camera intrinsics
- `groundtruth.csv` with poses (ts, tx, ty, tz, qx, qy, qz, qw)

## References

```bibtex
@inproceedings{liu2022sage,
  title={SAGE-SLAM: SLAM with Appearance and Geometry Prior for Endoscopy},
  author={Liu, Xingtong and Li, Zhaoshuo and Ishii, Masaru and
          Hager, Gregory D. and Taylor, Russell H. and Unberath, Mathias},
  booktitle={IEEE International Conference on Robotics and Automation (ICRA)},
  year={2022}
}

@article{teufel2024oneslam,
  title={OneSLAM to map them all: a generalized approach to SLAM for monocular
         endoscopic imaging based on tracking any point},
  author={Teufel, T. and Shu, H. and others},
  journal={International Journal of Computer Assisted Radiology and Surgery},
  year={2024}
}

@article{bobrow2023c3vd,
  title={Colonoscopy 3D video dataset with paired depth from 2D-3D registration},
  author={Bobrow, Taylor L. and others},
  journal={Medical Image Analysis},
  year={2023}
}

@article{ozyoruk2021endoslam,
  title={EndoSLAM dataset and an unsupervised monocular visual odometry and
         depth estimation approach for endoscopic videos},
  author={Ozyoruk, Kutsev Bengisu and others},
  journal={Medical Image Analysis},
  year={2021}
}
```
