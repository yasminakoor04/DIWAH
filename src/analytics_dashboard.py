"""
DIWAH Analytics Dashboard - Main Application.

Comprehensive validation dashboard for wearable sensor research at Linnaeus University.
This is the main entry point that ties together all dashboard components.
"""

import logging
import os
from typing import Dict, Any, Optional, List, Tuple

import pandas as pd
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

from .config import INFLUX_BUCKET, EXCLUDED_SUBJECTS
from .backend.database import get_query_api, tag_values, health_check
from .constants import COLORS, DEVICE_COLORS, PARTICIPANT_MAPPING
from .frontend.visualizations import make_time_plot, make_correlation_heatmap
from .frontend.layouts import (
    create_kpi_card, make_comparison_table, create_header,
    create_controls, create_main_tabs, create_stats_table,
    create_device_stats_cards, create_cohort_table, create_mobile_sidebar
)
from .backend.cohort import get_cohort_data, get_cohort_summary
from .backend.stats_utils import (
    calculate_summary_stats, calculate_correlations,
    compare_activity_rest, calculate_data_quality
)

logger = logging.getLogger(__name__)


def load_data(subject: str, session: str) -> Optional[Dict[str, Any]]:
    """
    Load raw and aggregated accelerometer data from InfluxDB.
    
    Args:
        subject: Subject identifier
        session: Session type
    
    Returns:
        Dict with keys 'raw', 'agg', 'stats', 'error'
    """
    data = {'raw': {}, 'agg': {}, 'stats': {}, 'error': None}
    
    if not subject or not session:
        logger.warning(f"Invalid parameters: subject={subject}, session={session}")
        data['error'] = "Invalid subject or session parameter"
        return data
    
    # Sanitize inputs
    safe_subject = str(subject).replace('"', '\\"')
    safe_session = str(session).replace('"', '\\"')
    
    try:
        query_api = get_query_api()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        data['error'] = "Database connection failed."
        return data
    
    raw_flux = f'''from(bucket: "{INFLUX_BUCKET}")
    |> range(start: -100y)
    |> filter(fn: (r) => r._measurement == "accelerometer" and r.subject == "{safe_subject}" and r.session == "{safe_session}" and r._field == "magnitude")
    |> pivot(rowKey:["_time"], columnKey:["device"], valueColumn:"_value")'''
    
    agg_flux = f'''from(bucket: "{INFLUX_BUCKET}")
    |> range(start: -100y)
    |> filter(fn: (r) => r._measurement == "accelerometer" and r.subject == "{safe_subject}" and r.session == "{safe_session}" and r._field == "magnitude")
    |> aggregateWindow(every:5s, fn:mean, createEmpty:false)
    |> pivot(rowKey:["_time"], columnKey:["device"], valueColumn:"_value")'''

    if health_check():
        try:
            # We no longer load raw data as the dashboard visualizations only use 5s aggregated data
            agg_df = query_api.query_data_frame(agg_flux)
            if isinstance(agg_df, list) and agg_df:
                agg_df = pd.concat(agg_df, ignore_index=False)
                
            if isinstance(agg_df, pd.DataFrame) and not agg_df.empty:
                for dev in DEVICE_COLORS:
                    cols = [c for c in agg_df.columns if dev.lower() in c.lower()]
                    if cols:
                        # Extract _time and the first matched device column
                        d = agg_df[['_time', cols[0]]].copy()
                        d.columns = ['_time', dev]
                        d = d.dropna()
                        if not d.empty:
                            data['agg'][dev] = d
                            # Update stats
                            data['stats'][dev] = {
                                'samples': len(d),
                                'start': str(d['_time'].min()),
                                'end': str(d['_time'].max()),
                                'windows': len(d)
                            }
        except Exception as e:
            logger.error(f"Error loading aggregated data from InfluxDB: {e}")
            data['error'] = f"Failed to load data from database: {e}"
    else:
        data['error'] = "Database is unreachable."
    
    # Calculate duration
    for dev in data['stats']:
        try:
            start = pd.to_datetime(data['stats'][dev]['start'])
            end = pd.to_datetime(data['stats'][dev]['end'])
            data['stats'][dev]['duration'] = str(end - start)
        except (ValueError, KeyError):
            pass
    
    if not data['raw'] and not data['agg'] and not data['error']:
        return None
    
    return data


