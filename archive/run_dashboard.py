import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from influxdb_client import InfluxDBClient

try:
    import dash
    from dash import dcc, html, Input, Output
except ImportError:
    print("Installing dash...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'dash'])
    import dash
    from dash import dcc, html, Input, Output

from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

# Initialize InfluxDB client
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60_000)
query_api = influx_client.query_api()

def get_available_subjects_sessions():
    """Query InfluxDB for distinct subject/session combinations efficiently using schema.tagValues"""
    subjects_sessions = {}

# json_files = list(PLOTS_PATH.glob("data_*.json"))
    
#     for file in json_files:
#         # Parse filename like "data_2002_activity.json"
#         name = file.stem.replace('data_', '')
#         if '_' in name:
#             parts = name.split('_')
#             subject = parts[0]
#             session = '_'.join(parts[1:])
            
#             if subject not in subjects_sessions:
#                 subjects_sessions[subject] = []
#             if session not in subjects_sessions[subject]:
#                 subjects_sessions[subject].append(session)
    
    # return subjects_sessions
    subjects_query = f'''
    import "influxdata/influxdb/schema"
    schema.tagValues(
        bucket: "{INFLUX_BUCKET}",
        tag: "subject",
        predicate: (r) => r._measurement == "accelerometer",
        start: 2024-01-01T00:00:00Z,
        stop: 2025-12-31T23:59:59Z
    )
    '''

    try:
        # Get all distinct subjects
        subjects = []
        for table in query_api.query(subjects_query):
            for record in table.records:
                val = record.get_value()
                if val:
                    subjects.append(val)

        # For each subject, get sessions
        for subject in subjects:
            session_query = f'''
            import "influxdata/influxdb/schema"
            schema.tagValues(
                bucket: "{INFLUX_BUCKET}",
                tag: "session",
                predicate: (r) => r._measurement == "accelerometer" and r.subject == "{subject}",
                start: 2024-01-01T00:00:00Z,
                stop: 2025-12-31T23:59:59Z
            )
            '''

            sessions = []
            for table in query_api.query(session_query):
                for record in table.records:
                    val = record.get_value()
                    if val:
                        sessions.append(val)

            if sessions:
                subjects_sessions[subject] = sorted(set(sessions))

        return subjects_sessions
# def load_data_from_json(subject, session):
#     json_file = PLOTS_PATH / f"data_{subject}_{session}.json"
    
#     if not json_file.exists():
#         return None
    
#     with open(json_file, 'r') as f:
#         data = json.load(f)
    
#     return data
    except Exception as e:
        print(f"Error querying InfluxDB: {e}")
        return {}

def load_data_from_influx(subject, session):
    """Load raw and aggregated data from InfluxDB"""
    
    # Query raw data (limited sample for visualization)
    raw_query = f'''
    from(bucket: "{INFLUX_BUCKET}")
        |> range(start: 2024-01-01T00:00:00Z, stop: 2025-12-31T23:59:59Z)
        |> filter(fn: (r) => r["_measurement"] == "accelerometer")
        |> filter(fn: (r) => r["subject"] == "{subject}")
        |> filter(fn: (r) => r["session"] == "{session}")
        |> filter(fn: (r) => r["_field"] == "magnitude")
        |> pivot(rowKey:["_time"], columnKey: ["device"], valueColumn: "_value")
    '''
    
    # Query aggregated data (5-second windows)
    agg_query = f'''
    from(bucket: "{INFLUX_BUCKET}")
        |> range(start: 2024-01-01T00:00:00Z, stop: 2025-12-31T23:59:59Z)
        |> filter(fn: (r) => r["_measurement"] == "accelerometer")
        |> filter(fn: (r) => r["subject"] == "{subject}")
        |> filter(fn: (r) => r["session"] == "{session}")
        |> filter(fn: (r) => r["_field"] == "magnitude")
        |> aggregateWindow(every: 5s, fn: mean, createEmpty: false)
        |> pivot(rowKey:["_time"], columnKey: ["device"], valueColumn: "_value")
    '''
    
    try:
        # Execute queries
        raw_result = query_api.query_data_frame(raw_query)
        agg_result = query_api.query_data_frame(agg_query)
        
        data = {
            'raw': {},
            'aggregated': {},
            'stats': {}
        }
        
        # Process raw data
        if not raw_result.empty:
            for device in ['actigraph', 'bangle', 'emotibit']:
                if device in raw_result.columns:
                    device_data = raw_result[['_time', device]].dropna()
                    if not device_data.empty:
                        data['raw'][device] = {
                            'timestamp': device_data['_time'].tolist(),
                            'magnitude': device_data[device].tolist()
                        }
                        
                        # Calculate stats
                        data['stats'][device] = {
                            'samples': len(device_data),
                            'duration': str(device_data['_time'].max() - device_data['_time'].min()),
                            'start_time': str(device_data['_time'].min()),
                            'end_time': str(device_data['_time'].max()),
                            'windows': 'N/A'
                        }
        
        # Process aggregated data
        if not agg_result.empty:
            for device in ['actigraph', 'bangle', 'emotibit']:
                if device in agg_result.columns:
                    device_data = agg_result[['_time', device]].dropna()
                    if not device_data.empty:
                        data['aggregated'][device] = {
                            'timestamp': device_data['_time'].tolist(),
                            'magnitude_mean': device_data[device].tolist()
                        }
                        
                        # Update windows count in stats
                        if device in data['stats']:
                            data['stats'][device]['windows'] = len(device_data)
        
        return data if (data['raw'] or data['aggregated']) else None
    
    except Exception as e:
        print(f"Error loading data from InfluxDB: {e}")
        return None

