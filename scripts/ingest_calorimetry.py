import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from src.config import INFLUX_BUCKET, INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL

# Source: manually trimmed OneDrive folder
DEFAULT_TRIMMED = Path(
    r"C:\Users\Hanna\OneDrive - Linnéuniversitetet\THESIS 2026"
    r"\pictures of trimmed subjects_ALL\trimmed_CSV\master_epochs.csv"
)

# Same exclusion list as ingest_trimmed.py
BAD_SUBJECTS = ["2004", "2005", "2008", "2014", "2019", "2032"]


def ingest_calorimetry(trimmed_csv: Path = DEFAULT_TRIMMED) -> None:
    if not trimmed_csv.exists():
        print(f"ERROR: File not found: {trimmed_csv}")
        sys.exit(1)

    print(f"Loading: {trimmed_csv}")
    df = pd.read_csv(trimmed_csv)

    # Normalise subject column
    sub_col = "subject_id" if "subject_id" in df.columns else "subject"
    df["subject"] = (
        df[sub_col].astype(str)
        .str.replace("Diwah", "", regex=False)
        .str.strip()
    )

    # Drop bad subjects
    df = df[~df["subject"].isin(BAD_SUBJECTS)].copy()

    # Parse real timestamps directly from the CSV
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp", "subject"])

    # Rename columns to the expected InfluxDB field names
    rename = {}
    if "hr_polar" in df.columns:
        rename["hr_polar"] = "HR"
    if "mets" in df.columns:
        rename["mets"] = "METS"
    df = df.rename(columns=rename)

    hr_mets_cols = [c for c in ["HR", "METS"] if c in df.columns]
    if not hr_mets_cols:
        print("ERROR: Neither hr_polar nor mets columns found in CSV")
        sys.exit(1)

    df["session"] = "activity"
    df = df[["subject", "session", "timestamp"] + hr_mets_cols].copy()
    df = df.dropna(subset=hr_mets_cols, how="all")
    df = df.set_index("timestamp")

    print(f"Writing {len(df):,} rows for {df['subject'].nunique()} subjects...")

    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=120_000) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        chunk_size = 10_000
        for start in range(0, len(df), chunk_size):
            chunk = df.iloc[start:start + chunk_size]
            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=chunk,
                data_frame_measurement_name="calorimetry",
                data_frame_tag_columns=["subject", "session"],
                write_precision=WritePrecision.S,
            )

    subjects_done = sorted(df["subject"].unique())
    print(f"Done! Ingested {len(df):,} calorimetry rows.")
    print("Subjects: " + ", ".join(subjects_done))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--trimmed-csv", type=Path, default=DEFAULT_TRIMMED)
    args = parser.parse_args()
    ingest_calorimetry(args.trimmed_csv)
