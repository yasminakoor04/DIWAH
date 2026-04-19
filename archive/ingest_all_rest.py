#!/usr/bin/env python3
"""
Unified script to ingest ALL rest sessions directly into InfluxDB.
Ensures all data is downsampled to 5s epochs before ingestion.
Handles:
- Bangle (from _rest.csv files)
- EmotiBit (from _rest folders)
- Actigraph (dynamically extracts rest from 5sec.csv based on Calorimetry start times)
"""

import sys
from pathlib import Path
import pandas as pd
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import re
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET, DATA_ROOT
from src.backend.parsers import BangleParser, EmotibitParser
from src.constants import PARTICIPANT_MAPPING

# Paths
BANGLE_DIR = DATA_ROOT / "Bangle"
EMOTIBIT_DIR = DATA_ROOT / "emotibit"
ACTIGRAPH_DIR = DATA_ROOT / "Actigraph (research device accelerometry)"
ALIGNED_OUTPUT_DIR = Path(r"c:\Users\yasmi\Downloads\diwah-anonymized\output\aligned")

def get_db_client():
    return InfluxDBClient(
        url=INFLUX_URL, 
        token=INFLUX_TOKEN, 
        org=INFLUX_ORG,
        timeout=60000
    )

def ingest_bangle_rest(write_api):
    print("\n--- Ingesting Bangle Rest Data ---")
    if not BANGLE_DIR.exists():
        print(f"Directory not found: {BANGLE_DIR}")
        return
        
    rest_files = list(BANGLE_DIR.glob("*_rest.csv"))
    if not rest_files:
        print("No files found.")
        return
        
    for file in sorted(rest_files):
        subject = file.stem.split('_')[0]
        if subject not in PARTICIPANT_MAPPING:
            continue
        print(f"Processing Bangle {subject}...")
        
        try:
            cal_file = ALIGNED_OUTPUT_DIR / subject / 'Calorimetry_aligned_5s.csv'
            if cal_file.exists():
                cal_df = pd.read_csv(cal_file)
                if not cal_df.empty:
                    activity_start = pd.to_datetime(cal_df['timestamp'].iloc[0])
                else:
                    activity_start = pd.to_datetime('2024-01-01 12:00:00')
                    print(f"  Warning: Calorimetry empty. Using fallback timeline for Bangle.")
            else:
                activity_start = pd.to_datetime('2024-01-01 12:00:00')
                print(f"  Warning: No Calorimetry. Using fallback timeline for Bangle.")

            df = BangleParser.parse_file(file)
            if df.empty or 'cumulative_time_ms' not in df.columns: continue
            
            rel_ms = df['cumulative_time_ms'] - df['cumulative_time_ms'].min()
            relative_td = pd.to_timedelta(rel_ms, unit='ms')
            df['timestamp'] = activity_start - relative_td.max() + relative_td
            df = df.dropna(subset=['timestamp'])
            
            df.set_index('timestamp', inplace=True)
            resampled = df['acc_magnitude'].resample('5s').mean().reset_index().dropna()
            
            points = []
            for _, row in resampled.iterrows():
                points.append({
                    "measurement": "accelerometer",
                    "tags": {"subject": subject, "device": "bangle", "session": "rest"},
                    "time": row['timestamp'].to_pydatetime(),
                    "fields": {"magnitude": float(row['acc_magnitude'])}
                })
                
            if points:
                write_api.write(bucket=INFLUX_BUCKET, record=points, write_precision=WritePrecision.S)
                print(f"  Written {len(points)} Bangle points")
        except Exception as e:
            print(f"  Error on Bangle {subject}: {e}")

