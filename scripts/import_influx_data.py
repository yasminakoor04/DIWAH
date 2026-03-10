#!/usr/bin/env python3
"""
Import InfluxDB data from exported Line Protocol files.

This script restores data exported by export_influx_data.py to an InfluxDB instance.
Use this to seed a new server deployment.

Usage:
    python scripts/import_influx_data.py influxdb-backups/export/backup_YYYYMMDD_HHMMSS
"""

import argparse
import sys
from pathlib import Path

from influxdb_client import InfluxDBClient, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET


def import_line_protocol_file(client: InfluxDBClient, lp_file: Path) -> int:
    """
    Import a Line Protocol file into InfluxDB.
    
    Returns:
        Number of lines imported
    """
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    # Read file and write in batches
    batch_size = 5000
    batch = []
    count = 0
    
    with open(lp_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            batch.append(line)
            count += 1
            
            if len(batch) >= batch_size:
                write_api.write(
                    bucket=INFLUX_BUCKET,
                    record=batch,
                    write_precision=WritePrecision.NS
                )
                batch = []
    
    # Write remaining
    if batch:
        write_api.write(
            bucket=INFLUX_BUCKET,
            record=batch,
            write_precision=WritePrecision.NS
        )
    
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Import InfluxDB data from Line Protocol backup"
    )
    parser.add_argument(
        "backup_dir",
        type=str,
        help="Path to backup directory containing .lp files"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be imported without writing"
    )
    args = parser.parse_args()
    
    backup_dir = Path(args.backup_dir)
    
    if not backup_dir.exists():
        print(f"ERROR: Backup directory not found: {backup_dir}")
        sys.exit(1)
    
    print("InfluxDB Data Import")
    print("=" * 60)
    print(f"Source: {backup_dir}")
    print(f"Target: {INFLUX_URL} / {INFLUX_BUCKET}")
    print()
    
    # Check for .lp files
    lp_files = list(backup_dir.glob("*.lp"))
    if not lp_files:
        print("ERROR: No .lp files found in backup directory")
        sys.exit(1)
    
    print(f"Found {len(lp_files)} data files: {', '.join(f.stem for f in lp_files)}")
    print()
    
    if args.dry_run:
        print("*** DRY RUN MODE - No data will be written ***")
        print()
        for lp_file in lp_files:
            line_count = sum(1 for _ in open(lp_file, 'r', encoding='utf-8'))
            print(f"  {lp_file.stem}: {line_count:,} points")
        return
    
    # Connect
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    
    # Check connection
    health = client.health()
    if health.status != "pass":
        print(f"ERROR: Database health check failed: {health.status}")
        sys.exit(1)
    
    print("Connected to InfluxDB")
    print()
    
    # Import each file
    total = 0
    for lp_file in lp_files:
        print(f"Importing {lp_file.stem}...", end=" ", flush=True)
        count = import_line_protocol_file(client, lp_file)
        print(f"{count:,} points")
        total += count
    
    client.close()
    
    print()
    print("=" * 60)
    print(f"Import complete! {total:,} total points imported")


if __name__ == "__main__":
    main()
