import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path so we can import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET
from influxdb_client import InfluxDBClient

def export_data():
    print(f"Connecting to InfluxDB at {INFLUX_URL}...")
    
    # Increase timeout since exporting a whole bucket can take a while if it's large
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=600000)
    query_api = client.query_api()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    export_file = output_dir / f"cumulus_export_{timestamp}.csv"
    
    print(f"Exporting all data from bucket '{INFLUX_BUCKET}'...")
    print(f"Writing to: {export_file}")
    print("This may take a few minutes depending on database size. Please wait...")
    
    flux_query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: 0)
    '''
    
    try:
        # We use query_csv to stream results directly to an annotated CSV 
        # which is the exact format InfluxDB requires for importing
        csv_result = query_api.query_csv(flux_query)
        
        with open(export_file, 'w', encoding='utf-8') as f:
            for row in csv_result:
                # Ensure fields with commas are quoted
                safe_row = [f'"{str(val)}"' if ',' in str(val) else str(val) for val in row]
                f.write(','.join(safe_row) + '\n')
                
        print(f"\n✅ Export successful! File saved to: {export_file}")
        print("\nTo push this to Cumulus, use the Influx CLI on the target server:")
        print(f"influx write -b <CUMULUS_BUCKET> -f {export_file.name}")
        
    except Exception as e:
        print(f"\n❌ Export failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    export_data()
