from influxdb_client import InfluxDBClient
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60_000) as client:
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -100y, stop: 100y)
      |> filter(fn: (r) => r["_measurement"] == "accelerometer")
      |> filter(fn: (r) => r["subject"] == "2002")
      |> filter(fn: (r) => r["session"] == "activity")
      |> filter(fn: (r) => r["_field"] == "magnitude")
      |> group(columns: ["device"])
      |> sort(columns: ["_time"])
    '''
    
    tables = client.query_api().query(query)
    
    for table in tables:
        device = table.records[0].values.get("device", "unknown")
        if table.records:
            first_time = table.records[0].get_time()
            last_time = table.records[-1].get_time()
            count = len(table.records)
            print(f"\n{device}:")
            print(f"  First timestamp: {first_time}")
            print(f"  Last timestamp:  {last_time}")
            print(f"  Total records:   {count}")
