"""LNU styled dashboard (separate from original).
Run with: python run_dashboard_lnu.py or set container CMD.
"""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    import dash
    from dash import dcc, html, Input, Output, State
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'dash'])
    import dash
    from dash import dcc, html, Input, Output, State

from influxdb_client import InfluxDBClient
from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

# LNU colors
COLORS = {
    'buttercup': '#FFE000',
    'lily': '#FDECB2',
    'soot': '#232326',
    'crocus': '#5D4FB1',
    'ivy': '#007340',
    'azalea': '#A62186'
}
DEVICE_COLORS = {
    'actigraph': COLORS['crocus'],
    'bangle': COLORS['ivy'],
    'emotibit': COLORS['azalea']
}

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60_000)
query_api = client.query_api()

def tag_values(tag, subject=None):
    predicate = 'r._measurement == "accelerometer"'
    if subject:
        predicate += f' and r.subject == "{subject}"'
    flux = f'''import "influxdata/influxdb/schema"
    schema.tagValues(bucket: "{INFLUX_BUCKET}", tag: "{tag}", predicate: (r) => {predicate}, start: 2024-01-01T00:00:00Z, stop: 2025-12-31T23:59:59Z)'''
    vals = []
    for table in query_api.query(flux):
        for rec in table.records:
            v = rec.get_value()
            if v:
                vals.append(v)
    return sorted(set(vals))

def load_data(subject, session):
    raw_flux = f'''from(bucket: "{INFLUX_BUCKET}")
    |> range(start: 2024-01-01T00:00:00Z, stop: 2025-12-31T23:59:59Z)
    |> filter(fn: (r) => r._measurement == "accelerometer" and r.subject == "{subject}" and r.session == "{session}" and r._field == "magnitude")
    |> pivot(rowKey:["_time"], columnKey:["device"], valueColumn:"_value")'''
    agg_flux = f'''from(bucket: "{INFLUX_BUCKET}")
    |> range(start: 2024-01-01T00:00:00Z, stop: 2025-12-31T23:59:59Z)
    |> filter(fn: (r) => r._measurement == "accelerometer" and r.subject == "{subject}" and r.session == "{session}" and r._field == "magnitude")
    |> aggregateWindow(every:5s, fn:mean, createEmpty:false)
    |> pivot(rowKey:["_time"], columnKey:["device"], valueColumn:"_value")'''

    data = {'raw': {}, 'agg': {}, 'stats': {}}
    raw_df = query_api.query_data_frame(raw_flux)
    if isinstance(raw_df, list) and raw_df:
        raw_df = pd.concat(raw_df, ignore_index=False)
    if isinstance(raw_df, pd.DataFrame) and not raw_df.empty:
        for dev in DEVICE_COLORS:
            if dev in raw_df.columns:
                d = raw_df[['_time', dev]].dropna()
                if not d.empty:
                    data['raw'][dev] = d
                    data['stats'].setdefault(dev, {})
                    data['stats'][dev].update({'samples': len(d), 'start': str(d['_time'].min()), 'end': str(d['_time'].max())})
    agg_df = query_api.query_data_frame(agg_flux)
    if isinstance(agg_df, list) and agg_df:
        agg_df = pd.concat(agg_df, ignore_index=False)
    if isinstance(agg_df, pd.DataFrame) and not agg_df.empty:
        for dev in DEVICE_COLORS:
            if dev in agg_df.columns:
                d = agg_df[['_time', dev]].dropna()
                if not d.empty:
                    data['agg'][dev] = d
                    data['stats'].setdefault(dev, {})
                    data['stats'][dev]['windows'] = len(d)
    for dev, s in data['stats'].items():
        try:
            s['duration'] = str(pd.to_datetime(s['end']) - pd.to_datetime(s['start']))
        except Exception:
            pass
    return data if data['raw'] or data['agg'] else None

def make_fig(data, subject, session):
    fig = make_subplots(rows=2, cols=1, subplot_titles=("Raw Accelerometer Data", "5s Aggregated Magnitude"), vertical_spacing=0.12, row_heights=[0.45,0.55])
    for dev, df in data['raw'].items():
        fig.add_trace(go.Scatter(x=pd.to_datetime(df['_time']), y=df[dev], name=f"{dev.title()} raw", mode='lines', line=dict(color=DEVICE_COLORS[dev], width=1), opacity=0.6, legendgroup=dev), row=1,col=1)
    for dev, df in data['agg'].items():
        fig.add_trace(go.Scatter(x=pd.to_datetime(df['_time']), y=df[dev], name=f"{dev.title()} 5s avg", mode='lines+markers', line=dict(color=DEVICE_COLORS[dev], width=2), marker=dict(size=4,color=DEVICE_COLORS[dev]), legendgroup=dev), row=2,col=1)
    fig.update_layout(height=900, title=f"Subject {subject} ({session})", paper_bgcolor=COLORS['lily'], plot_bgcolor='white', hovermode='x unified', showlegend=True)
    fig.update_yaxes(title_text='Magnitude (g)', row=1,col=1)
    fig.update_yaxes(title_text='Magnitude (g)', row=2,col=1)
    return fig

