#!/usr/bin/env python3
"""
Verify InfluxDB contents - Show what data is stored in the database.

Usage:
    python scripts/verify_influx.py
"""

from influxdb_client import InfluxDBClient
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET


def main():
    print("InfluxDB Verification Tool")
    print("=" * 60)
    print(f"URL:    {INFLUX_URL}")
    print(f"Org:    {INFLUX_ORG}")
    print(f"Bucket: {INFLUX_BUCKET}")
    print()

    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60_000) as client:
        # Check connection
        try:
            health = client.health()
            print(f"✓ Connected: InfluxDB status = {health.status}")
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            print("\nMake sure InfluxDB is running:")
            print("  docker-compose up -d influxdb")
            sys.exit(1)
        
        query_api = client.query_api()
        
        # Get measurements
        print("\nMeasurements:")
        meas_query = f'''
        import "influxdata/influxdb/schema"
        schema.measurements(bucket: "{INFLUX_BUCKET}")
        '''
        try:
            measurements = []
            for table in query_api.query(meas_query):
                for rec in table.records:
                    measurements.append(rec.get_value())
            
            if measurements:
                for m in measurements:
                    print(f"  • {m}")
            else:
                print("  (none)")
        except Exception as e:
            print(f"  Error: {e}")
        
        # Get subjects
        print("\nSubjects:")
        subj_query = f'''
        import "influxdata/influxdb/schema"
        schema.tagValues(bucket: "{INFLUX_BUCKET}", tag: "subject", start: -100y)
        '''
        try:
            subjects = []
            for table in query_api.query(subj_query):
                for rec in table.records:
                    subjects.append(rec.get_value())
            
            if subjects:
                print(f"  {len(subjects)} subjects: {', '.join(sorted(subjects)[:10])}", end="")
                if len(subjects) > 10:
                    print(f" ... and {len(subjects) - 10} more")
                else:
                    print()
            else:
                print("  (none)")
        except Exception as e:
            print(f"  Error: {e}")
        
        # Get sessions
        print("\nSessions:")
        sess_query = f'''
        import "influxdata/influxdb/schema"
        schema.tagValues(bucket: "{INFLUX_BUCKET}", tag: "session", start: -100y)
        '''
        try:
            sessions = []
            for table in query_api.query(sess_query):
                for rec in table.records:
                    sessions.append(rec.get_value())
            
            if sessions:
                print(f"  {', '.join(sorted(sessions))}")
            else:
                print("  (none)")
        except Exception as e:
            print(f"  Error: {e}")
        
        # Get devices
        print("\nDevices:")
        dev_query = f'''
        import "influxdata/influxdb/schema"
        schema.tagValues(bucket: "{INFLUX_BUCKET}", tag: "device", start: -100y)
        '''
        try:
            devices = []
            for table in query_api.query(dev_query):
                for rec in table.records:
                    devices.append(rec.get_value())
            
            if devices:
                print(f"  {', '.join(sorted(devices))}")
            else:
                print("  (none)")
        except Exception as e:
            print(f"  Error: {e}")
        
        # Get total point count
        print("\nData Summary:")
        count_query = f'''
        from(bucket: "{INFLUX_BUCKET}")
            |> range(start: -100y)
            |> count()
        '''
        try:
            total = 0
            for table in query_api.query(count_query):
                for rec in table.records:
                    total += rec.get_value()
            
            print(f"  Total data points: {total:,}")
        except Exception as e:
            print(f"  Error counting points: {e}")
        
        # Get time range
        print("\nTime Range:")
        range_query = f'''
        from(bucket: "{INFLUX_BUCKET}")
            |> range(start: -100y)
            |> drop(columns: ["_value"])
            |> group()
            |> sort(columns: ["_time"])
            |> limit(n: 1)
        '''
        try:
            first_time = None
            for table in query_api.query(range_query):
                for rec in table.records:
                    first_time = rec.get_time()
                    break
            
            range_query_last = f'''
            from(bucket: "{INFLUX_BUCKET}")
                |> range(start: -100y)
                |> drop(columns: ["_value"])
                |> group()
                |> sort(columns: ["_time"], desc: true)
                |> limit(n: 1)
            '''
            last_time = None
            for table in query_api.query(range_query_last):
                for rec in table.records:
                    last_time = rec.get_time()
                    break
            
            if first_time and last_time:
                print(f"  Earliest: {first_time}")
                print(f"  Latest:   {last_time}")
            else:
                print("  (no data)")
        except Exception as e:
            print(f"  Error: {e}")
        
        print("\n" + "=" * 60)
        
        if total > 0:
            print("✓ Database contains data and is ready for the dashboard.")
        else:
            print("⚠ Database is empty. Run ingestion script:")
            print("  python scripts/ingest_all_data.py")


if __name__ == "__main__":
    main()
