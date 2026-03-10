"""
DEPRECATED: This file is archived and should not be imported by production code.

The active functions have been moved to:
- get_available_subjects_sessions() -> src/data_loader.py
- load_and_align_data() -> src/data_loader.py
- aggregate_to_5s_windows() -> src/data_loader.py (renamed to aggregate_to_windows)

This file is kept for historical reference only.
"""

import warnings
warnings.warn(
    "archive.create_dashboard is deprecated. "
    "Use src.data_loader instead for get_available_subjects_sessions() and load_and_align_data().",
    DeprecationWarning,
    stacklevel=2
)

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from parsers import ActigraphParser, BangleParser, EmotibitParser
from src.config import ACTIGRAPH_PATH, BANGLE_PATH, EMOTIBIT_PATH, PLOTS_PATH

def get_available_subjects_sessions():
    subjects_sessions = {}
    
    # Scan Bangle files (most reliable for subject/session combinations)
    bangle_files = list(BANGLE_PATH.glob("*.csv"))
    
    for file in bangle_files:
        # Parse filename like "2002_activity.csv"
        name = file.stem
        if '_' in name:
            subject, session = name.split('_', 1)
            if subject not in subjects_sessions:
                subjects_sessions[subject] = []
            if session not in subjects_sessions[subject]:
                subjects_sessions[subject].append(session)
    
    return subjects_sessions

def get_session_start_time(subject_id, session_type, device):
    if device == 'emotibit':
        emotibit_dir = EMOTIBIT_PATH / f"{subject_id}_{session_type}"
        if emotibit_dir.exists():
            csv_files = list(emotibit_dir.glob("*.csv"))
            if csv_files:
                filename = csv_files[0].stem
                try:
                    date_str = filename.rsplit('-', 1)[0]
                    dt = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                    return dt
                except:
                    pass
    return None

def load_and_align_data(subject_id, session_type):
    aligned_data = {}
    reference_time = None
    
    # 1. Load Actigraph
    actigraph_pattern = f"{subject_id}*RAW.csv"
    actigraph_files = list(ACTIGRAPH_PATH.glob(actigraph_pattern))
    
    if actigraph_files:
        acti_file = None
        for f in actigraph_files:
            if f.stat().st_size < 50*1024*1024:
                acti_file = f
                break
        if not acti_file and actigraph_files:
            acti_file = actigraph_files[0]
        
        if acti_file:
            df_acti = ActigraphParser.parse_raw_file(acti_file)
            reference_time = df_acti['timestamp'].min()
            df_acti['device'] = 'Actigraph'
            aligned_data['actigraph'] = df_acti
    
    # 2. Load Bangle
    bangle_file = BANGLE_PATH / f"{subject_id}_{session_type}.csv"
    if bangle_file.exists():
        df_bangle = BangleParser.parse_file(bangle_file)
        
        # Bangle records delta times, so we need to align to reference time (Actigraph)
        if reference_time and 'cumulative_time_ms' in df_bangle.columns:
            df_bangle['timestamp'] = reference_time + pd.to_timedelta(df_bangle['cumulative_time_ms'], unit='ms')
        
        df_bangle['device'] = 'Bangle'
        aligned_data['bangle'] = df_bangle
    
    # 3. Load Emotibit
    emotibit_dir = EMOTIBIT_PATH / f"{subject_id}_{session_type}"
    if emotibit_dir.exists():
        csv_files = list(emotibit_dir.glob("*.csv"))
        if csv_files:
            df_emoti_raw = EmotibitParser.parse_csv_file(csv_files[0])
            df_emoti = EmotibitParser.extract_accelerometer(df_emoti_raw)
            
            emotibit_start = get_session_start_time(subject_id, session_type, 'emotibit')
            
            if emotibit_start:
                df_emoti['timestamp'] = emotibit_start + pd.to_timedelta(df_emoti['timestamp'] - df_emoti['timestamp'].min(), unit='ms')
            elif reference_time:
                df_emoti['timestamp'] = reference_time + pd.to_timedelta(df_emoti['timestamp'] - df_emoti['timestamp'].min(), unit='ms')
            
            df_emoti['device'] = 'Emotibit'
            aligned_data['emotibit'] = df_emoti
    
    return aligned_data, reference_time

def aggregate_to_5s_windows(df, timestamp_col='timestamp', value_col='acc_magnitude'):
    if timestamp_col not in df.columns:
        return df
    
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        return df
    
    df_copy = df.copy()
    df_copy.set_index(timestamp_col, inplace=True)
    
    result = df_copy[value_col].resample('5s').agg(['mean', 'std', 'count']).reset_index()
    result.columns = [timestamp_col, f'{value_col}_mean', f'{value_col}_std', 'sample_count']
    result = result[result['sample_count'] > 0]
    
    return result

