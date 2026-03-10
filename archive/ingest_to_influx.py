import argparse
from typing import Dict
import pandas as pd
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET
from src.data_loader import get_available_subjects_sessions, load_and_align_data

def write_df(client: InfluxDBClient, df: pd.DataFrame, device: str, subject: str, session: str):
    if df is None or df.empty:
        print(f"  {device}: no data, skipping")
        return

    # Ensure timestamp is datetime and sorted
    if "timestamp" not in df.columns:
        print(f"  {device}: ERROR - no timestamp column!")
        return
    
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
    
    # Drop rows with invalid timestamps
    df = df.dropna(subset=['timestamp'])
    df = df.sort_values("timestamp")
    
    if df.empty:
        print(f"  {device}: no valid timestamps, skipping")
        return

    # Map column names (parsers use different conventions)
    acc_col_map = {
        'acc_x': ['acc_x', 'Acc_x'],
        'acc_y': ['acc_y', 'Acc_y'],
        'acc_z': ['acc_z', 'Acc_z']
    }
    
    # Build output DataFrame with timestamp kept as a column initially
    out = df[['timestamp']].copy()
    
    for target_col, possible_names in acc_col_map.items():
        for col in possible_names:
            if col in df.columns:
                out[target_col] = pd.to_numeric(df[col], errors="coerce")
                break

    # Magnitude column name varies across parsers
    if "acc_magnitude" in df.columns:
        out["magnitude"] = pd.to_numeric(df["acc_magnitude"], errors="coerce")
    elif "magnitude" in df.columns:
        out["magnitude"] = pd.to_numeric(df["magnitude"], errors="coerce")

    # Tag columns
    out["device"] = device
    out["subject"] = subject
    out["session"] = session

    # Drop rows with all NaN fields (excluding tags and timestamp)
    field_cols = [c for c in out.columns if c not in ['timestamp', 'device', 'subject', 'session']]
    if not field_cols:
        print(f"  {device}: ERROR - no field columns found!")
        return
    
    out = out.dropna(how='all', subset=field_cols)
    
    if out.empty:
        print(f"  {device}: all data is NaN, skipping")
        return

    # Now set timestamp as index for InfluxDB write
    out = out.set_index('timestamp')

    print(f"  {device}: writing {len(out):,} points...", end='', flush=True)

    write_api = client.write_api(write_options=ASYNCHRONOUS)

    # Write in chunks for large files (batching improves speed)
    chunk_size = 100000  # Increased for faster bulk writes
    if len(out) > chunk_size:
        for i in range(0, len(out), chunk_size):
            chunk = out.iloc[i:i+chunk_size]
            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=chunk,
                data_frame_measurement_name="accelerometer",
                data_frame_tag_columns=["device", "subject", "session"],
                write_precision=WritePrecision.MS
            )
        write_api.close()  # Flush remaining writes
    else:
        write_api.write(
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
            record=out,
            data_frame_measurement_name="accelerometer",
            data_frame_tag_columns=["device", "subject", "session"],
            write_precision=WritePrecision.MS
        )
        write_api.close()
    
    print(" done!")  # Newline after completion


def ingest_subject_session(subject: str, session: str, downsample: int = 1):
    print(f"Loading {subject} - {session}...", end='', flush=True)
    aligned_data, _ = load_and_align_data(subject, session)
    print(f" loaded {len(aligned_data)} devices")

    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=120_000) as client:
        for device, df in aligned_data.items():
            # Apply downsampling if requested
            if downsample > 1 and len(df) > 100000:
                original_len = len(df)
                df = df.iloc[::downsample]
                print(f"  {device}: downsampled {original_len:,} -> {len(df):,} points")
            write_df(client, df, device=device, subject=subject, session=session)


def main():
    parser = argparse.ArgumentParser(description="Ingest aligned accelerometer data into InfluxDB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Ingest all detected subject/session combinations")
    group.add_argument("--one", nargs=2, metavar=("SUBJECT", "SESSION"), help="Ingest a single subject and session")
    parser.add_argument("--downsample", type=int, default=1, metavar="N", help="Keep every Nth point (default: 1 = all points)")
    parser.add_argument("--skip", nargs="+", metavar="SUBJECT", help="Skip specific subjects")
    args = parser.parse_args()

    skip_subjects = set(args.skip or [])
    
    if args.all:
        combos: Dict[str, list] = get_available_subjects_sessions()
        total = 0
        for subject, sessions in combos.items():
            if subject in skip_subjects:
                print(f"Skipping {subject} (all sessions)")
                continue
            for session in sessions:
                print(f"Ingesting {subject} - {session} ...")
                ingest_subject_session(subject, session, downsample=args.downsample)
                total += 1
        print(f"Done. Ingested {total} subject-session combinations.")
    else:
        subject, session = args.one
        print(f"Ingesting {subject} - {session} ...")
        ingest_subject_session(subject, session, downsample=args.downsample)
        print("Done.")


if __name__ == "__main__":
    main()