# Initialize Dash app
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
    assets_folder=os.path.join(os.path.dirname(__file__), 'assets')
)
app.title = "DIWAH Analytics Dashboard"
app.config.suppress_callback_exceptions = True

# Set Flask secret key for session management
app.server.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())

# Add Basic Authentication if credentials are configured
_auth_username = os.getenv('DASHBOARD_USERNAME')
_auth_password = os.getenv('DASHBOARD_PASSWORD')
if _auth_username and _auth_password:
    from dash_auth import BasicAuth
    BasicAuth(app, {_auth_username: _auth_password})
    logger.info("Dashboard authentication enabled")
else:
    logger.warning("DASHBOARD_USERNAME/PASSWORD not set - running without authentication!")

# Get subjects (excluding configured exclusions and ensuring they are valid participants)
all_subjects = tag_values('subject')
subjects = [s for s in all_subjects if s not in EXCLUDED_SUBJECTS and s in PARTICIPANT_MAPPING]

# Build layout
app.layout = dbc.Container([
    create_header(),
    html.Div([
        dbc.Row([
            # Mobile Menu Button (Visible only on xs/sm)
            dbc.Col([
                dbc.Button("☰ Menu", id="open-sidebar", n_clicks=0, color="secondary", className="mb-2 d-md-none")
            ], xs=12, className="d-md-none"),
            
            # Sidebar (Hidden on mobile, visible on md+)
            dbc.Col([create_controls(subjects)], xs=12, md=3, lg=2, className="d-none d-md-block", style={'padding': '10px'}),
            dbc.Col([
                create_main_tabs(),
                dcc.Loading(
                    id="loading-tabs",
                    type="circle",
                    children=html.Div(id='tab-content', style={'padding': '10px'})
                )
            ], xs=12, md=9, lg=8, style={'padding': '10px'}),
            dbc.Col([
                dcc.Loading(
                    id="loading-cards",
                    type="dot",
                    children=html.Div(id='summary-cards', style={'padding': '8px'})
                )
            ], xs=12, md=12, lg=2, style={'padding': '10px'})
        ])
    ]),
    dcc.Graph(style={'display': 'none'}), # Force load Plotly.js for callback-rendered graphs
    
    # Mobile Sidebar Component
    create_mobile_sidebar(subjects)
], fluid=True, id="main-container", style={'fontFamily': 'system-ui, sans-serif', 'minHeight': '100vh', 'transition': 'background-color 0.3s ease'})


# Callbacks
@app.callback(
    [Output('sess-dd', 'options'),
     Output('sess-dd', 'value'),
     Output('compare-sess-dd', 'options'),
     Output('mobile-sess-dd', 'options'),
     Output('mobile-sess-dd', 'value'),
     Output('mobile-compare-sess-dd', 'options')],
    [Input('sub-dd', 'value'),
     Input('mobile-sub-dd', 'value')]
)
def update_sessions(sub1, sub2):
    """Update session dropdowns when subject changes."""
    ctx = dash.callback_context
    if not ctx.triggered:
        sub = sub1 if sub1 else sub2
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        sub = sub1 if 'mobile' not in trigger_id else sub2
        
    if not sub:
        return [], None, [], [], None, []
        
    sessions = tag_values('session', subject=sub)
    opts = [{'label': s.title(), 'value': s} for s in sessions]
    default = sessions[0] if sessions else None
    return opts, default, opts, opts, default, opts