def create_plot(data, subject, session):
    if not data:
        return go.Figure().add_annotation(
            text="No data available",
            showarrow=False,
            font=dict(size=20)
        )
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=(
            f'Raw Accelerometer Data',
            f'5-Second Aggregated Accelerometer Magnitude'
        ),
        vertical_spacing=0.12,
        row_heights=[0.4, 0.6]
    )
    
    colors = {
        'actigraph': '#FF6B6B',
        'bangle': '#4ECDC4',
        'emotibit': '#95E1D3'
    }
    
    # Add raw data traces
    for device in ['actigraph', 'bangle', 'emotibit']:
        if device in data['raw'] and data['raw'][device]:
            timestamps = pd.to_datetime(data['raw'][device]['timestamp'])
            magnitudes = data['raw'][device]['magnitude']
            
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=magnitudes,
                    mode='lines',
                    name=f'{device.capitalize()} (raw)',
                    line=dict(color=colors[device], width=1),
                    opacity=0.6,
                    legendgroup=device
                ),
                row=1, col=1
            )
    
    # Add aggregated data traces
    for device in ['actigraph', 'bangle', 'emotibit']:
        if device in data['aggregated'] and data['aggregated'][device]:
            timestamps = pd.to_datetime(data['aggregated'][device]['timestamp'])
            magnitudes = data['aggregated'][device]['magnitude_mean']
            
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=magnitudes,
                    mode='lines+markers',
                    name=f'{device.capitalize()} (5s avg)',
                    line=dict(color=colors[device], width=2),
                    marker=dict(size=4),
                    legendgroup=device
                ),
                row=2, col=1
            )
    
    # Update layout
    fig.update_layout(
        height=900,
        title_text=f"Accelerometer Comparison - Subject {subject} ({session})",
        showlegend=True,
        hovermode='x unified',
        template='plotly_white'
    )
    
    fig.update_yaxes(title_text="Magnitude (g)", row=1, col=1)
    fig.update_yaxes(title_text="Magnitude (g)", row=2, col=1)
    fig.update_xaxes(title_text="Time", row=1, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)
    
    return fig

# Initialize the Dash app
app = dash.Dash(__name__)

# Get available data
subjects_sessions = get_available_subjects_sessions()
print(f"Found data for {len(subjects_sessions)} subjects")

# Sort subjects
all_subjects = sorted(subjects_sessions.keys())

