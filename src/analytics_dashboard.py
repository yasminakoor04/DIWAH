"""
DIWAH Analytics Dashboard - Main Application.

Comprehensive validation dashboard for wearable sensor research at Linnaeus University.
This is the main entry point that ties together all dashboard components.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import pandas as pd
import numpy as np
import plotly.graph_objects as go
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
    data = {'raw': {}, 'agg': {}, 'stats': {}, 'calorimetry': {}, 'error': None}
    
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
            # Query calorimetry (Vyntus HR)
            calo_flux = f'''from(bucket: "{INFLUX_BUCKET}")
            |> range(start: -100y)
            |> filter(fn: (r) => r._measurement == "calorimetry" and r.subject == "{safe_subject}" and r.session == "{safe_session}" and r._field == "HR")
            |> aggregateWindow(every:5s, fn:mean, createEmpty:false)
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'''
            calo_df = query_api.query_data_frame(calo_flux)
            if isinstance(calo_df, list) and calo_df:
                calo_df = pd.concat(calo_df, ignore_index=False)
            if isinstance(calo_df, pd.DataFrame) and not calo_df.empty and 'HR' in calo_df.columns:
                calo_df['HR'] = pd.to_numeric(calo_df['HR'], errors='coerce')
                calo_df = calo_df.dropna(subset=['HR'])
                data['calorimetry']['hr'] = calo_df
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

# Authentication has been removed.

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
     Input('mobile-sub-dd', 'value')]
)
def update_summary(sub1, sub2):
    """Update KPI summary cards for the Activity session."""
    ctx = dash.callback_context
    if not ctx.triggered:
        sub = sub1
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if 'mobile' in trigger_id:
            sub = sub2
        else:
            sub = sub1
            
    sess = "activity"
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
    
    # Polar HR card
    hr_df = data.get('calorimetry', {}).get('hr')
    if hr_df is not None and not hr_df.empty:
        avg_hr = hr_df['HR'].mean()
        hr_count = len(hr_df)
        cards.append(create_kpi_card(
            'Polar HR',
            f"{avg_hr:.0f} bpm",
            f"{hr_count:,} samples",
            tooltip_text="Average heart rate recorded by the Polar Chest Strap during this activity session"
        ))
    
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
     Input('mobile-sub-dd', 'value'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def render_tab(tab, sub1, sub2, is_dark_mode, ex1, ex2):
    """Render content for the selected tab targeting the Activity session."""
    template = "plotly_dark" if is_dark_mode else "plotly_white"
    exclude_bad = ex1 or ex2
    sess = "activity"
    comp_sess = None
    
    ctx = dash.callback_context
    if not ctx.triggered:
        sub = sub1
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if 'mobile' in trigger_id:
            sub = sub2
        else:
            sub = sub1
            
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

    if tab == 'tab-corr-emotibit':
        from src.backend.correlation import get_cohort_analysis
        from src.backend.data_quality import filter_good_subjects
        from src.frontend.layouts import create_emotibit_correlation_layout
        
        corr_df = get_cohort_analysis()
        if exclude_bad:
            corr_df = filter_good_subjects(corr_df)
            
        subjects = []
        if not corr_df.empty and 'Subject' in corr_df.columns:
            subjects = sorted(corr_df['Subject'].astype(str).unique())
        return create_emotibit_correlation_layout(corr_df, subjects, template=template)


    if tab == 'tab-ml':
        from src.frontend.layouts import create_ml_layout
        return create_ml_layout(is_dark=is_dark_mode)
                
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
    Output('corr-cohort-scatter', 'figure'),
    [Input('tabs', 'active_tab'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def update_corr_cohort_scatter(tab, is_dark, ex1, ex2):
    if tab != 'tab-corr':
        return {}
    exclude_bad = ex1 or ex2
    template = "plotly_dark" if is_dark else "plotly_white"
    
    from src.backend.correlation import get_all_aligned_data, get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.frontend.visualizations import make_scatter_plot
    import plotly.graph_objects as go
    
    df = get_all_aligned_data(exclude_bad=exclude_bad)
    
    # Calculate the mean of individual correlations for the override
    corr_df = get_cohort_analysis()
    if exclude_bad:
        corr_df = filter_good_subjects(corr_df)
    overall_r = corr_df['Bangle_Actigraph'].dropna().mean() if not corr_df.empty and 'Bangle_Actigraph' in corr_df.columns else None
    
    if df.empty or 'Actigraph' not in df.columns or 'Bangle' not in df.columns:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text="No cohort data available", showarrow=False)
        return fig
        
    fig = make_scatter_plot(df, 'Actigraph', 'Bangle', template=template, override_r=overall_r)
    fig.update_layout(
        xaxis_title='Actigraph (g)',
        yaxis_title='Bangle (g)',
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig

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


# === EmotiBit Tab Callbacks ===

@app.callback(
    [Output('emo-overall-corr-value', 'children'),
     Output('emo-overall-corr-info', 'children')],
    [Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value'),
     Input('tabs', 'active_tab')]
)
def update_emo_overall_corr_stats(ex1, ex2, tab):
    if tab != 'tab-corr-emotibit':
        return "", ""
    exclude_bad = ex1 or ex2
    
    from src.backend.correlation import get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.constants import COLORS
    
    df = get_cohort_analysis()
    if exclude_bad:
        df = filter_good_subjects(df)
    
    if df.empty or 'EmotiBit_Actigraph' not in df.columns:
        return html.Span("N/A", style={'fontSize': '2.8rem', 'fontWeight': '700', 'color': '#999'}), ""
    
    valid = df['EmotiBit_Actigraph'].dropna()
    if valid.empty:
        return html.Span("N/A", style={'fontSize': '2.8rem', 'fontWeight': '700', 'color': '#999'}), ""
        
    overall_r = valid.mean()
    n_subjects = len(valid)
    min_r = valid.min()
    max_r = valid.max()
    
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
    Output('emo-corr-bar-chart', 'figure'),
    [Input('tabs', 'active_tab'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def update_emo_corr_bar_chart(tab, is_dark, ex1, ex2):
    if tab != 'tab-corr-emotibit':
        return {}
    exclude_bad = ex1 or ex2
    template = "plotly_dark" if is_dark else "plotly_white"
    from src.backend.correlation import get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.frontend.visualizations import make_correlation_bar_chart
    
    df = get_cohort_analysis()
    if exclude_bad:
        df = filter_good_subjects(df)
    return make_correlation_bar_chart(df, metric='EmotiBit_Actigraph', template=template)


@app.callback(
    Output('emo-corr-boxplot', 'figure'),
    [Input('tabs', 'active_tab'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def update_emo_corr_boxplot(tab, is_dark, ex1, ex2):
    if tab != 'tab-corr-emotibit':
        return {}
    exclude_bad = ex1 or ex2
    template = "plotly_dark" if is_dark else "plotly_white"
    from src.backend.correlation import get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.frontend.visualizations import make_subgroup_boxplot
    
    df = get_cohort_analysis()
    if exclude_bad:
        df = filter_good_subjects(df)
    
    group_col = 'Gender' if 'Gender' in df.columns else 'Sex' if 'Sex' in df.columns else None
    if group_col:
        return make_subgroup_boxplot(df, group_col, metric='EmotiBit_Actigraph', template=template)
    else:
        import plotly.express as px
        if 'EmotiBit_Actigraph' in df.columns:
            fig = px.box(df, y='EmotiBit_Actigraph', points='all', title='Correlation Distribution', template=template)
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            return fig
        return {}

@app.callback(
    Output('emo-corr-cohort-scatter', 'figure'),
    [Input('tabs', 'active_tab'),
     Input('theme-toggle', 'value'),
     Input('exclude-bad-data-switch', 'value'),
     Input('mobile-exclude-bad-data-switch', 'value')]
)
def update_emo_corr_cohort_scatter(tab, is_dark, ex1, ex2):
    if tab != 'tab-corr-emotibit':
        return {}
    exclude_bad = ex1 or ex2
    template = "plotly_dark" if is_dark else "plotly_white"
    
    from src.backend.correlation import get_all_aligned_data, get_cohort_analysis
    from src.backend.data_quality import filter_good_subjects
    from src.frontend.visualizations import make_scatter_plot
    import plotly.graph_objects as go
    
    df = get_all_aligned_data(exclude_bad=exclude_bad)
    
    # Calculate the mean of individual correlations for the override
    corr_df = get_cohort_analysis()
    if exclude_bad:
        corr_df = filter_good_subjects(corr_df)
    overall_r = corr_df['EmotiBit_Actigraph'].dropna().mean() if not corr_df.empty and 'EmotiBit_Actigraph' in corr_df.columns else None
    
    if df.empty or 'Actigraph' not in df.columns or 'EmotiBit' not in df.columns:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text="No cohort data available", showarrow=False)
        return fig
        
    fig = make_scatter_plot(df, 'Actigraph', 'EmotiBit', template=template, override_r=overall_r)
    fig.update_layout(
        xaxis_title='Actigraph (g)',
        yaxis_title='EmotiBit (g)',
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig


@app.callback(
    [Output('emo-corr-scatter-plot', 'figure'),
     Output('emo-corr-time-plot', 'figure')],
    Input('emo-corr-subject-dd', 'value'),
    Input('theme-toggle', 'value')
)
def update_emo_corr_detail_plots(subject, is_dark):
    if not subject:
        return {}, {}
        
    from src.backend.correlation import load_aligned_data
    from src.frontend.visualizations import make_scatter_plot
    import plotly.graph_objects as go
    from src.constants import DEVICE_COLORS, PARTICIPANT_MAPPING
    
    df = load_aligned_data(subject)
    template = "plotly_dark" if is_dark else "plotly_white"

    if df is None or df.empty:
        empty_fig = go.Figure(layout=dict(template=template))
        empty_fig.add_annotation(text="Data not available", showarrow=False)
        return empty_fig, empty_fig
    
    if 'Actigraph' in df.columns and 'EmotiBit' in df.columns:
        scatter_fig = make_scatter_plot(df, 'Actigraph', 'EmotiBit', template=template)
        scatter_fig.update_layout(
            xaxis_title='Actigraph (g)',
            yaxis_title='EmotiBit (g)',
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
    else:
        scatter_fig = go.Figure(layout=dict(template=template))
        scatter_fig.add_annotation(text="Missing Actigraph/EmotiBit data", showarrow=False)
    
    time_fig = go.Figure(layout=dict(template=template))
    for dev in df.columns:
        if dev.lower() not in ['actigraph', 'emotibit']:
            continue
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


# --- Live Data Hook for ML Tab ---
import os
from pathlib import Path
import json as _json
import numpy as _np

_data_dir = Path(__file__).resolve().parents[1] / "scripts" / "Acc_pipe" / "data" / "processed"
_fi_path = _data_dir / "ml_feature_importance.json"

# Note: ML Predictions are now loaded dynamically from InfluxDB inside the callback!

_fi_data = {}
if _fi_path.exists():
    try:
        with open(_fi_path, 'r') as _f:
            _fi_data = _json.load(_f)
    except Exception:
        pass

# --- Feature Importance Callback ---
@app.callback(
    Output("fi-bar-chart", "figure"),
    [Input("fi-device-dd", "value"),
     Input("theme-toggle", "value")]
)
def update_feature_importance(device_key, is_dark):
    template = "plotly_dark" if is_dark else "plotly_white"
    features = _fi_data.get(device_key, [])

    if not features:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text="No feature importance data available", showarrow=False)
        return fig

    top = features[:15]
    top.reverse()  # so the most important is at the top of horizontal bar

    names = [f["feature"].replace(f"{device_key}_", "") for f in top]
    values = [f["importance"] for f in top]

    fig = go.Figure(go.Bar(
        x=values, y=names, orientation='h',
        marker_color=COLORS['ivy'],
        text=[f"{v:.3f}" for v in values],
        textposition='outside',
        hovertemplate="<b>%{y}</b><br>Importance: %{x:.4f}<extra></extra>"
    ))

    hover_bg = "#333" if is_dark else "white"
    hover_font = "#eee" if is_dark else "#222"

    fig.update_layout(
        template=template,
        hoverlabel=dict(bgcolor=hover_bg, font_color=hover_font),
        xaxis_title="Gini Importance",
        yaxis=dict(tickfont=dict(size=10)),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=180, r=40, t=20, b=40),
        xaxis=dict(gridcolor='rgba(150,150,150,0.1)'),
        height=450
    )
    return fig


# --- ML Scatter, Residual, Bland-Altman, Line Callbacks ---
@app.callback(
    [Output("ml-scatter-plot", "figure"),
     Output("ml-residual-plot", "figure"),
     Output("ml-bland-altman-plot", "figure"),
     Output("ml-line-plot", "figure")],
    [Input("ml-device-dd", "value"),
     Input("ml-model-dd", "value"),
     Input("theme-toggle", "value")]
)
def update_ml_plots(selected_device, selected_model, is_dark):
    template = "plotly_dark" if is_dark else "plotly_white"
    hover_bg = "#333" if is_dark else "white"
    hover_font = "#eee" if is_dark else "#222"
    
    # Read from local ml_predictions.csv (always up-to-date with latest evaluation run)
    try:
        predictions_csv = Path(__file__).resolve().parent.parent / "scripts" / "Acc_pipe" / "data" / "processed" / "ml_predictions.csv"
        all_preds = pd.read_csv(predictions_csv)
        filtered_df = all_preds[
            (all_preds["Device"] == selected_device) &
            (all_preds["Model"] == selected_model)
        ].copy()
        
        if filtered_df.empty:
            true_vals = np.array([])
            pred_vals = np.array([])
        else:
            true_vals = filtered_df["True_METs"].values
            pred_vals = filtered_df["Pred_METs"].values
    except Exception as e:
        print(f"Error loading ml_predictions.csv: {e}")
        true_vals = np.array([])
        pred_vals = np.array([])
        filtered_df = pd.DataFrame(columns=["True_METs", "Pred_METs"])

    grid_color = 'rgba(255,255,255,0.1)' if is_dark else 'rgba(0,0,0,0.1)'
    axis_color = 'rgba(255,255,255,0.5)' if is_dark else 'black'
    y_range = [-10, 45] if (selected_model == "Multiple Linear Regression" and selected_device == "Reference (ActiGraph + Polar HR)") else [0, 20]

    # --- 1. Scatter Plot (y=x) ---
    scatter_fig = go.Figure()
    scatter_fig.add_trace(go.Scatter(
        x=true_vals, y=pred_vals,
        mode="markers", name="Predictions",
        marker=dict(color=COLORS['crocus'], size=8, opacity=0.6, line=dict(width=1, color="rgba(255,255,255,0.2)")),
        hovertemplate="<b>True:</b> %{x:.2f} METs<br><b>Predicted:</b> %{y:.2f} METs<extra></extra>"
    ))
    scatter_fig.add_trace(go.Scatter(
        x=[0, 15], y=[0, 15], mode="lines", name="Perfect Prediction (y=x)",
        line=dict(color=COLORS['buttercup'], width=3, dash="dash"), hoverinfo="skip"
    ))
    scatter_fig.update_layout(
        title={"text": f"Prediction Accuracy: {selected_device}", "font": {"size": 16}},
        xaxis_title="True METs", yaxis_title="Predicted METs",
        xaxis=dict(range=[0, 15], zeroline=False, gridcolor=grid_color),
        yaxis=dict(range=y_range, zeroline=True, zerolinewidth=1, zerolinecolor=axis_color, gridcolor=grid_color),
        template=template,
        hoverlabel=dict(bgcolor=hover_bg, font_color=hover_font),
        margin=dict(t=60, b=50, l=50, r=30),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(x=0.01, y=0.98, bgcolor="rgba(0,0,0,0)"), hovermode="closest", height=450
    )

    # --- 2. Residual Plot ---
    residuals = pred_vals - true_vals
    residual_fig = go.Figure()
    residual_fig.add_trace(go.Scatter(
        x=true_vals, y=residuals,
        mode="markers", name="Residuals",
        marker=dict(color=COLORS['crocus'], size=8, opacity=0.6),
        hovertemplate="True: %{x:.2f}<br>Error: %{y:.2f} METs<extra></extra>"
    ))
    # Zero line
    residual_fig.add_hline(y=0, line_dash="solid", line_color=COLORS['buttercup'], line_width=2)
    # ±1 MET clinically acceptable band
    residual_fig.add_hrect(y0=-1, y1=1, fillcolor="rgba(76,175,80,0.1)", line_width=0,
                           annotation_text="±1 MET", annotation_position="top right",
                           annotation_font_color=COLORS['ivy'])

    residual_fig.update_layout(
        title={"text": f"Residual Analysis: {selected_device}", "font": {"size": 16}},
        xaxis_title="True METs", yaxis_title="Prediction Error (METs)",
        xaxis=dict(range=[0, 16], gridcolor=grid_color),
        yaxis=dict(gridcolor=grid_color, zeroline=True, zerolinecolor=axis_color),
        template=template,
        hoverlabel=dict(bgcolor=hover_bg, font_color=hover_font),
        margin=dict(t=60, b=50, l=50, r=30),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False, hovermode="closest", height=450
    )

    # --- 3. Bland-Altman Plot ---
    ba_mean = (true_vals + pred_vals) / 2
    ba_diff = pred_vals - true_vals
    mean_diff = float(_np.mean(ba_diff)) if len(ba_diff) > 0 else 0
    std_diff = float(_np.std(ba_diff)) if len(ba_diff) > 0 else 0
    upper_loa = mean_diff + 1.96 * std_diff
    lower_loa = mean_diff - 1.96 * std_diff

    ba_fig = go.Figure()
    ba_fig.add_trace(go.Scatter(
        x=ba_mean, y=ba_diff,
        mode="markers", name="Observations",
        marker=dict(color=COLORS['crocus'], size=8, opacity=0.6),
        hovertemplate="Mean: %{x:.2f}<br>Diff: %{y:.2f} METs<extra></extra>"
    ))
    # Mean bias line
    ba_fig.add_hline(y=mean_diff, line_dash="solid", line_color=COLORS['buttercup'], line_width=2,
                     annotation_text=f"Mean bias: {mean_diff:.2f}", annotation_position="top left",
                     annotation_font_color=COLORS['buttercup'])
    # Upper LOA
    ba_fig.add_hline(y=upper_loa, line_dash="dash", line_color=COLORS['azalea'], line_width=1.5,
                     annotation_text=f"+1.96 SD: {upper_loa:.2f}", annotation_position="top right",
                     annotation_font_color=COLORS['azalea'])
    # Lower LOA
    ba_fig.add_hline(y=lower_loa, line_dash="dash", line_color=COLORS['azalea'], line_width=1.5,
                     annotation_text=f"-1.96 SD: {lower_loa:.2f}", annotation_position="bottom right",
                     annotation_font_color=COLORS['azalea'])

    # Count within LOA
    within = int(_np.sum((ba_diff >= lower_loa) & (ba_diff <= upper_loa))) if len(ba_diff) > 0 else 0
    total = len(ba_diff) if len(ba_diff) > 0 else 1
    pct_within = within / total * 100

    ba_fig.update_layout(
        title={"text": f"Bland-Altman: {selected_device} ({pct_within:.0f}% in LOA)", "font": {"size": 14}},
        xaxis_title="Mean of True & Predicted (METs)", yaxis_title="Difference (Pred - True)",
        xaxis=dict(gridcolor=grid_color),
        yaxis=dict(gridcolor=grid_color, zeroline=True, zerolinecolor=axis_color),
        template=template,
        hoverlabel=dict(bgcolor=hover_bg, font_color=hover_font),
        margin=dict(t=60, b=50, l=50, r=30),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False, hovermode="closest", height=450
    )

    # --- 4. Sequential Line Chart ---
    line_fig = go.Figure()
    sorted_df = filtered_df.sort_values(by="True_METs").reset_index(drop=True)

    line_fig.add_trace(go.Scatter(
        y=sorted_df["True_METs"], mode="lines+markers", name="Actual",
        line=dict(color=COLORS['buttercup'], width=3), marker=dict(size=6),
        hovertemplate="<b>Actual:</b> %{y:.2f} METs<extra></extra>"
    ))
    line_fig.add_trace(go.Scatter(
        y=sorted_df["Pred_METs"], mode="lines+markers", name="Predicted",
        line=dict(color=COLORS['crocus'], width=3), marker=dict(size=6),
        hovertemplate="<b>Predicted:</b> %{y:.2f} METs<extra></extra>"
    ))
    line_fig.update_layout(
        title={"text": "Tracking Across Activity Spectrum", "font": {"size": 16}},
        xaxis_title="Activity Spectrum (Rest → Peak)", yaxis_title="Energy (METs)",
        xaxis=dict(zeroline=False, gridcolor=grid_color),
        yaxis=dict(range=y_range, zeroline=True, zerolinewidth=1, zerolinecolor=axis_color, gridcolor=grid_color),
        template=template,
        hoverlabel=dict(bgcolor=hover_bg, font_color=hover_font),
        margin=dict(t=60, b=50, l=50, r=30),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified", height=450
    )

    return scatter_fig, residual_fig, ba_fig, line_fig


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
