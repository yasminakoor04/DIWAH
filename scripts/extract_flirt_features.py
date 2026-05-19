#!/usr/bin/env python3
"""
FLIRT Feature Extraction Pipeline — DIWAH Thesis (Device-Specific Separation)
===========================================================================
Extracts ML-ready, 5-second windowed features from aligned wearable data.
Crucially, this script creates completely separate feature matrices for each
device to prevent missing data in one device (e.g., EmotiBit) from dropping
perfectly valid epochs in another device (e.g., ActiGraph).

Output: 
  - data/processed/flirt_reference.csv
  - data/processed/flirt_emotibit.csv
  - data/processed/flirt_bangle.csv
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import flirt
    _FLIRT_AVAILABLE = True
except ImportError:
    _FLIRT_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ACC_PIPE_PROCESSED = Path(__file__).resolve().parent / "Acc_pipe" / "data" / "processed"

DEFAULT_INPUT_CSV = _ACC_PIPE_PROCESSED / "master_epochs.csv"

DATA_FREQUENCY_HZ: int = 1
WINDOW_LENGTH_S: int = 60
WINDOW_STEP_S: int = 60
FILL_LIMIT: int = 3

ACCEL_COLS = {
    "reference": {"x": "ax_mean_actigraph", "y": "ay_mean_actigraph", "z": "az_mean_actigraph"},
    "emotibit":  {"x": "ax_mean_emotibit",  "y": "ay_mean_emotibit",  "z": "az_mean_emotibit"},
    "bangle":    {"x": "ax_mean_bangle",    "y": "ay_mean_bangle",    "z": "az_mean_bangle"},
}

VM_COLS = {
    "reference": "vm_mean_actigraph",
    "bangle":    "vm_mean_bangle",
    "emotibit":  "vm_mean_emotibit",
}

HR_COL   = "hr_polar"
METS_COL = "mets"

def load_and_preprocess(csv_path: Path) -> pd.DataFrame:
    log.info("Loading dataset:  %s", csv_path)
    df = pd.read_csv(csv_path, low_memory=False)
    
    sub_col = "subject_id" if "subject_id" in df.columns else "subject"
    df[sub_col] = df[sub_col].astype(str).str.replace("Diwah", "", regex=False).str.strip()
    
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    df = df.set_index("timestamp")
    
    num_cols = df.select_dtypes(include=[np.number]).columns
    df[num_cols] = df[num_cols].ffill(limit=FILL_LIMIT).bfill(limit=FILL_LIMIT)
    
    df["subject_id"] = df[sub_col]
    return df

def extract_acc_features(df: pd.DataFrame, device: str) -> Optional[pd.DataFrame]:
    col_map = ACCEL_COLS[device]
    missing = [v for v in col_map.values() if v not in df.columns]
    if missing:
        return None

    xyz = df[[col_map["x"], col_map["y"], col_map["z"]]].copy()
    xyz.columns = ["x", "y", "z"]
    xyz = xyz.dropna(how="all")

    if len(xyz) < 10: return None

    try:
        feats = flirt.get_acc_features(xyz, window_length=WINDOW_LENGTH_S, window_step_size=WINDOW_STEP_S, data_frequency=DATA_FREQUENCY_HZ, num_cores=1)
        if feats is None or feats.empty: return None
        feats.columns = [f"{device}_acc_{c}" for c in feats.columns]
        return feats
    except:
        return None

def extract_vm_stat_features(df: pd.DataFrame, device: str) -> Optional[pd.DataFrame]:
    vm_col = VM_COLS.get(device)
    if vm_col not in df.columns: return None

    vm = df[[vm_col]].dropna()
    if len(vm) < 2: return None

    try:
        feats = flirt.get_stat_features(vm, window_length=WINDOW_LENGTH_S, window_step_size=WINDOW_STEP_S)
        if feats is None or feats.empty: return None
        feats.columns = [f"{device}_vm_stat_{c}" for c in feats.columns]
        return feats
    except:
        return None

def extract_hr_stat_features(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if HR_COL not in df.columns: return None
    hr = df[[HR_COL]].dropna()
    if len(hr) < 2: return None

    try:
        feats = flirt.get_stat_features(hr, window_length=WINDOW_LENGTH_S, window_step_size=WINDOW_STEP_S)
        feats.columns = [f"hr_polar_stat_{c}" for c in feats.columns]
        return feats
    except:
        return None

def resample_mets(df: pd.DataFrame) -> Optional[pd.Series]:
    if METS_COL not in df.columns: return None
    return df[METS_COL].resample(f"{WINDOW_LENGTH_S}s").mean().rename(METS_COL)

def resample_subjects(df: pd.DataFrame) -> pd.Series:
    """Keep track of subject ID during resampling by picking the first mode."""
    return df["subject_id"].resample(f"{WINDOW_LENGTH_S}s").first()

def generate_device_matrix_for_subject(df: pd.DataFrame, device: str, mets: pd.Series, subjects: pd.Series) -> Optional[pd.DataFrame]:
    log.info("  Generating specific matrix for: %s", device)
    
    parts = []
    
    # 1. Accel Features
    acc_f = extract_acc_features(df, device)
    if acc_f is not None: parts.append(acc_f)
        
    # 2. VM Features
    vm_f = extract_vm_stat_features(df, device)
    if vm_f is not None: parts.append(vm_f)
        
    # 3. Polar HR (ONLY for Reference)
    if device == "reference":
        hr_f = extract_hr_stat_features(df)
        if hr_f is not None: parts.append(hr_f)
            
    if not parts:
        log.warning("  No features extracted for %s", device)
        return None

    merged = pd.concat(parts, axis=1, join="outer").sort_index()
    
    # Align with METs and Subject IDs
    if mets is not None:
        mets = mets.dropna().sort_index()
        merged = pd.merge_asof(merged, mets.to_frame(), left_index=True, right_index=True, direction="nearest", tolerance=pd.Timedelta(f"{WINDOW_STEP_S}s"))
        merged = pd.merge_asof(merged, subjects.to_frame(), left_index=True, right_index=True, direction="nearest", tolerance=pd.Timedelta(f"{WINDOW_STEP_S}s"))
        
        merged = merged.dropna(subset=[METS_COL])
        
        if acc_f is not None:
            merged = merged.dropna(subset=acc_f.columns, how='all')

    return merged

def main():
    if not _FLIRT_AVAILABLE:
        log.error("FLIRT not installed.")
        sys.exit(1)

    # Load the full file once
    full_df = load_and_preprocess(DEFAULT_INPUT_CSV)
    
    # Get list of unique subjects
    subjects_list = full_df["subject_id"].unique()
    log.info("Processing %d subjects individually...", len(subjects_list))
    
    all_reference = []
    all_emotibit = []
    all_bangle = []
    
    for subj in subjects_list:
        log.info("--- Subject %s ---", subj)
        sub_df = full_df[full_df["subject_id"] == subj].copy()
        
        if len(sub_df) < 10:
            continue
            
        mets = resample_mets(sub_df)
        subjects = resample_subjects(sub_df)
        
        ref_df = generate_device_matrix_for_subject(sub_df, "reference", mets, subjects)
        if ref_df is not None: all_reference.append(ref_df)
            
        emo_df = generate_device_matrix_for_subject(sub_df, "emotibit", mets, subjects)
        if emo_df is not None: all_emotibit.append(emo_df)
            
        ban_df = generate_device_matrix_for_subject(sub_df, "bangle", mets, subjects)
        if ban_df is not None: all_bangle.append(ban_df)

    DEFAULT_INPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    if all_reference:
        pd.concat(all_reference).to_csv(_ACC_PIPE_PROCESSED / "flirt_reference.csv")
        log.info("Saved Reference Matrix -> %d epochs", len(pd.concat(all_reference)))
        
    if all_emotibit:
        pd.concat(all_emotibit).to_csv(_ACC_PIPE_PROCESSED / "flirt_emotibit.csv")
        log.info("Saved EmotiBit Matrix -> %d epochs", len(pd.concat(all_emotibit)))
        
    if all_bangle:
        pd.concat(all_bangle).to_csv(_ACC_PIPE_PROCESSED / "flirt_bangle.csv")
        log.info("Saved Bangle Matrix -> %d epochs", len(pd.concat(all_bangle)))

if __name__ == "__main__":
    main()
