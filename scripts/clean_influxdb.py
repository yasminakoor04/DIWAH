import sys
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from influxdb_client import InfluxDBClient
from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

def main():
    parser = argparse.ArgumentParser(description="Clean InfluxDB Database Bucket")
    parser.add_argument("--force", action="store_true", help="Vaporize and recreate the bucket without asking for confirmation")
    args = parser.parse_args()

    print(f"Connecting to InfluxDB at {INFLUX_URL}...")
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60000)
    
    try:
        health = client.health()
        if health.status != "pass":
            print(f"Database health check failed: {health.status}")
            return
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return

    buckets_api = client.buckets_api()
    bucket = buckets_api.find_bucket_by_name(INFLUX_BUCKET)
    
    if bucket:
        if not args.force:
            response = input(f"WARNING: This will completely destroy the '{INFLUX_BUCKET}' bucket and all its data. Are you sure? (y/N): ")
            if response.lower() != 'y':
                print("Operation cancelled.")
                return
                
        print(f"Destroying bucket '{INFLUX_BUCKET}' to flush schema cache...")
        buckets_api.delete_bucket(bucket.id)
    else:
        print(f"Bucket '{INFLUX_BUCKET}' does not exist yet. Creating it...")
        
    print(f"Finding organization '{INFLUX_ORG}'...")
    orgs_api = client.organizations_api()
    orgs = orgs_api.find_organizations(org=INFLUX_ORG)
    
    if not orgs:
        print(f"Error: Organization '{INFLUX_ORG}' not found.")
        return
        
    org_id = orgs[0].id
    
    print(f"Creating bucket '{INFLUX_BUCKET}'...")
    buckets_api.create_bucket(bucket_name=INFLUX_BUCKET, org_id=org_id)
    print(f"Success! The '{INFLUX_BUCKET}' database bucket is completely clean and ready for ingestion.")

if __name__ == '__main__':
    main()