app = dash.Dash(__name__)
subjects = tag_values('subject')

app.layout = html.Div([
    html.Div([
        html.H1('DIWAH Wearable Sensors Dashboard', style={'margin':'0','color':COLORS['soot']}),
        html.P('Linnaeus University • Vector magnitude (5s)', style={'margin':'6px 0 0 0','color':COLORS['soot']})
    ], style={'background':COLORS['buttercup'],'padding':'26px 20px','borderBottom':f'4px solid {COLORS['soot']}'}),
    html.Div([
        html.Div([
            html.Label('Subject', style={'fontWeight':600}),
            dcc.Dropdown(id='sub-dd', options=[{'label':s,'value':s} for s in subjects], value=subjects[0] if subjects else None, style={'minWidth':'200px'})
        ], style={'marginRight':'14px'}),
        html.Div([
            html.Label('Session', style={'fontWeight':600}),
            dcc.Dropdown(id='sess-dd', style={'minWidth':'200px'})
        ]),
        html.Div([
            html.Button('Revisit consent', id='btn-consent', n_clicks=0, style={'background':COLORS['soot'],'color':COLORS['buttercup'],'border':'none','padding':'10px 14px','borderRadius':'8px','fontWeight':600,'cursor':'pointer'})
        ], style={'marginLeft':'auto'})
    ], style={'display':'flex','flexWrap':'wrap','gap':'12px','alignItems':'end','background':COLORS['lily'],'padding':'14px 20px','borderBottom':f'1px solid {COLORS['lily']}'}),
    dcc.ConfirmDialog(id='consent-dialog', message='Data usage follows approved consent. Contact project lead for details.'),
    html.Div([
        html.Div([dcc.Graph(id='lnu-graph')], style={'background':'white','border':f'1px solid {COLORS['lily']}','borderRadius':'10px','padding':'18px','boxShadow':'0 2px 8px rgba(0,0,0,0.04)'}),
        html.Div(id='stats', style={'background':'white','border':f'1px solid {COLORS['lily']}','borderRadius':'10px','padding':'18px','marginTop':'18px','boxShadow':'0 2px 8px rgba(0,0,0,0.04)'})
    ], style={'maxWidth':'1180px','margin':'20px auto'}),
], style={'fontFamily':'system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif','background':'#fafafa'})

@app.callback(Output('sess-dd','options'),Output('sess-dd','value'),Input('sub-dd','value'))
def _sessions(sub):
    if not sub:
        return [], None
    sessions = tag_values('session', subject=sub)
    return [{'label':s.title(),'value':s} for s in sessions], (sessions[0] if sessions else None)

@app.callback(Output('lnu-graph','figure'),Output('stats','children'),Input('sub-dd','value'),Input('sess-dd','value'))
def _plot(sub, sess):
    if not sub or not sess:
        return go.Figure().add_annotation(text='Select subject & session', showarrow=False), ''
    data = load_data(sub, sess)
    if not data:
        return go.Figure().add_annotation(text='No data', showarrow=False), ''
    fig = make_fig(data, sub, sess)
    cards = []
    for dev,s in data['stats'].items():
        cards.append(html.Div([
            html.H4(dev.title(), style={'margin':'0 0 6px 0','color':DEVICE_COLORS[dev]}),
            html.Div(f"Samples: {s.get('samples','-')}") ,
            html.Div(f"Duration: {s.get('duration','-')}") ,
            html.Div(f"Start: {s.get('start','-')}") ,
            html.Div(f"End: {s.get('end','-')}") ,
            html.Div(f"5s windows: {s.get('windows','-')}")
        ], style={'flex':'1 1 220px','background':'white','border':f'1px solid {COLORS['lily']}','borderLeft':f'6px solid {DEVICE_COLORS[dev]}','padding':'12px 14px','borderRadius':'8px'}))
    return fig, html.Div(cards, style={'display':'flex','flexWrap':'wrap','gap':'12px'})

@app.callback(Output('consent-dialog','displayed'),Input('btn-consent','n_clicks'),State('consent-dialog','displayed'))
def _consent(n, disp):
    return bool(n)

if __name__ == '__main__':
    print('Starting LNU themed dashboard at http://localhost:8050')
    app.run(debug=True, host='0.0.0.0', port=8050, use_reloader=False)
