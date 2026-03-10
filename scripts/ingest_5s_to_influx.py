import argparse
from pathlib import Path
import pandas as pd
from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET, OUTPUT_ROOT, DATA_ROOT
from src.constants import PARTICIPANT_MAPPING

PARTICIPANTS_FILE = DATA_ROOT / 'participants_anonymized.csv'

def ingest_subject_5s(client: InfluxDBClient, subject: str):
    if subject not in PARTICIPANT_MAPPING:
        print(f"Skipping {subject} as it is not in PARTICIPANT_MAPPING")
        return

    subj_dir = OUTPUT_ROOT / "aligned" / subject
    if not subj_dir.exists():
        print(f"Directory not found for {subject}")
        return
        
    # Dashboard uses 'activity' to determine session
    session = 'activity'
        
    for file in subj_dir.glob("*_aligned_5s.csv"):
        device = file.name.split('_')[0] 
        print(f"Ingesting {subject} - {device} - 5s data...")
        
        df = pd.read_csv(file)
        if df.empty or "timestamp" not in df.columns:
            print(f"Skipping {file.name}: missing timestamp.")
            continue
            
        if device != "Calorimetry" and "acc_magnitude_5s" not in df.columns:
            print(f"Skipping {file.name}: missing expected accelerometer columns.")
            continue
            
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df = df.sort_values("timestamp")
        
        if df.empty:
            continue
            
        if device == "Calorimetry":
            if "HR" in df.columns:
                df["hr"] = pd.to_numeric(df["HR"], errors="coerce")
            if "METS" in df.columns:
                df["mets"] = pd.to_numeric(df["METS"], errors="coerce")
            
            # keep only relevant columns for calorimetry
            keep_cols = ["timestamp", "device", "subject", "session"]
            if "hr" in df.columns: keep_cols.append("hr")
            if "mets" in df.columns: keep_cols.append("mets")
            measurement_name = "calorimetry"
        else:
            df["magnitude"] = pd.to_numeric(df["acc_magnitude_5s"], errors="coerce")
            df = df.dropna(subset=['magnitude'])
            keep_cols = ["timestamp", "magnitude", "device", "subject", "session"]
            measurement_name = "accelerometer"
            
        df["device"] = device
        df["subject"] = subject
        df["session"] = session
        
        df = df[[c for c in keep_cols if c in df.columns]]
        df = df.set_index("timestamp")
        
        write_api = client.write_api(write_options=ASYNCHRONOUS)
        
        chunk_size = 50000
        if len(df) > chunk_size:
            for i in range(0, len(df), chunk_size):
                chunk = df.iloc[i:i+chunk_size]
                write_api.write(
                    bucket=INFLUX_BUCKET,
                    org=INFLUX_ORG,
                    record=chunk,
                    data_frame_measurement_name=measurement_name,
                    data_frame_tag_columns=["device", "subject", "session"],
                    write_precision=WritePrecision.MS
                )
            write_api.close()
        else:
            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=df,
                data_frame_measurement_name=measurement_name,
                data_frame_tag_columns=["device", "subject", "session"],
                write_precision=WritePrecision.MS
            )
            write_api.close()
        print(f"  -> Written {len(df):,} points for {device}.")

def ingest_participants(client: InfluxDBClient):
    """
    Ingest participant demographics into InfluxDB.
    """
    if not PARTICIPANTS_FILE.exists():
        print(f"Participants file not found: {PARTICIPANTS_FILE}")
        return
    
    print(f"\nIngesting participant demographics...")
    
    try:
        df = pd.read_csv(PARTICIPANTS_FILE)
    except Exception as e:
        print(f"  Error reading participants file: {e}")
        return
    
    if df.empty:
        print("  No participants found")
        return
    
    # Use a fixed timestamp for metadata
    ref_time = datetime(2024, 1, 1, 0, 0, 0)
    
    points = []
    for _, row in df.iterrows():
        # Extract subject ID (remove 'Diwah' prefix if present)
        subject_id = str(row['ID']).replace('Diwah', '')
        
        if subject_id not in PARTICIPANT_MAPPING:
            continue
        
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
                "length_cm": float(row.get('Length_cm', 0)) if pd.notna(row.get('Length_cm')) else 0.0,
                "weight_kg": float(row.get('Weight_kg', 0)) if pd.notna(row.get('Weight_kg')) else 0.0,
                "age_years": int(row.get('Age_years', 0)) if pd.notna(row.get('Age_years')) else 0,
                "bmi": float(row.get('BMI_kg_m2', 0)) if pd.notna(row.get('BMI_kg_m2')) else 0.0
            }
        }
        points.append(point)
    
    from influxdb_client.client.write_api import SYNCHRONOUS
    write_api = client.write_api(write_options=SYNCHRONOUS)
    write_api.write(
        bucket=INFLUX_BUCKET,
        org=INFLUX_ORG,
        record=points,
        write_precision=WritePrecision.S
    )
    print(f"  -> Written {len(points)} participant demographic records.")

def main():
    parser = argparse.ArgumentParser(description="Ingest 5s aligned accelerometer data into InfluxDB")
    parser.add_argument("--subject", type=str, help="Ingest a single subject. If omitted, ingests all subjects in output/aligned/.")
    args = parser.parse_args()
    
    aligned_dir = OUTPUT_ROOT / "aligned"
    if not aligned_dir.exists():
        print(f"No aligned data found at {aligned_dir}")
        return
        
    subjects_to_ingest = []
    if args.subject:
        subjects_to_ingest = [args.subject]
    else:
        subjects_to_ingest = [d.name for d in aligned_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        
    print(f"Connecting to {INFLUX_URL}")
    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=120_000) as client:
        try:
            health = client.health()
            if health.status != "pass":
                print(f"Database health check failed: {health.status}")
                return
        except Exception as e:
            print(f"Failed to connect to DB: {e}")
            return
            
        for subject in subjects_to_ingest:
            ingest_subject_5s(client, subject)
            
        # Also ingest participants whenever we ingest data
        ingest_participants(client)

    print("Done!")

if __name__ == "__main__":
    main()
