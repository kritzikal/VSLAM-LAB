# OneSLAM Incremental Parameter Tuning: camcalib Dataset

**Generated:** 2026-02-17
**Dataset:** camcalib / 2-2 (frames 0-541, 1374x1371 px, 30 Hz endoscopy)
**Method:** OneSLAM-DEV (monocular, CoTracker-based point tracking)
**Metric:** ATE RMSE in mm (with Sim3 alignment via `evo_ape -as`)
**Methodology:** Start from baseline, add one optimal parameter at a time (ordered by single-parameter improvement)

---

## Ground Truth Motion Analysis

The camcalib 2-2 ground truth trajectory was recorded with an EM tracker at 30 Hz.
OneSLAM processes frames 0-541 (18s) of the full 1541-frame (51.4s) recording.

| Metric | Processed (0-18s) | Full (0-51s) | Unit |
|--------|-------------------|--------------|------|
| Total path length | 110.8 | 383.1 | mm |
| Mean speed | 6.16 | 7.30 | mm/s |
| Median speed | 4.58 | 4.52 | mm/s |
| Mean angular velocity | 5.50 | 5.72 | deg/s |
| Workspace range (X/Y/Z) | 4.9 / 76.2 / 12.2 | 17.7 / 76.2 / 30.0 | mm |

> See [COMBO report](ONESLAM_CAMCALIB_COMBO.md) for full motion analysis with
> trajectory visualizations and speed/angular velocity distributions.

---

## Methodology

Parameters are added incrementally in order of their single-parameter improvement:

1. `local_ba_size` = `10` (single-param improvement: -60.7%)
2. `depth_scale` = `1.0` (single-param improvement: -58.5%)
3. `point_sampler` = `r2d2` (single-param improvement: -54.8%)
4. `keyframe_subsample` = `6` (single-param improvement: -36.5%)
5. `section_length` = `8` (single-param improvement: -33.4%)
6. `tracking_ba_iterations` = `5` (single-param improvement: -29.7%)
7. `tracked_point_num_min` = `50` (single-param improvement: -29.1%)

Each step **keeps all previously applied changes** and adds one more.
This reveals parameter interactions and whether improvements compound or conflict.

---

## Results

| Step | Parameter Changed | Value | ATE RMSE (mm) | ATE Mean (mm) | vs Baseline | vs Previous | Cumulative Changes |
|------|-------------------|-------|---------------|---------------|-------------|-------------|-------------------|
| 0 | (baseline) | - | **17.22** | 14.56 | - | - | none |
| 1 | `local_ba_size` | `10` | **6.76** | 6.06 | -60.7% | -60.7% | local_ba_size=10 |
| 2 | `depth_scale` | `1.0` | **7.68** | 6.94 | -55.4% | +13.6% | local_ba_size=10, depth_scale=1.0 |
| 3 | `point_sampler` | `r2d2` | **8.82** | 7.92 | -48.8% | +14.8% | local_ba_size=10, depth_scale=1.0, point_sampler=r2d2 |
| 4 | `keyframe_subsample` | `6` | **9.01** | 8.12 | -47.7% | +2.2% | local_ba_size=10, depth_scale=1.0, point_sampler=r2d2, keyframe_subsample=6 |
| 5 | `section_length` | `8` | **9.14** | 7.98 | -46.9% | +1.4% | local_ba_size=10, depth_scale=1.0, point_sampler=r2d2, keyframe_subsample=6, section_length=8 |
| 6 | `tracking_ba_iterations` | `5` | **12.99** | 11.16 | -24.6% | +42.1% | local_ba_size=10, depth_scale=1.0, point_sampler=r2d2, keyframe_subsample=6, section_length=8, tracking_ba_iterations=5 |
| 7 | `tracked_point_num_min` | `50` | **14.90** | 12.96 | -13.5% | +14.7% | local_ba_size=10, depth_scale=1.0, point_sampler=r2d2, keyframe_subsample=6, section_length=8, tracking_ba_iterations=5, tracked_point_num_min=50 |

---

## Analysis

**Best result:** Step 1 with ATE RMSE = **6.76 mm**
  (total improvement: **-60.7%** vs baseline 17.22 mm)

Note: Adding parameters beyond step 1 degraded performance,
suggesting parameter interactions or overfitting to this sequence.

### Parameter Interactions

Key observations from incremental stacking:

- **Step 1 (`local_ba_size=10`):** Improved by 10.46 mm - compounds well with previous changes
- **Step 2 (`depth_scale=1.0`):** Worsened by 0.92 mm - conflicts with previous changes (single-param was -58.5%)
- **Step 3 (`point_sampler=r2d2`):** Worsened by 1.14 mm - conflicts with previous changes (single-param was -54.8%)
- **Step 4 (`keyframe_subsample=6`):** Marginal effect (+0.19 mm) - largely redundant with previous changes
- **Step 5 (`section_length=8`):** Marginal effect (+0.13 mm) - largely redundant with previous changes
- **Step 6 (`tracking_ba_iterations=5`):** Worsened by 3.85 mm - conflicts with previous changes (single-param was -29.7%)
- **Step 7 (`tracked_point_num_min=50`):** Worsened by 1.91 mm - conflicts with previous changes (single-param was -29.1%)

---

## Recommended Configuration

Based on incremental tuning, the optimal configuration uses changes from steps 0-1:

| Parameter | Value |
|-----------|-------|
| `cotracker_model` | `cotracker_stride_4_wind_8` |
| `cotracker_window_size` | `8` |
| `depth_estimator` | `constant` |
| `depth_scale` | `3.0` |
| `global_ba_iterations` | `0` |
| `img_height` | `-1` |
| `img_width` | `-1` |
| `keyframe_decision` | `subsample` |
| `keyframe_subsample` | `4` |
| `local_ba_size` | `10` **<-- tuned** |
| `localization_track_num` | `50` |
| `lumen_mask_high_threshold` | `0.95` |
| `lumen_mask_low_threshold` | `0.05` |
| `minimum_new_points` | `0` |
| `past_frame_size` | `5` |
| `point_resample_cooldown` | `1` |
| `point_sampler` | `uniform` |
| `pose_guesser` | `last_pose` |
| `ransac_localization` | `True` |
| `section_length` | `13` |
| `tracked_point_num_max` | `2000` |
| `tracked_point_num_min` | `200` |
| `tracking_ba_iterations` | `20` |
| `update_localized_pose` | `False` |

## Notes

- Parameters applied incrementally in order of single-parameter improvement
- ATE RMSE computed with Sim3 alignment (`evo_ape -as`) and reported in mm
- Lower ATE RMSE is better
- Frame range: 0-541 of camcalib sequence 2-2
- Total steps tested: 8
