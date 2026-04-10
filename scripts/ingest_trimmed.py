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

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
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

    untrimmed = pd.read_csv(untrimmed_csv)
    untrimmed = ensure_subject_column(untrimmed)
    untrimmed = ensure_timestamp_column(untrimmed)

    unified = pd.concat([trimmed_good, untrimmed], ignore_index=True, sort=False)
    unified = unified.dropna(subset=["subject", "timestamp"])
    return unified


def to_measurement_df(unified: pd.DataFrame) -> pd.DataFrame:
    frames = []

    for vm_col, device in VM_TO_DEVICE.items():
        if vm_col not in unified.columns:
            continue

        chunk = unified[["subject", "timestamp", vm_col]].copy()
        chunk["magnitude"] = pd.to_numeric(chunk[vm_col], errors="coerce")
        chunk = chunk.dropna(subset=["magnitude"])
        chunk["device"] = device
        chunk["session"] = "activity"
        frames.append(chunk[["timestamp", "subject", "device", "session", "magnitude"]])

    if not frames:
        raise ValueError("None of vm_mean_actigraph/vm_mean_bangle/vm_mean_emotibit were present")

    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["timestamp", "subject", "magnitude"])
    out = out.sort_values("timestamp")
    out = out.set_index("timestamp")
    return out


def write_to_influx(df: pd.DataFrame) -> None:
    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=120_000) as client:
        write_api = client.write_api(write_options=ASYNCHRONOUS)

        chunk_size = 50_000
        if len(df) <= chunk_size:
            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=df,
                data_frame_measurement_name="accelerometer",
                data_frame_tag_columns=["subject", "device", "session"],
                write_precision=WritePrecision.S,
            )
        else:
            for start in range(0, len(df), chunk_size):
                part = df.iloc[start:start + chunk_size]
                write_api.write(
                    bucket=INFLUX_BUCKET,
                    org=INFLUX_ORG,
                    record=part,
                    data_frame_measurement_name="accelerometer",
                    data_frame_tag_columns=["subject", "device", "session"],
                    write_precision=WritePrecision.S,
                )

        write_api.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest trimmed+untrimmed unified 5s epochs")
    parser.add_argument("--trimmed-csv", type=Path, default=DEFAULT_TRIMMED)
    parser.add_argument("--untrimmed-csv", type=Path, default=DEFAULT_UNTRIMMED)
    args = parser.parse_args()

    unified = load_and_prepare(args.trimmed_csv, args.untrimmed_csv)
    measurement_df = to_measurement_df(unified)

    write_to_influx(measurement_df)

    unique_subjects = sorted(measurement_df["subject"].astype(str).unique())
    print(f"Ingested rows: {len(measurement_df):,}")
    print(f"Subjects pushed: {len(unique_subjects)}")
    print("Subject IDs: " + ", ".join(unique_subjects))


if __name__ == "__main__":
    main()
