import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime, timedelta
from parsers import ActigraphParser, BangleParser, EmotibitParser
from src.config import ACTIGRAPH_PATH, BANGLE_PATH, EMOTIBIT_PATH, PLOTS_PATH

def get_session_start_time(subject_id, session_type, device):
    if device == 'actigraph':
        # Actigraph has timestamps in the file
        return None  # Will use the timestamps from the file
    
    elif device == 'bangle':
        # Try to extract from filename or use Actigraph time as reference
        bangle_file = BANGLE_PATH / f"{subject_id}_{session_type}.csv"
        if bangle_file.exists():
            # File modification time as fallback
            import os
            mtime = os.path.getmtime(bangle_file)
            return datetime.fromtimestamp(mtime)
        return None
    
    elif device == 'emotibit':
        # Emotibit has timestamp in the filename
        emotibit_dir = EMOTIBIT_PATH / f"{subject_id}_{session_type}"
        if emotibit_dir.exists():
            csv_files = list(emotibit_dir.glob("*.csv"))
            if csv_files:
                # Extract timestamp from filename like "2024-05-14_09-41-01-184452.csv"
                filename = csv_files[0].stem
                try:
                    # Parse "2024-05-14_09-41-01"
                    date_str = filename.split('-184452')[0]  # Remove microseconds
                    dt = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                    return dt
                except:
                    pass
        return None

def load_and_align_data(subject_id, session_type):
    print(f"\n{'='*70}")
    print(f"Loading and aligning data for Subject {subject_id} - {session_type}")
    print(f"{'='*70}\n")
    
    aligned_data = {}
    reference_time = None
    
    # 1. Load Actigraph (has absolute timestamps - use as reference)
    print("Loading Actigraph data...")
    actigraph_pattern = f"{subject_id}*RAW.csv"
    actigraph_files = list(ACTIGRAPH_PATH.glob(actigraph_pattern))
    
    if actigraph_files:
        # Use smaller file for testing, or first file
        acti_file = None
        for f in actigraph_files:
            if f.stat().st_size < 50*1024*1024:  # Less than 50MB
                acti_file = f
                break
        if not acti_file and actigraph_files:
            acti_file = actigraph_files[0]
        
        if acti_file:
            df_acti = ActigraphParser.parse_raw_file(acti_file)
            reference_time = df_acti['timestamp'].min()
            df_acti['device'] = 'Actigraph'
            aligned_data['actigraph'] = df_acti
            print(f"   Loaded {len(df_acti):,} samples")
            print(f"   Start time: {reference_time}")
            print(f"   End time: {df_acti['timestamp'].max()}")
    
    # 2. Load Bangle
    print("\nLoading Bangle data...")
    bangle_file = BANGLE_PATH / f"{subject_id}_{session_type}.csv"
    if bangle_file.exists():
        df_bangle = BangleParser.parse_file(bangle_file)
        
        # Align to reference time
        if reference_time:
            # Convert cumulative milliseconds to timedelta
            df_bangle['timestamp'] = reference_time + pd.to_timedelta(df_bangle['cumulative_time_ms'], unit='ms')
        else:
            # Use file modification time as fallback
            bangle_start = get_session_start_time(subject_id, session_type, 'bangle')
            if bangle_start:
                df_bangle['timestamp'] = bangle_start + pd.to_timedelta(df_bangle['cumulative_time_ms'], unit='ms')
        
        df_bangle['device'] = 'Bangle'
        aligned_data['bangle'] = df_bangle
        print(f"   Loaded {len(df_bangle):,} samples")
        if 'timestamp' in df_bangle.columns:
            print(f"   Start time: {df_bangle['timestamp'].min()}")
            print(f"   End time: {df_bangle['timestamp'].max()}")
    
    # 3. Load Emotibit
    print("\nLoading Emotibit data...")
    emotibit_dir = EMOTIBIT_PATH / f"{subject_id}_{session_type}"
    if emotibit_dir.exists():
        csv_files = list(emotibit_dir.glob("*.csv"))
        if csv_files:
            df_emoti_raw = EmotibitParser.parse_csv_file(csv_files[0])
            df_emoti = EmotibitParser.extract_accelerometer(df_emoti_raw)
            
            # Get Emotibit start time from filename
            emotibit_start = get_session_start_time(subject_id, session_type, 'emotibit')
            
            if emotibit_start:
                # Convert local_timestamp (milliseconds) to datetime
                df_emoti['timestamp'] = emotibit_start + pd.to_timedelta(df_emoti['timestamp'] - df_emoti['timestamp'].min(), unit='ms')
            elif reference_time:
                # Use Actigraph reference time
                df_emoti['timestamp'] = reference_time + pd.to_timedelta(df_emoti['timestamp'] - df_emoti['timestamp'].min(), unit='ms')
            
            df_emoti['device'] = 'Emotibit'
            aligned_data['emotibit'] = df_emoti
            print(f"   Loaded {len(df_emoti):,} samples")
            if 'timestamp' in df_emoti.columns and pd.api.types.is_datetime64_any_dtype(df_emoti['timestamp']):
                print(f"   Start time: {df_emoti['timestamp'].min()}")
                print(f"   End time: {df_emoti['timestamp'].max()}")
    
    return aligned_data, reference_time

