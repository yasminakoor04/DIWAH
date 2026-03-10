#!/usr/bin/env python3
"""
Ingest pre-aligned data from output/aligned/ folder into InfluxDB.

This script reads the aligned 5-second epoch data that has already been
processed and synchronized between devices.

Data format in output/aligned/{subject}/:
- Actigraph_aligned_5s.csv: timestamp, acc_magnitude_5s
- Bangle_aligned_5s.csv: timestamp, acc_magnitude_5s
- EmotiBit_aligned_5s.csv: timestamp, acc_magnitude_5s
- Calorimetry_aligned_5s.csv: timestamp, HR, METS

Usage:
    python scripts/ingest_aligned_data.py              # Ingest all subjects
    python scripts/ingest_aligned_data.py --subject 2002  # Single subject
    python scripts/ingest_aligned_data.py --dry-run    # Preview without writing
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET, OUTPUT_ROOT, DATA_ROOT

# Aligned data directory
ALIGNED_DIR = OUTPUT_ROOT / 'aligned'

# Participants file (still in diwah-anonymized for now)
PARTICIPANTS_FILE = DATA_ROOT / 'participants_anonymized.csv'


def ingest_subject(client: InfluxDBClient, subject: str, dry_run: bool = False) -> Dict[str, int]:
    """
    Ingest all aligned data for a single subject.
    
    Supports both folder structures:
    - Old: output/aligned/{subject}/*.csv (all treated as activity)
    - New: output/aligned/{subject}/{session}/*.csv
    
    Returns:
        Dict with counts per device
    """
    subject_dir = ALIGNED_DIR / subject
    if not subject_dir.exists():
        print(f"  Subject directory not found: {subject_dir}")
        return {}
    
    counts = {'actigraph': 0, 'bangle': 0, 'emotibit': 0, 'calorimetry': 0}
    
    # Check for session subfolders (new structure)
    activity_dir = subject_dir / 'activity'
    rest_dir = subject_dir / 'rest'
    
    if activity_dir.exists() or rest_dir.exists():
        # New structure with session subfolders
        for session in ['activity', 'rest']:
            session_dir = subject_dir / session
            if not session_dir.exists():
                continue
                
            print(f"  Processing {session} session...")
            session_counts = ingest_session(client, subject, session, session_dir, dry_run)
            
            for device, count in session_counts.items():
                counts[device] = counts.get(device, 0) + count
    else:
        # Old structure - files directly in subject folder (treat as activity)
        print(f"  Processing activity session (legacy structure)...")
        session_counts = ingest_session(client, subject, 'activity', subject_dir, dry_run)
        counts = session_counts
    
    return counts


def ingest_session(client: InfluxDBClient, subject: str, session: str, session_dir: Path, dry_run: bool = False) -> Dict[str, int]:
    """
    Ingest aligned data for a single session (activity or rest).
    
    Returns:
        Dict with counts per device
    """
    counts = {}
    
    # Define file mappings
    device_files = {
        'actigraph': 'Actigraph_aligned_5s.csv',
        'bangle': 'Bangle_aligned_5s.csv',
        'emotibit': 'EmotiBit_aligned_5s.csv',
    }
    
    # Ingest accelerometer data (Actigraph, Bangle, EmotiBit)
    for device, filename in device_files.items():
        file_path = session_dir / filename
        if not file_path.exists():
            continue
            
        try:
            df = pd.read_csv(file_path, parse_dates=['timestamp'])
            if df.empty:
                continue
            
            # Drop rows with NaT timestamps or NaN values
            df = df.dropna(subset=['timestamp', 'acc_magnitude_5s'])
            if df.empty:
                continue
                
            points = []
            for _, row in df.iterrows():
                point = {
                    "measurement": "accelerometer",
                    "tags": {
                        "subject": subject,
                        "device": device,
                        "session": session
                    },
                    "time": row['timestamp'].to_pydatetime(),
                    "fields": {
                        "magnitude": float(row['acc_magnitude_5s'])
                    }
                }
                points.append(point)
            
            if points:
                if dry_run:
                    print(f"    {device.title()}: would write {len(points)} points")
                else:
                    write_api = client.write_api(write_options=SYNCHRONOUS)
                    write_api.write(
                        bucket=INFLUX_BUCKET,
                        record=points,
                        write_precision=WritePrecision.S
                    )
                    print(f"    {device.title()}: {len(points)} points")
                counts[device] = len(points)
                
        except Exception as e:
            print(f"    {device.title()}: Error - {e}")
    
    # Ingest calorimetry data (only for activity sessions typically)
    cal_file = session_dir / 'Calorimetry_aligned_5s.csv'
    if cal_file.exists():
        try:
            df = pd.read_csv(cal_file, parse_dates=['timestamp'])
            if not df.empty:
                points = []
                for _, row in df.iterrows():
                    fields = {}
                    if 'HR' in row and pd.notna(row['HR']):
                        fields['hr'] = float(row['HR'])
                    if 'METS' in row and pd.notna(row['METS']):
                        fields['mets'] = float(row['METS'])
                    
                    if fields:
                        point = {
                            "measurement": "calorimetry",
                            "tags": {
                                "subject": subject,
                                "device": "calorimetry",
                                "session": session
                            },
                            "time": row['timestamp'].to_pydatetime(),
                            "fields": fields
                        }
                        points.append(point)
                
                if points:
                    if dry_run:
                        print(f"    Calorimetry: would write {len(points)} points")
                    else:
                        write_api = client.write_api(write_options=SYNCHRONOUS)
                        write_api.write(
                            bucket=INFLUX_BUCKET,
                            record=points,
                            write_precision=WritePrecision.S
                        )
                        print(f"    Calorimetry: {len(points)} points")
                    counts['calorimetry'] = len(points)
                    
        except Exception as e:
            print(f"    Calorimetry: Error - {e}")
    
    return counts


def ingest_participants(client: InfluxDBClient, dry_run: bool = False) -> int:
    """
    Ingest participant demographics into InfluxDB.
    """
    if not PARTICIPANTS_FILE.exists():
        print(f"Participants file not found: {PARTICIPANTS_FILE}")
        return 0
    
    print(f"\nIngesting participant demographics...")
    
    try:
        df = pd.read_csv(PARTICIPANTS_FILE)
    except Exception as e:
        print(f"  Error reading participants file: {e}")
        return 0
    
    if df.empty:
        print("  No participants found")
        return 0
    
    # Use a fixed timestamp for metadata
    ref_time = datetime(2024, 1, 1, 0, 0, 0)
    
    points = []
    for _, row in df.iterrows():
        # Extract subject ID (remove 'Diwah' prefix if present)
        subject_id = str(row['ID']).replace('Diwah', '')
        
        # Map Swedish gender to English
        gender = row.get('Gender', '')
        if gender == 'Kvinna':
            gender = 'Female'
        elif gender == 'Man':
            gender = 'Male'
        
        point = {
            "measurement": "participants",
            "tags": {
                "subject": subject_id,
                "gender": gender
            },
            "time": ref_time,
            "fields": {
                "length_cm": float(row.get('Length_cm', 0)),
                "weight_kg": float(row.get('Weight_kg', 0)),
                "age_years": int(row.get('Age_years', 0)),
                "bmi": float(row.get('BMI_kg_m2', 0))
            }
        }
        points.append(point)
    
    if dry_run:
        print(f"  Would write {len(points)} participant records")
    else:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(
            bucket=INFLUX_BUCKET,
            record=points,
            write_precision=WritePrecision.S
        )
        print(f"  Wrote {len(points)} participant records")
    
    return len(points)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest pre-aligned DIWAH data from output/aligned/ into InfluxDB"
    )
    parser.add_argument(
        "--subject", "-s",
        type=str,
        help="Ingest only a specific subject (e.g., 2002)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be ingested without writing"
    )
    parser.add_argument(
        "--skip-participants",
        action="store_true",
        help="Skip ingesting participant demographics"
    )
    args = parser.parse_args()
    
    print("DIWAH Aligned Data Ingestion")
    print("=" * 60)
    print(f"Source:  {ALIGNED_DIR}")
    print(f"Target:  {INFLUX_URL} / {INFLUX_BUCKET}")
    print()
    
    if not ALIGNED_DIR.exists():
        print(f"ERROR: Aligned data directory not found: {ALIGNED_DIR}")
        sys.exit(1)
    
    # Discover subjects
    subjects = sorted([d.name for d in ALIGNED_DIR.iterdir() if d.is_dir()])
    
    if not subjects:
        print("ERROR: No subject directories found")
        sys.exit(1)
    
    print(f"Found {len(subjects)} subjects: {', '.join(subjects[:10])}{'...' if len(subjects) > 10 else ''}")
    print()
    
    if args.subject:
        if args.subject not in subjects:
            print(f"ERROR: Subject {args.subject} not found")
            sys.exit(1)
        subjects = [args.subject]
    
    if args.dry_run:
        print("*** DRY RUN MODE - No data will be written ***\n")
    
    # Connect to InfluxDB
    print(f"Connecting to {INFLUX_URL}...")
    
    try:
        client = InfluxDBClient(
            url=INFLUX_URL,
            token=INFLUX_TOKEN,
            org=INFLUX_ORG,
            timeout=120_000
        )
        
        if not args.dry_run:
            health = client.health()
            if health.status != "pass":
                print(f"ERROR: Database health check failed: {health.status}")
                sys.exit(1)
        
        print("Connected!\n")
        
    except Exception as e:
        print(f"ERROR: Failed to connect: {e}")
        sys.exit(1)
    
    # Ingest participants first
    participants_count = 0
    if not args.skip_participants:
        participants_count = ingest_participants(client, dry_run=args.dry_run)
    
    # Ingest aligned data
    total_counts = {'actigraph': 0, 'bangle': 0, 'emotibit': 0, 'calorimetry': 0}
    
    for subject in subjects:
        print(f"\nSubject: {subject}")
        counts = ingest_subject(client, subject, dry_run=args.dry_run)
        for device, count in counts.items():
            total_counts[device] += count
    
    # Summary
    print(f"\n{'='*60}")
    print("INGESTION COMPLETE")
    print(f"{'='*60}")
    print("\nTotal points ingested:")
    
    if participants_count > 0:
        print(f"  {'Participants':12} {participants_count:>10,} records")
    
    for device, count in total_counts.items():
        if count > 0:
            print(f"  {device.title():12} {count:>10,} points")
    
    total = sum(total_counts.values())
    print(f"  {'TOTAL':12} {total:>10,} points")
    
    if args.dry_run:
        print("\n*** This was a dry run - no data was actually written ***")
    
    client.close()


if __name__ == "__main__":
    main()