@app.callback(
    [Output('sub-dd', 'options'),
     Output('sub-dd', 'value'),
     Output('mobile-sub-dd', 'options'),
     Output('mobile-sub-dd', 'value')],
    [Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')],
    [State('sub-dd', 'value'),
     State('mobile-sub-dd', 'value')]
)
def update_subject_dropdown(ex1, ex2, curr_val1, curr_val2):
    """Update subject dropdowns when exclude bad data is toggled."""
    exclude_bad = ex1 or ex2
    from src.backend.database import tag_values
    from src.backend.data_quality import get_quality_summary
    from src.config import EXCLUDED_SUBJECTS
    from src.constants import PARTICIPANT_MAPPING
    
    all_subjects = tag_values('subject')
    subjects = [s for s in all_subjects if s not in EXCLUDED_SUBJECTS and str(s) in PARTICIPANT_MAPPING]
    
    if exclude_bad:
        summary = get_quality_summary()
        bad_subs = summary.get('bad_subjects', [])
        subjects = [s for s in subjects if s not in bad_subs]
        
    opts = [{'label': f"Participant {PARTICIPANT_MAPPING.get(str(s), s)}", 'value': str(s)} for s in subjects]
    
    val1 = curr_val1 if curr_val1 in subjects else (subjects[0] if subjects else None)
    val2 = curr_val2 if curr_val2 in subjects else (subjects[0] if subjects else None)
    
    return opts, val1, opts, val2


@app.callback(
    Output('summary-cards', 'children'),
    [Input('sub-dd', 'value'),
     Input('sess-dd', 'value'),
     Input('mobile-sub-dd', 'value'),
     Input('mobile-sess-dd', 'value')]
)
def update_summary(sub1, sess1, sub2, sess2):
    """Update KPI summary cards."""
    ctx = dash.callback_context
    if not ctx.triggered:
        sub, sess = sub1, sess1
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if 'mobile' in trigger_id:
            sub, sess = sub2, sess2
        else:
            sub, sess = sub1, sess1
    if not sub or not sess:
        return []
    
    data = load_data(sub, sess)
    if not data:
        return []
    
    quality = calculate_data_quality(data)
    stats = calculate_summary_stats(data)
    
    cards = [
        create_kpi_card('Data Alignment', quality.get('alignment', 'N/A'), 'Overlap of 5s windows', tooltip_text="Percentage of timestamps where all devices have data"),
        create_kpi_card('Active Devices', quality.get('devices_available', 'N/A'), 'Devices with data', tooltip_text="Number of devices reporting valid data in this session")
    ]
    for dev, st in stats.items():
        cards.append(create_kpi_card(dev.title(), f"{st['mean']:.2f}g", f"{st['count']:,} samples", tooltip_text=f"Average acceleration magnitude for {dev}"))
    
    return html.Div(cards)


@app.callback(
    Output('main-container', 'data-theme'),
    Input('theme-toggle', 'value')
)
def update_theme(is_dark):
    return "dark" if is_dark else "light"


@app.callback(
    Output('tab-content', 'children'),
    [Input('tabs', 'active_tab'),
     Input('sub-dd', 'value'),
     Input('sess-dd', 'value'),
     Input('compare-sess-dd', 'value'),
     Input('mobile-sub-dd', 'value'),
     Input('mobile-sess-dd', 'value'),
     Input('mobile-compare-sess-dd', 'value'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def render_tab(tab, sub1, sess1, comp_sess1, sub2, sess2, comp_sess2, is_dark_mode, ex1, ex2):
    """Render content for the selected tab."""
    template = "plotly_dark" if is_dark_mode else "plotly_white"
    exclude_bad = ex1 or ex2
    
    ctx = dash.callback_context
    # Default to desktop if no trigger (initial load)
    if not ctx.triggered:
        sub, sess, comp_sess = sub1, sess1, comp_sess1
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if 'mobile' in trigger_id:
            sub, sess, comp_sess = sub2, sess2, comp_sess2
        else:
            sub, sess, comp_sess = sub1, sess1, comp_sess1
            
    # For tabs that don't need a specific subject, handle them first
    if tab == 'tab-about':
        from src.frontend.layouts import create_about_layout
        return create_about_layout()
        
    if tab == 'tab-corr':
        # Load correlation data (aligned files)
        from src.backend.correlation import get_cohort_analysis
        from src.backend.data_quality import filter_good_subjects
        from src.frontend.layouts import create_correlation_layout
        
        corr_df = get_cohort_analysis()
        if exclude_bad:
            corr_df = filter_good_subjects(corr_df)
        
        # Get list of subjects for dropdown
        subjects = []
        if not corr_df.empty and 'Subject' in corr_df.columns:
            subjects = sorted(corr_df['Subject'].astype(str).unique())
        return create_correlation_layout(corr_df, subjects, template=template)
        
    # The remaining tabs require subject and session
    if not sub or not sess:
        return html.Div('Select subject and session', style={'padding': '40px', 'textAlign': 'center'})
    
    data = load_data(sub, sess)
    if not data:
        return html.Div('No data available', style={'padding': '40px', 'textAlign': 'center'})
    
    if tab == 'tab-timeseries':
        graphs = []
        
        # Main Session Plot
        fig1 = make_time_plot(data, sub, sess, template=template)
        graphs.append(dbc.Card([
            dbc.CardHeader(html.H5(f"Session: {sess}", className="m-0")),
            dbc.CardBody([
                dcc.Graph(figure=fig1, config={'responsive': True, 'displayModeBar': False})
            ])
        ], className="shadow-sm mb-4 dashboard-card"))

        # Comparison Session Plot (if selected)
        if comp_sess and comp_sess != sess:
            comp_data = load_data(sub, comp_sess)
            if comp_data:
                fig2 = make_time_plot(comp_data, sub, comp_sess, template=template)
                graphs.append(dbc.Card([
                    dbc.CardHeader(html.H5(f"Comparison: {comp_sess}", className="m-0 text-muted")),
                    dbc.CardBody([
                        dcc.Graph(figure=fig2, config={'responsive': True, 'displayModeBar': False})
                    ])
                ], className="shadow-sm mb-4 dashboard-card"))
        
        # Combine graphs and stats
        return html.Div(graphs + [
            html.Div(create_device_stats_cards(data), style={'marginTop': '20px'})
        ])
    
    elif tab == 'tab-stats':
        stats = calculate_summary_stats(data)
        return html.Div([
            html.H3('Descriptive Statistics'),
            create_stats_table(stats)
        ])
    
    elif tab == 'tab-compare':
        if not comp_sess:
            return html.Div('Select comparison session', style={'padding': '40px', 'textAlign': 'center'})
            
        data = load_data(sub, sess)
        comp_data = load_data(sub, comp_sess)
        
        if not data or not comp_data:
            return html.Div('Data missing for comparison', style={'padding': '40px', 'textAlign': 'center'})
            
        # Compare sessions
        comp_res = compare_activity_rest(data, comp_data)
        
        return html.Div([
            html.H3(f"Statistical Comparison: {sess} vs {comp_sess}"),
            html.P("Comparing mean magnitude and variability between sessions."),
            make_comparison_table(comp_res)
        ], style={'padding': '20px'})

    elif tab == 'tab-about':
        from src.frontend.layouts import create_about_layout
        return create_about_layout()
    
    return html.Div("Select a tab")

# Callbacks for Correlation Tab - Overall Stats (dynamic based on filter)
@app.callback(
    [Output('overall-corr-value', 'children'),
     Output('overall-corr-info', 'children')],
    [Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value'),
     Input('tabs', 'active_tab')]
)
def update_overall_corr_stats(ex1, ex2, tab):
    if tab != 'tab-corr':
        return "", ""
    exclude_bad = ex1 or ex2
    
    from src.backend.correlation import get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.constants import COLORS
    
    df = get_cohort_analysis()
    if exclude_bad:
        df = filter_good_subjects(df)
    
    if df.empty or 'Bangle_Actigraph' not in df.columns:
        return html.Span("N/A", style={'fontSize': '2.8rem', 'fontWeight': '700', 'color': '#999'}), ""
    
    overall_r = df['Bangle_Actigraph'].mean()
    n_subjects = len(df)
    min_r = df['Bangle_Actigraph'].min()
    max_r = df['Bangle_Actigraph'].max()
    
    # Color based on quality
    if overall_r >= 0.7:
        color = COLORS['ivy']
    elif overall_r >= 0.5:
        color = COLORS['buttercup']
    else:
        color = COLORS['azalea']
    
    suffix = " (filtered)" if exclude_bad else ""
    
    value = html.Span(f"r = {overall_r:.2f}", style={
        'fontSize': '2.8rem', 'fontWeight': '700', 'color': color
    })
    info = f"N = {n_subjects} subjects{suffix}  |  Range: {min_r:.2f} → {max_r:.2f}"
    
    return value, info

@app.callback(
    Output('corr-bar-chart', 'figure'),
    [Input('tabs', 'active_tab'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def update_corr_bar_chart(tab, is_dark, ex1, ex2):
    if tab != 'tab-corr':
        return {}
    exclude_bad = ex1 or ex2
    template = "plotly_dark" if is_dark else "plotly_white"
    from src.backend.correlation import get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.frontend.visualizations import make_correlation_bar_chart
    
    df = get_cohort_analysis()
    if exclude_bad:
        df = filter_good_subjects(df)
    return make_correlation_bar_chart(df, template=template)

@app.callback(
    Output('corr-boxplot', 'figure'),
    [Input('tabs', 'active_tab'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def update_corr_boxplot(tab, is_dark, ex1, ex2):
    if tab != 'tab-corr':
        return {}
    exclude_bad = ex1 or ex2
    template = "plotly_dark" if is_dark else "plotly_white"
    from src.backend.correlation import get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.frontend.visualizations import make_subgroup_boxplot
    
    df = get_cohort_analysis()
    if exclude_bad:
        df = filter_good_subjects(df)
    
    # Use 'Gender' or 'Sex' column for subgroup comparison
    group_col = 'Gender' if 'Gender' in df.columns else 'Sex' if 'Sex' in df.columns else None
    if group_col:
        return make_subgroup_boxplot(df, group_col, template=template)
    else:
        # Fallback: create simple boxplot without grouping
        import plotly.express as px
        if 'Bangle_Actigraph' in df.columns:
            fig = px.box(df, y='Bangle_Actigraph', points='all', title='Correlation Distribution', template=template)
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            return fig
        return {}

@app.callback(
    [Output('corr-scatter-plot', 'figure'),
     Output('corr-time-plot', 'figure')],
    Input('corr-subject-dd', 'value'),
    Input('theme-toggle', 'value')
)
def update_corr_detail_plots(subject, is_dark):
    if not subject:
        return {}, {}
        
    from src.backend.correlation import load_aligned_data
    from src.frontend.visualizations import make_scatter_plot
    import plotly.graph_objects as go
    from src.constants import DEVICE_COLORS, PARTICIPANT_MAPPING
    
    
    # New load_aligned_data returns single merged DF
    df = load_aligned_data(subject)
    
    template = "plotly_dark" if is_dark else "plotly_white"

    if df is None or df.empty:
        empty_fig = go.Figure(layout=dict(template=template))
        empty_fig.add_annotation(text="Data not available", showarrow=False)
        return empty_fig, empty_fig
    
    # Scatter: Bangle vs Actigraph
    # df has columns 'Actigraph', 'Bangle', 'EmotiBit' set as index 'timestamp'
    if 'Actigraph' in df.columns and 'Bangle' in df.columns:
        scatter_fig = make_scatter_plot(df, 'Actigraph', 'Bangle', template=template)
        scatter_fig.update_layout(
            xaxis_title='Actigraph (g)',
            yaxis_title='Bangle (g)',
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
    else:
        scatter_fig = go.Figure(layout=dict(template=template))
        scatter_fig.add_annotation(text="Missing Actigraph/Bangle data", showarrow=False)
    
    # Time Series comparison
    time_fig = go.Figure(layout=dict(template=template))
    for dev in df.columns:
        color = DEVICE_COLORS.get(dev.lower(), 'gray')
        time_fig.add_trace(go.Scatter(
            x=df.index,
            y=df[dev],
            name=dev,
            mode='lines',
            line=dict(color=color)
        ))
    time_fig.update_layout(
        title=f"Participant {PARTICIPANT_MAPPING.get(str(subject), subject)}: Aligned Time Series (5s)",
        height=300,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    
    return scatter_fig, time_fig


@app.callback(
    Output('calorimetry-timeline-plot', 'figure'),
    Input('corr-subject-dd', 'value'),
    Input('theme-toggle', 'value')
)
def update_calorimetry_timeline(subject, is_dark):
    """Update the new Calorimetry Energy Expenditure timeline - loads from InfluxDB."""
    if not subject:
        return {}
        
    from src.frontend.visualizations import make_calorimetry_timeline
    import plotly.graph_objects as go
    import pandas as pd
    from src.config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET
    from influxdb_client import InfluxDBClient
    
    template = "plotly_dark" if is_dark else "plotly_white"
    
    # Query calorimetry data from InfluxDB
    try:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        query_api = client.query_api()
        
        flux_query = f'''
        from(bucket: "{INFLUX_BUCKET}")
            |> range(start: 0)
            |> filter(fn: (r) => r["_measurement"] == "calorimetry")
            |> filter(fn: (r) => r["subject"] == "{subject}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> sort(columns: ["_time"])
        '''
        
        result = query_api.query_data_frame(flux_query)
        client.close()
        
        if result is None or (isinstance(result, pd.DataFrame) and result.empty):
            empty_fig = go.Figure(layout=dict(template=template))
            empty_fig.add_annotation(text=f"No calorimetry data found for subject {subject}", showarrow=False)
            return empty_fig
        
        # Handle list of dataframes
        if isinstance(result, list):
            result = pd.concat(result, ignore_index=True) if result else pd.DataFrame()
        
        if result.empty:
            empty_fig = go.Figure(layout=dict(template=template))
            empty_fig.add_annotation(text=f"No calorimetry data found for subject {subject}", showarrow=False)
            return empty_fig
        
        # Set timestamp as index
        df_cal = result.copy()
        df_cal['timestamp'] = pd.to_datetime(df_cal['_time'])
        df_cal = df_cal.set_index('timestamp')
        
        # Rename lowercase fields to uppercase for visualization
        if 'hr' in df_cal.columns:
            df_cal = df_cal.rename(columns={'hr': 'HR', 'mets': 'METS'})
        
        return make_calorimetry_timeline(df_cal, subject, template=template)
        
    except Exception as e:
        empty_fig = go.Figure(layout=dict(template=template))
        empty_fig.add_annotation(text=f"Error loading calorimetry from InfluxDB: {e}", showarrow=False)
        return empty_fig


# Callback to toggle mobile sidebar
@app.callback(
    Output("mobile-sidebar", "is_open"),
    Input("open-sidebar", "n_clicks"),
    [State("mobile-sidebar", "is_open")],
)
def toggle_sidebar(n1, is_open):
    if n1:
        return not is_open
    return is_open


def run_server(host: str = None, port: int = 8050, debug: bool = False):
    """
    Run the dashboard server.
    
    Args:
        host: Host address (default: from env or '0.0.0.0')
        port: Port number (default: 8050)
        debug: Enable debug mode
    """
    import logging
    # Suppress default Dash startup message
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    if host is None:
        host = os.getenv('DASHBOARD_HOST', '0.0.0.0')
    
    print(f'\nDIWAH Analytics Dashboard running at: http://127.0.0.1:{port}')
    
    app.run(debug=debug, host=host, port=port, use_reloader=False)


if __name__ == '__main__':
    debug = os.getenv('DASHBOARD_DEBUG', 'False').lower() == 'true'
    run_server(debug=debug)