def aggregate_to_5s_windows(df, timestamp_col='timestamp', value_col='acc_magnitude'):
    if timestamp_col not in df.columns:
        print(f"   Warning: {timestamp_col} not found in dataframe")
        return df
    
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        print(f"   Warning: {timestamp_col} is not datetime type")
        return df
    
    df_copy = df.copy()
    df_copy.set_index(timestamp_col, inplace=True)
    
    # Resample to 5-second windows
    result = df_copy[value_col].resample('5S').agg(['mean', 'std', 'count']).reset_index()
    result.columns = [timestamp_col, f'{value_col}_mean', f'{value_col}_std', 'sample_count']
    
    # Remove windows with no data
    result = result[result['sample_count'] > 0]
    
    return result

def create_aligned_comparison_plot(aligned_data, subject_id, session_type):
    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=(
            f'Raw Accelerometer Data - Subject {subject_id} ({session_type})',
            f'5-Second Aggregated Accelerometer Magnitude - All Devices Aligned'
        ),
        vertical_spacing=0.12,
        row_heights=[0.4, 0.6]
    )
    
    colors = {
        'actigraph': '#FF6B6B',  # Red
        'bangle': '#4ECDC4',      # Teal
        'emotibit': '#95E1D3'     # Mint
    }
    
    # Row 1: Raw data (downsampled for visualization)
    for device_name, df in aligned_data.items():
        if 'timestamp' in df.columns and pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            # Downsample for visualization (every 10th point for raw data)
            df_plot = df.iloc[::10].copy()
            
            fig.add_trace(
                go.Scatter(
                    x=df_plot['timestamp'],
                    y=df_plot['acc_magnitude'],
                    mode='lines',
                    name=f'{device_name.capitalize()} (raw)',
                    line=dict(color=colors[device_name], width=1),
                    opacity=0.6,
                    legendgroup=device_name
                ),
                row=1, col=1
            )
    
    # Row 2: 5-second aggregated data
    for device_name, df in aligned_data.items():
        if 'timestamp' in df.columns and pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            print(f"\nAggregating {device_name} to 5-second windows...")
            df_5s = aggregate_to_5s_windows(df)
            print(f"   Created {len(df_5s)} windows")
            
            fig.add_trace(
                go.Scatter(
                    x=df_5s['timestamp'],
                    y=df_5s['acc_magnitude_mean'],
                    mode='lines+markers',
                    name=f'{device_name.capitalize()} (5s avg)',
                    line=dict(color=colors[device_name], width=2),
                    marker=dict(size=4),
                    error_y=dict(
                        type='data',
                        array=df_5s['acc_magnitude_std'],
                        visible=True,
                        thickness=1,
                        width=0
                    ),
                    legendgroup=device_name
                ),
                row=2, col=1
            )
    
    # Update layout
    fig.update_layout(
        height=900,
        title_text=f"Accelerometer Comparison - Subject {subject_id} ({session_type}) - Aligned Timestamps",
        showlegend=True,
        hovermode='x unified',
        template='plotly_white'
    )
    
    # Update axes
    fig.update_yaxes(title_text="Magnitude (g)", row=1, col=1)
    fig.update_yaxes(title_text="Magnitude (g)", row=2, col=1)
    fig.update_xaxes(title_text="Time", row=1, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)
    
    return fig

def main():
    print("DIWAH Accelerometer Visualization - ALIGNED & 5-SECOND WINDOWS")
    print("="*70)
    
    # Configuration
    subject_id = '2002'
    session_type = 'activity'
    
    # Load and align data
    aligned_data, reference_time = load_and_align_data(subject_id, session_type)
    
    if not aligned_data:
        print("\nNo data loaded! Check if files exist for this subject/session.")
        return
    
    # Create visualization
    print(f"\nCreating aligned comparison visualization...")
    fig = create_aligned_comparison_plot(aligned_data, subject_id, session_type)
    
    # Save
    output_file = PLOTS_PATH / f"aligned_5s_comparison_{subject_id}_{session_type}.html"
    fig.write_html(str(output_file))
    print(f"\nSaved to: {output_file}")
    
    # Show in browser
    print("\nOpening in browser...")
    fig.show()
    
    print("\n" + "="*70)
    print("Visualization complete!")
    print(f"Bottom plot shows 5-second aggregated data with all devices aligned!")
    print("="*70)

if __name__ == "__main__":
    main()
