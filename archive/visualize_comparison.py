import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from parsers import ActigraphParser, BangleParser, EmotibitParser, calculate_magnitude_5s_windows
from src.config import ACTIGRAPH_PATH, BANGLE_PATH, EMOTIBIT_PATH, PLOTS_PATH

def load_subject_session(subject_id, session_type):
    data = {}
    
    # 1. Load Actigraph
    print(f"Loading Actigraph data for {subject_id}_{session_type}...")
    actigraph_pattern = f"{subject_id}*RAW.csv"
    actigraph_files = list(ACTIGRAPH_PATH.glob(actigraph_pattern))
    
    if actigraph_files:
        # Use smaller file for testing
        small_files = [f for f in actigraph_files if f.stat().st_size < 10*1024*1024]
        if small_files:
            data['actigraph'] = ActigraphParser.parse_raw_file(small_files[0])
            print(f"  Loaded {len(data['actigraph'])} samples")
        elif actigraph_files:
            data['actigraph'] = ActigraphParser.parse_raw_file(actigraph_files[0])
            print(f"  Loaded {len(data['actigraph'])} samples")
    
    # 2. Load Bangle
    print(f"Loading Bangle data for {subject_id}_{session_type}...")
    bangle_file = BANGLE_PATH / f"{subject_id}_{session_type}.csv"
    if bangle_file.exists():
        data['bangle'] = BangleParser.parse_file(bangle_file)
        print(f"  Loaded {len(data['bangle'])} samples")
    
    # 3. Load Emotibit
    print(f"Loading Emotibit data for {subject_id}_{session_type}...")
    emotibit_dir = EMOTIBIT_PATH / f"{subject_id}_{session_type}"
    if emotibit_dir.exists():
        csv_files = list(emotibit_dir.glob("*.csv"))
        if csv_files:
            df_emoti_raw = EmotibitParser.parse_csv_file(csv_files[0])
            data['emotibit'] = EmotibitParser.extract_accelerometer(df_emoti_raw)
            print(f"  Loaded {len(data['emotibit'])} samples")
    
    return data

def plot_comparison(data, subject_id, session_type):
    fig = make_subplots(
        rows=4, cols=1,
        subplot_titles=(
            'Actigraph (30 Hz)',
            'Bangle (~12.5 Hz)',
            'Emotibit (25 Hz)',
            'All Devices - 5-Second Windows'
        ),
        vertical_spacing=0.08,
        shared_xaxes=False
    )
    
    # Colors
    colors = {
        'actigraph': '#FF6B6B',  # Red
        'bangle': '#4ECDC4',      # Teal
        'emotibit': '#95E1D3'     # Mint
    }
    
    row = 1
    
    # Plot each device
    if 'actigraph' in data:
        df = data['actigraph']
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['acc_magnitude'],
                mode='lines',
                name='Actigraph',
                line=dict(color=colors['actigraph'], width=1)
            ),
            row=row, col=1
        )
        row += 1
    
    if 'bangle' in data:
        df = data['bangle']
        # Use relative time for now (seconds)
        time_seconds = df['cumulative_time_ms'] / 1000
        fig.add_trace(
            go.Scatter(
                x=time_seconds,
                y=df['acc_magnitude'],
                mode='lines',
                name='Bangle',
                line=dict(color=colors['bangle'], width=1)
            ),
            row=row, col=1
        )
        row += 1
    
    if 'emotibit' in data:
        df = data['emotibit']
        # Convert timestamp to relative seconds
        df['time_seconds'] = (df['timestamp'] - df['timestamp'].min()) / 1000
        fig.add_trace(
            go.Scatter(
                x=df['time_seconds'],
                y=df['acc_magnitude'],
                mode='lines',
                name='Emotibit',
                line=dict(color=colors['emotibit'], width=1)
            ),
            row=row, col=1
        )
        row += 1
    
    # 5-second windows comparison
    if 'actigraph' in data:
        df_5s = calculate_magnitude_5s_windows(data['actigraph'])
        fig.add_trace(
            go.Scatter(
                x=df_5s['timestamp'],
                y=df_5s['acc_magnitude_5s'],
                mode='lines+markers',
                name='Actigraph (5s)',
                line=dict(color=colors['actigraph'], width=2),
                marker=dict(size=4)
            ),
            row=4, col=1
        )
    
    if 'bangle' in data:
        # Need to add proper timestamp first for resampling
        # For now, skip or use approximation
        pass
    
    if 'emotibit' in data:
        # Similar issue with timestamp
        pass
    
    # Update layout
    fig.update_layout(
        height=1200,
        title_text=f"Accelerometer Comparison - Subject {subject_id} ({session_type})",
        showlegend=True,
        hovermode='x unified'
    )
    
    # Update y-axes
    fig.update_yaxes(title_text="Magnitude (g)", row=1, col=1)
    fig.update_yaxes(title_text="Magnitude (g)", row=2, col=1)
    fig.update_yaxes(title_text="Magnitude (g)", row=3, col=1)
    fig.update_yaxes(title_text="Magnitude (g)", row=4, col=1)
    
    # Update x-axes
    fig.update_xaxes(title_text="Time", row=1, col=1)
    fig.update_xaxes(title_text="Time (seconds)", row=2, col=1)
    fig.update_xaxes(title_text="Time (seconds)", row=3, col=1)
    fig.update_xaxes(title_text="Time", row=4, col=1)
    
    return fig

def main():
    print("DIWAH Accelerometer Visualization")
    print("="*60)
    
    # Test with subject 2002, activity session
    subject_id = '2002'
    session_type = 'activity'
    
    print(f"\nLoading data for Subject {subject_id}, Session: {session_type}")
    print("-"*60)
    
    data = load_subject_session(subject_id, session_type)
    
    print(f"\nCreating visualization...")
    fig = plot_comparison(data, subject_id, session_type)
    
    # Save to HTML
    output_file = PLOTS_PATH / f"accelerometer_comparison_{subject_id}_{session_type}.html"
    fig.write_html(str(output_file))
    print(f"Saved to: {output_file}")
    
    # Show in browser
    print("\nOpening in browser...")
    fig.show()
    
    print("\n" + "="*60)
    print("Visualization complete!")
    print("="*60)

if __name__ == "__main__":
    main()