def create_interactive_dashboard():
    
    # Get all available subjects and sessions
    subjects_sessions = get_available_subjects_sessions()
    
    print(f"Found data for:")
    for subject, sessions in sorted(subjects_sessions.items()):
        print(f"   Subject {subject}: {', '.join(sessions)}")
    
    # Create HTML with dropdown
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>DIWAH Accelerometer Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 {
            margin: 0 0 10px 0;
        }
        .controls {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .control-group {
            display: inline-block;
            margin-right: 20px;
        }
        label {
            font-weight: bold;
            margin-right: 10px;
        }
        select, button {
            padding: 10px 15px;
            font-size: 14px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }
        button {
            background: #667eea;
            color: white;
            cursor: pointer;
            font-weight: bold;
            border: none;
            transition: background 0.3s;
        }
        button:hover {
            background: #5568d3;
        }
        #loading {
            display: none;
            text-align: center;
            padding: 20px;
            background: white;
            border-radius: 10px;
            margin: 20px 0;
        }
        #plot {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stats {
            background: white;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stats h3 {
            margin-top: 0;
        }
        .stat-item {
            margin: 5px 0;
            padding: 5px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 DIWAH Wearable Sensors Dashboard</h1>
        <p>Interactive visualization of accelerometer data from Actigraph, Bangle, and Emotibit</p>
    </div>
    
    <div class="controls">
        <div class="control-group">
            <label for="subject">Subject:</label>
            <select id="subject" onchange="updateSessionOptions()">
"""
    
    # Add subject options
    for subject in sorted(subjects_sessions.keys()):
        html_content += f'                <option value="{subject}">{subject}</option>\n'
    
    html_content += """
            </select>
        </div>
        
        <div class="control-group">
            <label for="session">Session:</label>
            <select id="session">
"""
    
    # Add session options for first subject
    first_subject = sorted(subjects_sessions.keys())[0]
    for session in subjects_sessions[first_subject]:
        html_content += f'                <option value="{session}">{session.capitalize()}</option>\n'
    
    html_content += """
            </select>
        </div>
        
        <button onclick="loadData()">Load Data</button>
    </div>
    
    <div id="loading">
        <h3>Loading and processing data...</h3>
        <p>This may take a moment...</p>
    </div>
    
    <div id="plot"></div>
    
    <div id="stats" class="stats" style="display:none;">
        <h3>📈 Session Statistics</h3>
        <div id="stats-content"></div>
    </div>
    
    <script>
        // Subject-session mapping
        const subjectSessions = """ + str(subjects_sessions).replace("'", '"') + """;
        
        function updateSessionOptions() {
            const subject = document.getElementById('subject').value;
            const sessionSelect = document.getElementById('session');
            sessionSelect.innerHTML = '';
            
            if (subjectSessions[subject]) {
                subjectSessions[subject].forEach(session => {
                    const option = document.createElement('option');
                    option.value = session;
                    option.textContent = session.charAt(0).toUpperCase() + session.slice(1);
                    sessionSelect.appendChild(option);
                });
            }
        }
        
        function loadData() {
            const subject = document.getElementById('subject').value;
            const session = document.getElementById('session').value;
            
            document.getElementById('loading').style.display = 'block';
            document.getElementById('plot').innerHTML = '';
            document.getElementById('stats').style.display = 'none';
            
            // Call Python backend (we'll generate JSON data files)
            fetch(`data_${subject}_${session}.json`)
                .then(response => response.json())
                .then(data => {
                    plotData(data, subject, session);
                    document.getElementById('loading').style.display = 'none';
                })
                .catch(error => {
                    document.getElementById('loading').innerHTML = 
                        '<h3 style="color: red;">Error loading data</h3>' +
                        '<p>Data not generated yet. Run: python generate_dashboard_data.py</p>';
                });
        }
        
        function plotData(data, subject, session) {
            // Create plot with data
            const traces = [];
            const colors = {
                'actigraph': '#FF6B6B',
                'bangle': '#4ECDC4',
                'emotibit': '#95E1D3'
            };
            
            // Raw data traces
            Object.keys(data.raw).forEach(device => {
                if (data.raw[device]) {
                    traces.push({
                        x: data.raw[device].timestamp,
                        y: data.raw[device].magnitude,
                        name: device.charAt(0).toUpperCase() + device.slice(1) + ' (raw)',
                        mode: 'lines',
                        line: {color: colors[device], width: 1},
                        opacity: 0.6,
                        yaxis: 'y',
                        legendgroup: device
                    });
                }
            });
            
            // 5-second aggregated traces
            Object.keys(data.aggregated).forEach(device => {
                if (data.aggregated[device]) {
                    traces.push({
                        x: data.aggregated[device].timestamp,
                        y: data.aggregated[device].magnitude_mean,
                        name: device.charAt(0).toUpperCase() + device.slice(1) + ' (5s avg)',
                        mode: 'lines+markers',
                        line: {color: colors[device], width: 2},
                        marker: {size: 4},
                        yaxis: 'y2',
                        legendgroup: device
                    });
                }
            });
            
            const layout = {
                title: `Accelerometer Comparison - Subject ${subject} (${session})`,
                height: 900,
                grid: {rows: 2, columns: 1, pattern: 'independent'},
                yaxis: {title: 'Magnitude (g)', domain: [0.55, 1]},
                yaxis2: {title: 'Magnitude (g)', domain: [0, 0.45]},
                xaxis: {title: 'Time'},
                xaxis2: {title: 'Time'},
                hovermode: 'x unified',
                template: 'plotly_white'
            };
            
            Plotly.newPlot('plot', traces, layout, {responsive: true});
            
            // Show stats
            showStats(data.stats, subject, session);
        }
        
        function showStats(stats, subject, session) {
            const statsDiv = document.getElementById('stats');
            const statsContent = document.getElementById('stats-content');
            
            let html = `<strong>Subject ${subject} - ${session.toUpperCase()} Session</strong><br><br>`;
            
            Object.keys(stats).forEach(device => {
                if (stats[device]) {
                    html += `<div class="stat-item">
                        <strong>${device.toUpperCase()}:</strong><br>
                        • Samples: ${stats[device].samples.toLocaleString()}<br>
                        • Duration: ${stats[device].duration}<br>
                        • Start: ${stats[device].start_time}<br>
                        • End: ${stats[device].end_time}<br>
                        • 5s windows: ${stats[device].windows}
                    </div>`;
                }
            });
            
            statsContent.innerHTML = html;
            statsDiv.style.display = 'block';
        }
        
        // Load first dataset on page load
        window.onload = function() {
            // Don't auto-load, wait for user to click
        };
    </script>
</body>
</html>
"""
    
    # Save HTML
    output_file = PLOTS_PATH / "dashboard.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\nDashboard created: {output_file}")
    return output_file, subjects_sessions

def generate_data_json(subject_id, session_type):
    """Generate JSON data file for a subject/session"""
    print(f"\nGenerating data for {subject_id}_{session_type}...")
    
    aligned_data, _ = load_and_align_data(subject_id, session_type)
    
    if not aligned_data:
        return None
    
    data_json = {
        'raw': {},
        'aggregated': {},
        'stats': {}
    }
    
    for device_name, df in aligned_data.items():
        if 'timestamp' in df.columns and pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            # Downsample raw data
            df_plot = df.iloc[::10].copy()
            data_json['raw'][device_name] = {
                'timestamp': df_plot['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').tolist(),
                'magnitude': df_plot['acc_magnitude'].tolist()
            }
            
            # 5-second aggregated
            df_5s = aggregate_to_5s_windows(df)
            data_json['aggregated'][device_name] = {
                'timestamp': df_5s['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').tolist(),
                'magnitude_mean': df_5s['acc_magnitude_mean'].tolist(),
                'magnitude_std': df_5s['acc_magnitude_std'].tolist()
            }
            
            # Stats
            duration = (df['timestamp'].max() - df['timestamp'].min()).total_seconds()
            data_json['stats'][device_name] = {
                'samples': len(df),
                'duration': f"{int(duration//60)}m {int(duration%60)}s",
                'start_time': df['timestamp'].min().strftime('%H:%M:%S'),
                'end_time': df['timestamp'].max().strftime('%H:%M:%S'),
                'windows': len(df_5s)
            }
    
    # Save JSON
    import json
    output_file = PLOTS_PATH / f"data_{subject_id}_{session_type}.json"
    with open(output_file, 'w') as f:
        json.dump(data_json, f)
    
    print(f"   Saved {output_file.name}")
    return output_file

def main():
    """Main function"""
    print("Creating Interactive Dashboard")
    print("="*70)
    
    # Create dashboard HTML
    dashboard_file, subjects_sessions = create_interactive_dashboard()
    
    # Generate JSON data for all subjects/sessions
    print("\nGenerating data files...")
    for subject, sessions in sorted(subjects_sessions.items()):
        for session in sessions:
            try:
                generate_data_json(subject, session)
            except Exception as e:
                print(f"   Error processing {subject}_{session}: {e}")
    
    print("\n" + "="*70)
    print(f"Dashboard ready!")
    print(f"Open in browser: {dashboard_file}")
    print("="*70)
    
    # Open in browser
    import webbrowser
    webbrowser.open(f'file://{dashboard_file.absolute()}')

if __name__ == "__main__":
    main()