# App layout
app.layout = html.Div([
    html.Div([
        html.H1("DIWAH Wearable Sensors Dashboard", 
                style={'color': 'white', 'margin': '0'}),
        html.P("Interactive visualization of accelerometer data from Actigraph, Bangle, and Emotibit",
               style={'color': 'white', 'margin': '10px 0 0 0'})
    ], style={
        'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'padding': '30px',
        'borderRadius': '10px',
        'marginBottom': '20px'
    }),
    
    html.Div([
        html.Div([
            html.Label('Subject:', style={'fontWeight': 'bold', 'marginRight': '10px'}),
            dcc.Dropdown(
                id='subject-dropdown',
                options=[{'label': s, 'value': s} for s in all_subjects],
                value=all_subjects[0] if all_subjects else None,
                style={'width': '200px', 'display': 'inline-block'}
            )
        ], style={'display': 'inline-block', 'marginRight': '30px'}),
        
        html.Div([
            html.Label('Session:', style={'fontWeight': 'bold', 'marginRight': '10px'}),
            dcc.Dropdown(
                id='session-dropdown',
                style={'width': '200px', 'display': 'inline-block'}
            )
        ], style={'display': 'inline-block'})
    ], style={
        'background': 'white',
        'padding': '20px',
        'borderRadius': '10px',
        'marginBottom': '20px'
    }),
    
    dcc.Loading(
        id="loading",
        type="default",
        children=[
            dcc.Graph(id='main-plot', style={'background': 'white', 'borderRadius': '10px'}),
            
            html.Div(id='stats-panel', style={
                'background': 'white',
                'padding': '20px',
                'borderRadius': '10px',
                'marginTop': '20px'
            })
        ]
    )
], style={
    'fontFamily': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
    'margin': '20px',
    'background': '#f5f5f5'
})

# Callback to update session dropdown based on selected subject
@app.callback(
    Output('session-dropdown', 'options'),
    Output('session-dropdown', 'value'),
    Input('subject-dropdown', 'value')
)
def update_session_dropdown(selected_subject):
    if not selected_subject or selected_subject not in subjects_sessions:
        return [], None
    
    sessions = subjects_sessions[selected_subject]
    options = [{'label': s.capitalize(), 'value': s} for s in sessions]
    value = sessions[0] if sessions else None
    
    return options, value

# Callback to update plot
@app.callback(
    Output('main-plot', 'figure'),
    Output('stats-panel', 'children'),
    Input('subject-dropdown', 'value'),
    Input('session-dropdown', 'value')
)
def update_plot(subject, session):
    if not subject or not session:
        empty_fig = go.Figure()
        empty_fig.add_annotation(
            text="Select a subject and session",
            showarrow=False,
            font=dict(size=20)
        )
        return empty_fig, ""
    
    # Load data from jsons
    # data = load_data_from_json(subject, session)
    data = load_data_from_influx(subject, session)
    
    if not data:
        empty_fig = go.Figure()
        empty_fig.add_annotation(
            text=f"No data available for Subject {subject} - {session}",
            showarrow=False,
            font=dict(size=20)
        )
        return empty_fig, ""
    
    # Create plot
    fig = create_plot(data, subject, session)
    
    # Create stats panel
    stats_html = [
        html.H3(f"Session Statistics - Subject {subject} ({session.upper()})"),
        html.Hr()
    ]
    
    for device in ['actigraph', 'bangle', 'emotibit']:
        if device in data['stats'] and data['stats'][device]:
            stats = data['stats'][device]
            stats_html.append(
                html.Div([
                    html.H4(f"{device.upper()}", style={'color': '#667eea'}),
                    html.P(f"• Samples: {stats['samples']:,}"),
                    html.P(f"• Duration: {stats['duration']}"),
                    html.P(f"• Start: {stats['start_time']}"),
                    html.P(f"• End: {stats['end_time']}"),
                    html.P(f"• 5s windows: {stats['windows']}")
                ], style={'marginBottom': '20px'})
            )
    
    return fig, stats_html

if __name__ == '__main__':
    print("\n" + "="*70)
    print("Starting DIWAH Dashboard Server")
    print("="*70)
    print(f"Loaded data for {len(subjects_sessions)} subjects")
    print("\nOpen the browser and go to:")
    print("   http://localhost:8050")
    print("="*70 + "\n")
    
    app.run(debug=True, host="127.0.0.1", port=8050, use_reloader=False)