def ingest_emotibit_rest(write_api):
    print("\n--- Ingesting EmotiBit Rest Data ---")
    if not EMOTIBIT_DIR.exists():
        print(f"Directory not found: {EMOTIBIT_DIR}")
        return
        
    rest_dirs = list(EMOTIBIT_DIR.glob("*_rest"))
    if not rest_dirs:
        print("No directories found.")
        return
        
    for rest_dir in sorted(rest_dirs):
        subject = rest_dir.name.split('_')[0]
        if subject not in PARTICIPANT_MAPPING:
            continue
        print(f"Processing EmotiBit {subject}...")
        
        csv_files = list(rest_dir.glob("*.csv"))
        if not csv_files: continue
            
        try:
            cal_file = ALIGNED_OUTPUT_DIR / subject / 'Calorimetry_aligned_5s.csv'
            if cal_file.exists():
                cal_df = pd.read_csv(cal_file)
                if not cal_df.empty:
                    activity_start = pd.to_datetime(cal_df['timestamp'].iloc[0])
                else:
                    activity_start = pd.to_datetime('2024-01-01 12:00:00')
                    print(f"  Warning: Calorimetry empty. Using fallback timeline for EmotiBit.")
            else:
                activity_start = pd.to_datetime('2024-01-01 12:00:00')
                print(f"  Warning: No Calorimetry. Using fallback timeline for EmotiBit.")

            df = EmotibitParser.parse_csv_file(csv_files[0])
            acc_df = EmotibitParser.extract_accelerometer(df)
            if acc_df.empty: continue
            
            acc_df['timestamp'] = pd.to_numeric(acc_df['timestamp'], errors='coerce')
            acc_df = acc_df.dropna(subset=['timestamp'])
            
            rel_ms = acc_df['timestamp'] - acc_df['timestamp'].min()
            relative_td = pd.to_timedelta(rel_ms, unit='ms')
            acc_df['dt'] = activity_start - relative_td.max() + relative_td
            acc_df.set_index('dt', inplace=True)
            
            resampled = acc_df['acc_magnitude'].resample('5s').mean().reset_index().dropna()
            
            points = []
            for _, row in resampled.iterrows():
                points.append({
                    "measurement": "accelerometer",
                    "tags": {"subject": subject, "device": "emotibit", "session": "rest"},
                    "time": row['dt'].to_pydatetime(),
                    "fields": {"magnitude": float(row['acc_magnitude'])}
                })
                
            if points:
                write_api.write(bucket=INFLUX_BUCKET, record=points, write_precision=WritePrecision.S)
                print(f"  Written {len(points)} EmotiBit points")
        except Exception as e:
            print(f"  Error on EmotiBit {subject}: {e}")

def ingest_actigraph_rest(write_api):
    print("\n--- Ingesting Actigraph Rest Data ---")
    if not ACTIGRAPH_DIR.exists():
        print(f"Directory not found: {ACTIGRAPH_DIR}")
        return
        
    files = list(ACTIGRAPH_DIR.glob("*5sec.csv"))
    if not files:
        print("No files found.")
        return
        
    for file in files:
        match = re.search(r'^(\d{4})', file.name)
        if not match: continue
        subject = match.group(1)
        if subject not in PARTICIPANT_MAPPING:
            continue
        print(f"Processing Actigraph {subject}...")
        
        activity_start = None
        cal_file = ALIGNED_OUTPUT_DIR / subject / 'Calorimetry_aligned_5s.csv'
        if cal_file.exists():
            cal_df = pd.read_csv(cal_file)
            if not cal_df.empty:
                activity_start = pd.to_datetime(cal_df['timestamp'].iloc[0])
            else:
                print("  Warning: Calorimetry file empty. Will assume first 15 mins is Rest.")
        else:
            print("  Warning: No Calorimetry file. Will assume first 15 mins is Rest.")
            
        try:
            
            with open(file, 'r') as f:
                lines = [next(f) for _ in range(10)]
            
            time_str = next((l.split('Start Time ')[1].strip() for l in lines if 'Start Time' in l), None)
            date_str = next((l.split('Start Date ')[1].strip() for l in lines if 'Start Date' in l), None)
            
            if not time_str or not date_str: continue
            start_dt = pd.to_datetime(f"{date_str} {time_str}")
            
            if activity_start is None:
                activity_start = start_dt + pd.Timedelta(minutes=15)
            
            if (activity_start - start_dt).total_seconds() <= 0: continue
            
            df = pd.read_csv(file, skiprows=10)
            if df.empty or len(df.columns) < 3: continue
            
            df['magnitude'] = np.sqrt(df[df.columns[0]]**2 + df[df.columns[1]]**2 + df[df.columns[2]]**2)
            df['dt'] = [start_dt + pd.Timedelta(seconds=5 * i) for i in range(len(df))]
            
            df_rest = df[df['dt'] < activity_start]
            
            points = []
            for _, row in df_rest.iterrows():
                points.append({
                    "measurement": "accelerometer",
                    "tags": {"subject": subject, "device": "actigraph", "session": "rest"},
                    "time": row['dt'].to_pydatetime(),
                    "fields": {"magnitude": float(row['magnitude']) / 1000.0 + 1.0}
                })
                
            if points:
                write_api.write(bucket=INFLUX_BUCKET, record=points, write_precision=WritePrecision.S)
                print(f"  Written {len(points)} Actigraph points")
                
        except Exception as e:
            print(f"  Error on Actigraph {subject}: {e}")

def main():
    client = get_db_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    print("STARTING UNIFIED REST DATA INGESTION")
    print("=" * 40)
    
    ingest_bangle_rest(write_api)
    ingest_emotibit_rest(write_api)
    ingest_actigraph_rest(write_api)
    
    client.close()
    print("\n================================")
    print("ALL REST DATA INGESTION COMPLETE")

if __name__ == '__main__':
    main()
