#!/usr/bin/env python3
"""
Ingest unified trimmed+untrimmed 5s wearable epochs into InfluxDB.

Workflow:
1. Load master_epochs.csv (trimmed source for cohort).
2. Remove manual bad subjects from trimmed frame.
3. Load master_epochs_untrimmed.csv and append those rows.
4. Map vm_mean_* columns to accelerometer/magnitude for all subjects.
"""

import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import INFLUX_BUCKET, INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL


BAD_SUBJECTS: List[str] = ["2004", "2005", "2008", "2014", "2019", "2032"]

_DATA_DIR = Path(__file__).resolve().parent / "Acc_pipe" / "data" / "processed"
DEFAULT_TRIMMED = _DATA_DIR / "master_epochs.csv"
DEFAULT_UNTRIMMED = _DATA_DIR / "master_epochs_untrimmed.csv"

VM_TO_DEVICE: Dict[str, str] = {
    "vm_mean_actigraph": "actigraph",
    "vm_mean_bangle": "bangle",
    "vm_mean_emotibit": "emotibit",
}


def normalize_subject(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace("Diwah", "", regex=False)
        .str.strip()
    )


def ensure_subject_column(df: pd.DataFrame) -> pd.DataFrame:
    for candidate in ["subject_id", "subject", "Subject", "ID", "id"]:
        if candidate in df.columns:
            out = df.copy()
            out["subject"] = normalize_subject(out[candidate])
            return out
    raise ValueError("No subject column found in input CSV")


def ensure_timestamp_column(df: pd.DataFrame) -> pd.DataFrame:
    for candidate in ["timestamp", "Timestamp", "time", "Time", "datetime", "Datetime"]:
        if candidate in df.columns:
            out = df.copy()
            out["timestamp"] = pd.to_datetime(out[candidate], errors="coerce", utc=True)
            return out
    raise ValueError("No timestamp column found in input CSV")


def load_and_prepare(trimmed_csv: Path, untrimmed_csv: Path) -> pd.DataFrame:
    trimmed = pd.read_csv(trimmed_csv)
    trimmed = ensure_subject_column(trimmed)
    trimmed = ensure_timestamp_column(trimmed)

    trimmed_good = trimmed[~trimmed["subject"].isin(BAD_SUBJECTS)].copy()

    if untrimmed_csv.exists():
        untrimmed = pd.read_csv(untrimmed_csv)
        untrimmed = ensure_subject_column(untrimmed)
        untrimmed = ensure_timestamp_column(untrimmed)
        unified = pd.concat([trimmed_good, untrimmed], ignore_index=True, sort=False)
    else:
        print(f"[WARNING] Untrimmed CSV not found at {untrimmed_csv}. Proceeding with trimmed data only.")
        unified = trimmed_good

    unified = unified.dropna(subset=["subject", "timestamp"])
    return unified


def to_measurement_dfs(unified: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    dfs = {}

    # 1. Accelerometer Data
    acc_frames = []
    for vm_col, device in VM_TO_DEVICE.items():
        if vm_col not in unified.columns:
            continue
        chunk = unified[["subject", "timestamp", vm_col]].copy()
        chunk["magnitude"] = pd.to_numeric(chunk[vm_col], errors="coerce")
        chunk = chunk.dropna(subset=["magnitude"])
        chunk["device"] = device
        chunk["session"] = "activity"
        acc_frames.append(chunk[["timestamp", "subject", "device", "session", "magnitude"]])

    if acc_frames:
        out_acc = pd.concat(acc_frames, ignore_index=True)
        out_acc = out_acc.dropna(subset=["timestamp", "subject", "magnitude"])
        out_acc = out_acc.set_index("timestamp").sort_index()
        dfs["accelerometer"] = out_acc

    # 2. Calorimetry Data (Vyntus HR & METs)
    calo_cols = []
    if "mets" in unified.columns: calo_cols.append("mets")
    if "hr_polar" in unified.columns: calo_cols.append("hr_polar")

    if calo_cols:
        calo_chunk = unified[["subject", "timestamp"] + calo_cols].copy()
        calo_chunk = calo_chunk.dropna(subset=calo_cols, how="all")
        
        # Rename to uppercase to strictly match InfluxDB schema
        rename_map = {"hr_polar": "HR", "mets": "METS"}
        calo_chunk = calo_chunk.rename(columns=rename_map)
        calo_chunk["session"] = "activity"
        
        final_cols = [rename_map.get(c, c) for c in calo_cols]
        calo_chunk = calo_chunk.dropna(subset=["subject", "timestamp"] + final_cols)
        calo_chunk = calo_chunk.set_index("timestamp").sort_index()
        dfs["calorimetry"] = calo_chunk

    if not dfs:
        raise ValueError("No valid accelerometer or calorimetry data found in frame!")
    return dfs


def write_to_influx(dfs: Dict[str, pd.DataFrame]) -> None:
    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=120_000) as client:
        write_api = client.write_api(write_options=ASYNCHRONOUS)
        chunk_size = 50_000

        for measurement, df in dfs.items():
            if measurement == "accelerometer":
                tag_cols = ["subject", "device", "session"]
            else:
                tag_cols = ["subject", "session"]

            for start in range(0, len(df), chunk_size):
                part = df.iloc[start:start + chunk_size]
                write_api.write(
                    bucket=INFLUX_BUCKET,
                    org=INFLUX_ORG,
                    record=part,
                    data_frame_measurement_name=measurement,
                    data_frame_tag_columns=tag_cols,
                    write_precision=WritePrecision.S,
                )
        write_api.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest trimmed+untrimmed unified 5s epochs (Wearables + Calorimetry)")
    parser.add_argument("--trimmed-csv", type=Path, default=DEFAULT_TRIMMED)
    parser.add_argument("--untrimmed-csv", type=Path, default=DEFAULT_UNTRIMMED)
    args = parser.parse_args()

    unified = load_and_prepare(args.trimmed_csv, args.untrimmed_csv)
    dfs = to_measurement_dfs(unified)

    write_to_influx(dfs)

    for measurement, df in dfs.items():
        unique_subjects = sorted(df["subject"].astype(str).unique())
        print(f"[{measurement.upper()}] Ingested {len(df):,} rows across {len(unique_subjects)} subjects.")
    print("Done!")


if __name__ == "__main__":
    main()
