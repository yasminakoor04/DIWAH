#!/usr/bin/env python3
"""
FLIRT Feature Extraction Pipeline — DIWAH Thesis
=================================================
Extracts ML-ready, 5-second windowed features from aligned wearable data
(ActiGraph, Bangle.js, EmotiBit) using the FLIRT library (v0.0.2).

Verified FLIRT API (v0.0.2):
  flirt.get_acc_features(data, window_length, window_step_size,
                         data_frequency, num_cores)
  flirt.get_hrv_features(data, window_length, window_step_size,
                         domains, threshold, clean_data, num_cores)
  flirt.get_stat_features(data, window_length, window_step_size)

Output: data/flirt_feature_matrix_ready.csv

Usage:
    python scripts/extract_flirt_features.py
    python scripts/extract_flirt_features.py --input data/master_epochs.csv
    python scripts/extract_flirt_features.py --subject 2003
    python scripts/extract_flirt_features.py --all-subjects
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# FLIRT imports — install via: pip install flirt
# ---------------------------------------------------------------------------
try:
    import flirt
    _FLIRT_AVAILABLE = True
except ImportError:
    _FLIRT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging — timestamped progress to stdout
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ACC_PIPE_PROCESSED = Path(__file__).resolve().parent / "Acc_pipe" / "data" / "processed"

DEFAULT_INPUT_CSV = _ACC_PIPE_PROCESSED / "master_epochs.csv"
DEFAULT_OUTPUT_CSV = _ACC_PIPE_PROCESSED / "flirt_feature_matrix_ready.csv"

# ---------------------------------------------------------------------------
# FLIRT epoch configuration
# ---------------------------------------------------------------------------
# master_epochs.csv has one row per 5-second epoch → effective frequency = 1/5 Hz.
# FLIRT's window_length is in seconds; window_step_size == window_length gives
# non-overlapping (tiling) windows matching the thesis 5 s epoch design.
#
# NOTE: If you later feed raw 100 Hz ActiGraph data instead, update
# DATA_FREQUENCY_HZ to 100 and keep window_length / window_step_size at 5.
DATA_FREQUENCY_HZ: int = 1       # 1 sample per second equivalent for epoched data
                                  # (since each row already represents 5 s, FLIRT
                                  # will see 5 samples = 5 s at 1 Hz)
WINDOW_LENGTH_S: int = 60         # seconds — FLIRT minimum recommended is 1 min
                                  # for statistically stable features. Change to 5
                                  # if your raw data is at high frequency (≥10 Hz).
WINDOW_STEP_S: int = 60          # non-overlapping stride (same as window_length)
FILL_LIMIT: int = 3               # max consecutive NaN rows to forward/back-fill

# NOTE ON WINDOW SIZE:
# ━━━━━━━━━━━━━━━━━━━━
# Because master_epochs.csv is already pre-aggregated to 5 s epochs, there are
# only ~36 rows per 3-minute stage. FLIRT needs a minimum number of samples per
# window to compute frequency-domain features.
#
# Recommended approach:
#   • Use window_length=60 (1 min) on this epoched CSV → 12 rows/window, stable.
#   • For raw 100 Hz ActiGraph CSV → use window_length=5, DATA_FREQUENCY_HZ=100.
#
# The get_stat_features() function works well even on short windows (5 s), so we
# use it separately for fine-grain statistics (mean, SD, skew, kurtosis, etc.).

# ---------------------------------------------------------------------------
# Column definitions (as they appear in master_epochs.csv)
# ---------------------------------------------------------------------------
ACCEL_COLS = {
    "actigraph": {
        "x": "ax_mean_actigraph",
        "y": "ay_mean_actigraph",
        "z": "az_mean_actigraph",
    },
    "bangle": {
        "x": "ax_mean_bangle",
        "y": "ay_mean_bangle",
        "z": "az_mean_bangle",
    },
    "emotibit": {
        "x": "ax_mean_emotibit",
        "y": "ay_mean_emotibit",
        "z": "az_mean_emotibit",
    },
}

VM_COLS = {
    "actigraph": "vm_mean_actigraph",
    "bangle":    "vm_mean_bangle",
    "emotibit":  "vm_mean_emotibit",
}

HR_COL   = "hr_polar"   # Polar chest strap heart rate (BPM)
METS_COL = "mets"       # Ground-truth METs from indirect calorimetry


# ===========================================================================
# Step 1 — Data loading & preprocessing
# ===========================================================================

def load_and_preprocess(
    csv_path: Path,
    subject_filter: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load master_epochs.csv and produce a clean DataFrame with DatetimeIndex.

    FLIRT requirements enforced:
      ✓ DatetimeIndex with UTC timezone (no ambiguous DST gaps)
      ✓ Monotonically increasing index (no duplicates)
      ✓ Numeric columns only (no object-type leakage)
      ✓ Short gaps imputed (≤ FILL_LIMIT rows)

    Args:
        csv_path:       Path to the aligned CSV.
        subject_filter: '2003', '2017', etc. — limits to one subject. None = all.

    Returns:
        Preprocessed DataFrame with DatetimeIndex.
    """
    log.info("Loading dataset:  %s", csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    df = pd.read_csv(csv_path, low_memory=False)
    log.info("  Raw shape: %d rows × %d columns.", *df.shape)

    # ── Subject filter ────────────────────────────────────────────────────
    sub_col = "subject_id" if "subject_id" in df.columns else "subject"
    # Strip the "Diwah" prefix that the R pipeline sometimes adds
    df[sub_col] = df[sub_col].astype(str).str.replace("Diwah", "", regex=False).str.strip()

    if subject_filter is not None:
        df = df[df[sub_col] == str(subject_filter)].copy()
        if df.empty:
            available = sorted(pd.read_csv(csv_path)[sub_col].astype(str).unique())
            raise ValueError(
                f"Subject '{subject_filter}' not found. "
                f"Available IDs: {available}"
            )
        log.info("  Filtered to subject %s — %d rows.", subject_filter, len(df))

    # ── Parse timestamps ──────────────────────────────────────────────────
    if "timestamp" not in df.columns:
        raise KeyError("Expected a 'timestamp' column in the CSV.")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    n_bad = df["timestamp"].isna().sum()
    if n_bad:
        log.warning("  Dropping %d rows with un-parseable timestamps.", n_bad)
        df = df.dropna(subset=["timestamp"])

    # Sort, drop exact duplicates, then set index
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    df = df.set_index("timestamp")
    log.info("  DatetimeIndex: %s → %s", df.index.min(), df.index.max())

    # ── Forward/back-fill short gaps ──────────────────────────────────────
    num_cols = df.select_dtypes(include=[np.number]).columns
    before = df[num_cols].isna().sum().sum()
    df[num_cols] = (
        df[num_cols]
        .ffill(limit=FILL_LIMIT)
        .bfill(limit=FILL_LIMIT)
    )
    after = df[num_cols].isna().sum().sum()
    log.info("  Imputation: %d NaNs filled; %d still missing.", before - after, after)

    return df


# ===========================================================================
# Step 2 — FLIRT accelerometer features  (per device, time + frequency domain)
# ===========================================================================

def extract_acc_features(df: pd.DataFrame, device: str, col_map: dict) -> Optional[pd.DataFrame]:
    """
    Run flirt.get_acc_features() a single device's X/Y/Z axes.

    FLIRT expects columns named 'x', 'y', 'z' and a DatetimeIndex.
    Returns one row per window with time-domain and frequency-domain features.

    Args:
        df:       Full DataFrame with DatetimeIndex.
        device:   Device name string ('actigraph', 'bangle', 'emotibit').
        col_map:  {'x': col, 'y': col, 'z': col} mapping.

    Returns:
        Feature DataFrame (windows × features) or None on failure.
    """
    missing_cols = [v for v in col_map.values() if v not in df.columns]
    if missing_cols:
        log.warning("  [%s] Missing columns %s — skipping device.", device, missing_cols)
        return None

    # Build FLIRT-format xyz DataFrame (columns must be 'x', 'y', 'z')
    xyz = df[[col_map["x"], col_map["y"], col_map["z"]]].copy()
    xyz.columns = ["x", "y", "z"]
    xyz = xyz.dropna(how="all")

    if len(xyz) < 10:
        log.warning("  [%s] Only %d valid rows — insufficient for feature extraction.", device, len(xyz))
        return None

    log.info("  [%s] Starting FLIRT accel extraction — %d rows, window=%ds, step=%ds...",
             device, len(xyz), WINDOW_LENGTH_S, WINDOW_STEP_S)

    try:
        # ── flirt.get_acc_features() ──────────────────────────────────────
        # Args:
        #   data           : DataFrame with columns 'x', 'y', 'z' + DatetimeIndex
        #   window_length  : seconds per window
        #   window_step_size: stride in seconds (= window_length → non-overlapping)
        #   data_frequency : sampling rate of the data in Hz
        #   num_cores      : 0 = auto-detect available CPU cores (parallelises internally)
        feats = flirt.get_acc_features(
            xyz,
            window_length=WINDOW_LENGTH_S,
            window_step_size=WINDOW_STEP_S,
            data_frequency=DATA_FREQUENCY_HZ,
            num_cores=1,
        )

        if feats is None or feats.empty:
            log.warning("  [%s] FLIRT returned an empty result.", device)
            return None

        # Prefix every column so devices don't collide in the merged matrix
        feats.columns = [f"{device}_acc_{c}" for c in feats.columns]
        log.info("  [%s] ✓ %d windows × %d features extracted.", device, *feats.shape)
        return feats

    except Exception as exc:
        # Catches: ValueError("window too short"), RuntimeError, etc.
        log.error("  [%s] FLIRT acc extraction failed: %s — skipping.", device, exc)
        return None


# ===========================================================================
# Step 2b — FLIRT statistical features on vector magnitude  (fine-grain)
# ===========================================================================

def extract_vm_stat_features(df: pd.DataFrame, device: str) -> Optional[pd.DataFrame]:
    """
    Run flirt.get_stat_features() on the pre-computed vector magnitude (VM)
    column. This is suitable for already-epoched data (even at 5 s resolution)
    since get_stat_features only needs ≥1 sample per window.

    Returns mean, std, min, max, skewness, kurtosis, quartiles, etc.
    """
    vm_col = VM_COLS.get(device)
    if vm_col is None or vm_col not in df.columns:
        log.warning("  [%s] VM column '%s' not found — skipping stat features.", device, vm_col)
        return None

    vm = df[[vm_col]].dropna()
    if len(vm) < 2:
        return None

    log.info("  [%s] Starting FLIRT stat extraction on VM column (%d rows)...", device, len(vm))

    try:
        # ── flirt.get_stat_features() ─────────────────────────────────────
        # Works on any windowed Pandas DataFrame; no data_frequency needed.
        # window_length and window_step_size still in seconds.
        feats = flirt.get_stat_features(
            vm,
            window_length=WINDOW_LENGTH_S,
            window_step_size=WINDOW_STEP_S,
        )

        if feats is None or feats.empty:
            return None

        feats.columns = [f"{device}_vm_stat_{c}" for c in feats.columns]
        log.info("  [%s] ✓ stat %d windows × %d features.", device, *feats.shape)
        return feats

    except Exception as exc:
        log.error("  [%s] FLIRT stat extraction failed: %s — skipping.", device, exc)
        return None


# ===========================================================================
# Step 3 — FLIRT heart-rate variability features
# ===========================================================================

def extract_hrv_features(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Run flirt.get_hrv_features() on the Polar HR signal.

    Note: the HRV module expects inter-beat intervals (IBI) in seconds or
    beat-per-minute (BPM) values with a DatetimeIndex.  FLIRT auto-detects
    the unit.  The 'td' domain gives time-domain HRV (RMSSD, SDNN, pNN50…),
    'fd' gives frequency-domain (LF, HF, LF/HF ratio), 'stat' gives
    descriptive stats.

    Args:
        df: Full DataFrame with DatetimeIndex and HR_COL column.

    Returns:
        Feature DataFrame or None.
    """
    if HR_COL not in df.columns:
        log.warning("  HR column '%s' not found — skipping HRV features.", HR_COL)
        return None

    hr = df[[HR_COL]].dropna()
    if len(hr) < 5:
        log.warning("  Insufficient HR data (%d rows) — skipping.", len(hr))
        return None

    log.info("  Starting FLIRT HRV extraction — %d rows, window=%ds...",
             len(hr), WINDOW_LENGTH_S)

    try:
        # ── flirt.get_hrv_features() ──────────────────────────────────────
        # Args:
        #   data          : Single-column DataFrame of HR/IBI + DatetimeIndex
        #   window_length : seconds per window
        #   window_step_size: stride in seconds
        #   domains       : list of HRV domain modules to include
        #   threshold     : outlier removal threshold (seconds)
        #   clean_data    : whether to clean artefacts before HRV computation
        #   num_cores     : 0 = auto
        feats = flirt.get_hrv_features(
            hr,
            window_length=WINDOW_LENGTH_S,
            window_step_size=WINDOW_STEP_S,
            domains=["td", "stat"],  # skip "fd" — needs high-res IBI, not BPM means
            threshold=0.2,
            clean_data=True,
            num_cores=1,
        )

        if feats is None or feats.empty:
            log.warning("  HRV: FLIRT returned an empty result.")
            return None

        feats.columns = [f"hrv_{c}" for c in feats.columns]
        log.info("  ✓ HRV %d windows × %d features.", *feats.shape)
        return feats

    except Exception as exc:
        log.error("  HRV extraction failed: %s — skipping.", exc)
        return None


# ===========================================================================
# Step 4 — METs resampling to match FLIRT windows
# ===========================================================================

def resample_mets(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Resample 'mets' into the same non-overlapping windows used by FLIRT.

    pandas .resample(f"{WINDOW_LENGTH_S}s").mean() produces one value per
    window by averaging all METs samples that fall in that bin —
    identical in behaviour to what FLIRT does when it aggregates raw samples.

    Returns:
        Series named 'mets', indexed by the start of each window.
    """
    if METS_COL not in df.columns:
        log.warning("  '%s' column not found — target variable absent.", METS_COL)
        return None

    log.info("  Resampling METs to %d-second non-overlapping windows...", WINDOW_LENGTH_S)
    mets = df[METS_COL].resample(f"{WINDOW_LENGTH_S}s").mean().rename(METS_COL)
    log.info("  METs: %d windows total, %d with valid values.",
             len(mets), mets.notna().sum())
    return mets


# ===========================================================================
# Step 5 — Merge all feature blocks into a single matrix
# ===========================================================================

def build_feature_matrix(
    acc_frames: list,
    stat_frames: list,
    hrv_frame: Optional[pd.DataFrame],
    mets: Optional[pd.Series],
) -> pd.DataFrame:
    """
    Concatenate feature blocks column-wise, then align with METs.
    Drops rows where target METs is missing.
    """
    parts = [f for f in (acc_frames + stat_frames) if f is not None and not f.empty]
    if hrv_frame is not None and not hrv_frame.empty:
        parts.append(hrv_frame)

    if not parts:
        raise RuntimeError(
            "No feature frames were successfully generated. "
            "Check the logs above for per-device errors."
        )

    log.info("  Merging %d feature block(s) on DatetimeIndex (outer join)...", len(parts))
    merged = pd.concat(parts, axis=1, join="outer").sort_index()

    if mets is not None:
        mets = mets.dropna().sort_index()
        # Due to windowing boundaries, FLIRT timestamps (e.g. 15:08:55) might
        # not perfectly match pandas resample boundaries (e.g. 15:09:00).
        # merge_asof finds the closest MET value within the window step.
        merged = pd.merge_asof(
            merged,
            mets.to_frame(name=METS_COL),
            left_index=True,
            right_index=True,
            direction="nearest",
            tolerance=pd.Timedelta(f"{WINDOW_STEP_S}s")
        )
        before = len(merged)
        merged = merged.dropna(subset=[METS_COL])
        log.info("  Dropped %d rows lacking METs ground truth (after temporal alignment).", before - len(merged))

    log.info("  Shape of final feature matrix: %d rows × %d columns.", *merged.shape)
    return merged


# ===========================================================================
# Main pipeline
# ===========================================================================

def run_pipeline(
    input_csv: Path,
    output_csv: Path,
    subject_filter: Optional[str],
) -> pd.DataFrame:
    """End-to-end pipeline for a single subject or the full cohort."""

    log.info("═" * 60)
    log.info("DIWAH — FLIRT Feature Extraction Pipeline")
    log.info("  Input : %s", input_csv)
    log.info("  Output: %s", output_csv)
    log.info("  Window: %d s / step: %d s / freq: %d Hz",
             WINDOW_LENGTH_S, WINDOW_STEP_S, DATA_FREQUENCY_HZ)
    log.info("═" * 60)

    if not _FLIRT_AVAILABLE:
        log.error("FLIRT not installed.  Run:  pip install flirt")
        sys.exit(1)

    # ── Step 1: Load ──────────────────────────────────────────────────────
    log.info("─" * 60)
    log.info("Step 1 — Loading and preprocessing")
    df = load_and_preprocess(input_csv, subject_filter=subject_filter)

    # ── Step 2: Accelerometer features per device ─────────────────────────
    log.info("─" * 60)
    log.info("Step 2 — FLIRT accelerometer feature extraction (time + freq domain)")
    acc_frames  = []
    stat_frames = []
    for device, col_map in ACCEL_COLS.items():
        # Time- and frequency-domain from raw XYZ
        acc_f = extract_acc_features(df, device, col_map)
        if acc_f is not None:
            acc_frames.append(acc_f)
        # Statistical features from pre-computed vector magnitude
        stat_f = extract_vm_stat_features(df, device)
        if stat_f is not None:
            stat_frames.append(stat_f)

    # ── Step 3: Heart-rate variability features ───────────────────────────
    log.info("─" * 60)
    log.info("Step 3 — FLIRT HRV feature extraction")
    hrv_frame = extract_hrv_features(df)

    # ── Step 4: Resample METs ─────────────────────────────────────────────
    log.info("─" * 60)
    log.info("Step 4 — METs resampling")
    mets = resample_mets(df)

    # ── Step 5: Merge and export ───────────────────────────────────────────
    log.info("─" * 60)
    log.info("Step 5 — Building final feature matrix")
    matrix = build_feature_matrix(acc_frames, stat_frames, hrv_frame, mets)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(output_csv)

    n_acc  = sum(1 for c in matrix.columns if "_acc_" in c)
    n_stat = sum(1 for c in matrix.columns if "_vm_stat_" in c)
    n_hrv  = sum(1 for c in matrix.columns if c.startswith("hrv_"))

    log.info("═" * 60)
    log.info("Done!")
    log.info("  Saved to: %s", output_csv)
    log.info("  Shape of final matrix:  %d rows × %d columns", *matrix.shape)
    log.info("  Acc features  : %d", n_acc)
    log.info("  VM stat feat  : %d", n_stat)
    log.info("  HRV features  : %d", n_hrv)
    log.info("  Target (METs) : 1 column")
    log.info("═" * 60)
    return matrix


def main():
    parser = argparse.ArgumentParser(
        description="DIWAH FLIRT Feature Extraction — generates flirt_feature_matrix_ready.csv"
    )
    parser.add_argument("--input",  type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--subject", type=str, default=None,
                        help="Process a single subject ID (e.g. '2003')")
    parser.add_argument("--all-subjects", action="store_true",
                        help="Process each subject independently and stack results")
    args = parser.parse_args()

    if args.all_subjects:
        # Load the full file once just to get subject list
        all_df = pd.read_csv(args.input, low_memory=False)
        sub_col = "subject_id" if "subject_id" in all_df.columns else "subject"
        subjects = sorted(all_df[sub_col].astype(str)
                         .str.replace("Diwah", "", regex=False).str.strip().unique())
        log.info("Processing %d subjects: %s", len(subjects), subjects)

        all_matrices = []
        for subj in subjects:
            try:
                sub_output = args.output.parent / f"flirt_{subj}.csv"
                m = run_pipeline(args.input, sub_output, subject_filter=subj)
                m.insert(0, "subject_id", subj)
                all_matrices.append(m)
            except Exception as exc:
                log.error("Subject %s failed: %s — skipping.", subj, exc)

        if all_matrices:
            full_matrix = pd.concat(all_matrices, axis=0)
            full_matrix.to_csv(args.output)
            log.info("Combined matrix saved to: %s  (%d rows total)", args.output, len(full_matrix))
    else:
        run_pipeline(args.input, args.output, subject_filter=args.subject)


if __name__ == "__main__":
    main()
