"""
UI layout components for DIWAH Analytics Dashboard.

This module contains all Dash HTML and layout component definitions.
"""

from typing import Dict, List, Any, Optional
import pandas as pd

from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc

from ..constants import COLORS, DEVICE_COLORS, PARTICIPANT_MAPPING
from ..backend.stats_utils import format_p_value


def create_kpi_card(title: str, value: str, subtext: str, color: str = "primary", tooltip_text: Optional[str] = None) -> dbc.Card:
    """
    Create a KPI card component.
    
    Args:
        title: Card title
        value: Main value to display
        subtext: Subtitle/description
        color: Bootstrap color class (unused, kept for API compatibility)
        tooltip_text: Optional text for the info tooltip
    
    Returns:
        Dash Bootstrap Card component
    """
    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.H6(
                    title,
                    className="card-subtitle text-muted-dark kpi-card-subtitle"
                    # Style removed - handled by CSS
                ),
                html.I(className="bi bi-info-circle-fill kpi-card-info-icon", id=f"tooltip-target-{title.replace(' ', '-').lower()}"),
                dbc.Tooltip(
                    tooltip_text or f"Explanation for {title}",
                    target=f"tooltip-target-{title.replace(' ', '-').lower()}",
                    placement="top",
                    className="kpi-card-tooltip"
                )
            ], className="kpi-card-body-content"),
            html.H2(
                value,
                className="card-title kpi-card-title"
                # Style removed - handled by CSS
            ),
            html.Small(subtext, className="text-muted", style={"fontSize": "0.75rem"})
        ], className="kpi-card-container"),
        className="kpi-card-shadow card",
        style={
            "borderLeft": f"5px solid {DEVICE_COLORS.get(color, COLORS.get(color, '#ccc'))}"
            # borderRadius and boxShadow handled by CSS class .kpi-card-shadow and .card
        }
    )


def make_comparison_table(comparison: Dict[str, Dict[str, float]]) -> html.Div:
    """
    Create activity vs rest comparison table.
    
    Args:
        comparison: Dictionary of comparison stats per device
    
    Returns:
        HTML table component
    """
    if not comparison:
        return html.Div("No comparison data available", style={'padding': '20px'})
    
    rows = []
    for dev, stats in comparison.items():
        rows.append(html.Tr([
            html.Td(dev.title(), style={'fontWeight': 'bold', 'color': DEVICE_COLORS.get(dev)}),
            html.Td(f"{stats['activity_mean']:.2f} ± {stats['activity_std']:.2f}"),
            html.Td(f"{stats['rest_mean']:.2f} ± {stats['rest_std']:.2f}"),
            html.Td(f"{stats['difference']:+.2f}g", className="comparison-diff"),
            html.Td(format_p_value(stats['p_value'])),
            html.Td(f"{stats['cohens_d']:.2f}")
        ]))
    
    table = html.Table([
        html.Thead(html.Tr([
            html.Th('Device'),
            html.Th('Activity'),
            html.Th('Rest'),
            html.Th('Difference'),
            html.Th([
                "p-value",
                html.I(className="bi bi-info-circle-fill ms-2", id="tooltip-pvalue", style={"fontSize": "0.8rem", "color": "#ccc", "cursor": "pointer"}),
                dbc.Tooltip("A p-value < 0.05 indicates there is a statistically significant difference between Activity and Rest periods. This means the difference is not just random chance.", target="tooltip-pvalue", placement="top")
            ]),
            html.Th([
                "Cohen's d",
                html.I(className="bi bi-info-circle-fill ms-2", id="tooltip-cohensd", style={"fontSize": "0.8rem", "color": "#ccc", "cursor": "pointer"}),
                dbc.Tooltip("Cohen's d measures the 'effect size' or how large the difference actually is. 0.2 is a small effect, 0.5 is medium, and 0.8+ is a large effect.", target="tooltip-cohensd", placement="top")
            ])
        ])),
        html.Tbody(rows)
    ], className="comparison-table")
    
    return table


def create_header() -> html.Div:
    """Create the dashboard header component."""
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.H1('DIWAH Analytics Dashboard', className="header-title"),
                html.P(
                    'Linnaeus University • Wearable Sensor Validation Study',
                    className="header-subtitle"
                )
            ]),
            dbc.Col([
                dbc.Switch(
                    id="theme-toggle",
                    label="Dark Mode",
                    value=False,
                    className="float-end theme-toggle",
                )
            ], width="auto")
        ], align="center")
    ], id="header-container")


def create_mobile_sidebar(subjects: List[str]) -> dbc.Offcanvas:
    """
    Create the offcanvas sidebar for mobile devices.
    
    Args:
        subjects: List of available subject IDs
    
    Returns:
        Offcanvas component containing controls
    """
    return dbc.Offcanvas(
        create_controls(subjects, id_prefix="mobile-"),
        id="mobile-sidebar",
        title="Menu",
        is_open=False,
        placement="start",
        style={'maxWidth': '80%'} # Don't take full width on small phones
    )


def create_controls(subjects: List[str], id_prefix: str = "") -> html.Div:
    """
    Create the control panel component.
    
    Args:
        subjects: List of available subject IDs
        id_prefix: Optional prefix for component IDs to avoid duplicates
    
    Returns:
        Control panel component
    """
    return html.Div([
        html.H5('Controls', className="controls-header"),
        html.Label('Participant', className="controls-label"),
        dcc.Dropdown(
            id=f'{id_prefix}sub-dd',
            options=[{'label': f"Participant {PARTICIPANT_MAPPING.get(str(s), s)}", 'value': s} for s in subjects],
            value=subjects[0] if subjects else None,
            className="controls-dropdown"
        ),
        html.Label('Session', className="controls-label"),
        dcc.Dropdown(id=f'{id_prefix}sess-dd', className="controls-dropdown"),
        html.Label('Compare with', className="controls-label"),
        dcc.Dropdown(id=f'{id_prefix}compare-sess-dd', placeholder='Select to compare...'),
        
        html.Div([
            dbc.Switch(
                id=f'{id_prefix}exclude-bad-data-switch',
                value=False,
                style={'display': 'none'}
            ),
        ], style={'display': 'none'})
    ], className="card controls-card")


def create_main_tabs() -> dbc.Tabs:
    """Create the main tab navigation component."""
    return dbc.Tabs([
        dbc.Tab(label='Time Series', tab_id='tab-timeseries'),
        dbc.Tab(label='Statistics', tab_id='tab-stats'),
        dbc.Tab(label='Correlations', tab_id='tab-corr'),
        dbc.Tab(label='About', tab_id='tab-about')
    ], id='tabs', active_tab='tab-timeseries')


def create_stats_table(stats: Dict[str, Dict[str, float]]) -> html.Table:
    """
    Create descriptive statistics table.
    
    Args:
        stats: Dictionary of statistics per device
    
    Returns:
        HTML table component
    """
    rows = []
    for dev, st in stats.items():
        rows.append(html.Tr([
            html.Td(dev.title(), style={'fontWeight': 'bold', 'color': DEVICE_COLORS.get(dev)}),
            html.Td(f"{st['mean']:.3f}"),
            html.Td(f"{st['std']:.3f}"),
            html.Td(f"{st['median']:.3f}"),
            html.Td(f"{st['min']:.3f}"),
            html.Td(f"{st['max']:.3f}"),
            html.Td(f"{st['count']:,}")
        ]))
    
    return html.Table([
        html.Thead(html.Tr([
            html.Th('Device'),
            html.Th('Mean'),
            html.Th('Std'),
            html.Th('Median'),
            html.Th('Min'),
            html.Th('Max'),
            html.Th('Count')
        ])),
        html.Tbody(rows)
    ], className="stats-table")


def create_device_stats_cards(data: Dict[str, Any]) -> List[html.Div]:
    """
    Create device statistics cards for time series tab.
    
    Args:
        data: Data dictionary containing 'stats' per device
    
    Returns:
        List of card components
    """
    stats_cards = []
    for dev, st in data.get('stats', {}).items():
        stats_cards.append(dbc.Col(dbc.Card([
            dbc.CardBody([
                html.H4(dev.title(), className="device-stats-title", style={'color': DEVICE_COLORS.get(dev, '#333')}),
                html.Div(f"Samples: {st.get('samples', 'N/A'):,}", className="text-muted-dark"),
                html.Div(f"Duration: {st.get('duration', 'N/A')}", className="text-muted-dark"),
                html.Div(f"5s windows: {st.get('windows', 'N/A')}", className="text-muted-dark")
            ], className="device-stats-body")
        ], className="card shadow-sm h-100 device-stats-card", style={
            'borderLeft': f"4px solid {DEVICE_COLORS.get(dev, '#333')}"
            # borderRadius and boxShadow handled by CSS
        }), xs=12, sm=6, md=4, lg=3, className="mb-3"))
    
    return dbc.Row(stats_cards, className="g-3")


def create_cohort_table(df: pd.DataFrame) -> dash_table.DataTable:
    """
    Create cohort data table.
    
    Args:
        df: DataFrame with cohort data
    
    Returns:
        Dash DataTable component
    """
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in df.columns],
        sort_action='native',
        filter_action='native',
        page_size=20,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '10px'},
        style_header={'backgroundColor': COLORS['buttercup'], 'fontWeight': 'bold'},
        style_data_conditional=[
            {'if': {'column_id': 'Subject'}, 'fontWeight': 'bold'},
            {'if': {'row_index': 'odd'}, 'backgroundColor': COLORS['lily']}
        ]
    )


def create_correlation_layout(corr_df: pd.DataFrame, subjects: List[str], template: str = "plotly_white") -> html.Div:
    """
    Create the Correlations tab layout with beautiful LNU branding.
    """
    from ..backend.correlation import perform_subgroup_comparison
    from ..backend.data_quality import get_bad_subjects, get_quality_summary
    # Import locally to avoid circular imports
    from .visualizations import make_scatter_plot, make_time_series_overlay, make_correlation_bar_chart, make_subgroup_boxplot, make_gender_bar_chart
    
    # Get quality info
    quality_summary = get_quality_summary()
    bad_subjects = quality_summary.get('bad_subjects', [])
    
    # Overall Stats
    overall_r = 0.0
    n_subjects = 0
    min_r = 0.0
    max_r = 0.0
    if not corr_df.empty and 'Bangle_Actigraph' in corr_df.columns:
        overall_r = corr_df['Bangle_Actigraph'].mean()
        min_r = corr_df['Bangle_Actigraph'].min()
        max_r = corr_df['Bangle_Actigraph'].max()
        n_subjects = len(corr_df)
        
    # Demographic Stats (Gender)
    male_r = 0.0
    male_n = 0
    female_r = 0.0
    female_n = 0
    mw_test = {}
    
    if not corr_df.empty and 'Gender' in corr_df.columns and 'Bangle_Actigraph' in corr_df.columns:
        # Only include subjects with valid correlation data
        valid_df = corr_df.dropna(subset=['Bangle_Actigraph'])
        
        m_df = valid_df[valid_df['Gender'] == 'Male']
        if not m_df.empty:
            male_r = m_df['Bangle_Actigraph'].mean()
            male_n = len(m_df)
            
        f_df = valid_df[valid_df['Gender'] == 'Female']
        if not f_df.empty:
            female_r = f_df['Bangle_Actigraph'].mean()
            female_n = len(f_df)
            
        res = perform_subgroup_comparison(valid_df, 'Gender', 'Bangle_Actigraph')
        if 'p_value' in res:
            p_val = res['p_value']
            u_stat = res['u_stat']
            interp = "No significant difference between groups"
            if p_val < 0.05:
                interp = "Significant difference detected (p < 0.05)"
            mw_test = {'u_stat': u_stat, 'p_value': p_val, 'interpretation': interp}
    
    # Helper for quality badge color
    def get_quality_color(r_val):
        if r_val >= 0.7: return COLORS['ivy']  # Green = excellent
        elif r_val >= 0.5: return COLORS['buttercup']  # Yellow = acceptable
        else: return COLORS['azalea']  # Pink = needs attention
    
    return html.Div([
        # === Header Banner with Data Quality Toggle ===
        html.Div([
            html.Div([
                html.Div([
                    html.H3("Correlation Analysis", 
                           style={'margin': 0, 'fontWeight': '600', 'color': COLORS['soot']}),
                    html.P("Bangle.js vs Actigraph (Research-Grade Reference)", 
                          style={'margin': '5px 0 0 0', 'fontSize': '0.95rem', 'color': COLORS['soot']})
                ]),
                # Data Quality Banner Info
                html.Div([
                    html.Div([
                        html.Span(f"{quality_summary['good']} high-quality subjects", style={
                            'fontSize': '0.8rem', 'color': COLORS['ivy'], 'fontWeight': '600',
                        }),
                    ], style={'display': 'flex', 'alignItems': 'center'}),
                    html.Div([
                        html.Small(f"{quality_summary['bad']} excluded", 
                                  style={'color': '#666', 'fontSize': '0.75rem', 'marginRight': '5px'}),
                        html.I(className="bi bi-info-circle-fill", id="tooltip-quality-banner", 
                               style={"fontSize": "0.75rem", "color": "#999", "cursor": "pointer"}),
                        dbc.Tooltip(
                            (
                                f"Quality Filter: {', '.join(sorted([f'Participant {PARTICIPANT_MAPPING.get(str(s), s)}' for s in bad_subjects]))} are flagged for 'bad data' "
                                "(correlation r < 0.50 or flatlined sensor data ≤ 1.0g). "
                                f"Additionally, {', '.join(sorted([f'Participant {PARTICIPANT_MAPPING.get(str(s), s)}' for s in PARTICIPANT_MAPPING.keys() if str(s) not in bad_subjects and (corr_df.empty or str(s) not in corr_df['Subject'].astype(str).tolist())]))} "
                                "are excluded from this correlation analysis due to missing reference data."
                            ),
                            target="tooltip-quality-banner",
                            placement="top",
                            style={"maxWidth": "350px"}
                        )
                    ], style={'marginTop': '5px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-end'})
                ], style={'textAlign': 'right'})
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-start'})
        ], style={
            'background': f"linear-gradient(135deg, {COLORS['buttercup']} 0%, {COLORS['lily']} 100%)",
            'padding': '20px 25px',
            'borderRadius': '12px',
            'marginBottom': '25px',
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)'
        }),

        # === ROW 1: Overall Correlation (Prominent) ===
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Div([
                            html.Span("OVERALL CORRELATION", className="text-muted", style={
                                'fontSize': '0.75rem', 'fontWeight': '600',
                                'letterSpacing': '1px', 'marginBottom': '10px'
                            }),
                            html.I(className="bi bi-info-circle-fill ms-2", id="tooltip-overall-corr", style={"fontSize": "0.8rem", "color": "#ccc", "cursor": "pointer"}),
                            dbc.Tooltip(
                                "Pearson correlation coefficient (r). Measures linear relationship strength (-1 to 1).",
                                target="tooltip-overall-corr",
                                placement="top",
                            )
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}),
                        html.Div(id='overall-corr-value'),  # Dynamic content from callback
                        html.Div(id='overall-corr-info', className="text-muted", style={
                            'fontSize': '0.9rem', 'marginTop': '8px'
                        })
                    ], style={'textAlign': 'center'})
                ], className="card", style={
                    'padding': '25px 40px', 'borderRadius': '12px',
                    'boxShadow': 'var(--card-shadow)',
                    'borderTop': f'4px solid {get_quality_color(overall_r)}'
                })
            ], xs=12, md=12) # Full width on all screens for main stat
        ], className="mb-4"),

        # === ROW 2: Correlation by Participant (Full Width) ===
        html.Div([
            html.H5("Correlation by Participant", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}'
            }),
        ], style={'marginTop': '20px'}),
        
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Span("Sorted by correlation strength", className="text-muted", style={
                            'fontSize': '0.85rem'
                        })
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    dcc.Loading(dcc.Graph(figure=make_correlation_bar_chart(corr_df, template=template), id='corr-bar-chart', style={'height': f'{max(450, len(corr_df) * 32)}px'}, config={'responsive': True}))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'borderLeft': f'4px solid {COLORS["soot"]}'
                })
            ], xs=12, lg=12, className="mb-4"),
        ]),

        # === ROW 3: Gender Comparison ===
        html.Div([
            html.H5("Gender Comparison", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}'
            }),
        ], style={'marginTop': '20px'}),
        
        dbc.Row([
            # Left Column: Stats Cards (Stacked)
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Div("MALE", className="text-muted", style={
                            'fontSize': '0.7rem', 'fontWeight': '600',
                            'letterSpacing': '1px', 'marginBottom': '8px'
                        }),
                        html.Div(f"r = {male_r:.2f}", style={
                            'fontSize': '1.8rem', 'fontWeight': '600', 'color': COLORS['crocus']
                        }),
                        html.Div(f"n = {male_n}", style={
                            'fontSize': '0.85rem', 'marginTop': '5px'
                        })
                    ], className="card mb-3", style={
                        'padding': '15px', 'borderRadius': '10px',
                        'boxShadow': 'var(--card-shadow)',
                        'borderLeft': f'4px solid {COLORS["crocus"]}',
                        'flex': '1'
                    }),
                    html.Div([
                        html.Div("FEMALE", className="text-muted", style={
                            'fontSize': '0.7rem', 'fontWeight': '600',
                            'letterSpacing': '1px', 'marginBottom': '8px'
                        }),
                        html.Div(f"r = {female_r:.2f}", style={
                            'fontSize': '1.8rem', 'fontWeight': '600', 'color': COLORS['azalea']
                        }),
                        html.Div(f"n = {female_n}", style={
                            'fontSize': '0.85rem', 'marginTop': '5px'
                        })
                    ], className="card mb-3", style={
                        'padding': '15px', 'borderRadius': '10px',
                        'boxShadow': 'var(--card-shadow)',
                        'borderLeft': f'4px solid {COLORS["azalea"]}',
                        'flex': '1'
                    }),
                    html.Div([
                        html.Div([
                            html.Span("MANN-WHITNEY U TEST", className="text-muted", style={
                                'fontSize': '0.7rem', 'fontWeight': '600',
                                'letterSpacing': '1px', 'marginBottom': '8px'
                            }),
                            html.I(className="bi bi-info-circle-fill ms-2", id="tooltip-mw-test", style={"fontSize": "0.8rem", "color": "#ccc", "cursor": "pointer"}),
                            dbc.Tooltip(
                                "Non-parametric test to compare differences between two independent groups (Male vs Female).",
                                target="tooltip-mw-test",
                                placement="top",
                            )
                        ], style={'display': 'flex', 'alignItems': 'center'}),
                        html.Div(f"p = {format_p_value(mw_test.get('p_value', 1.0))}", style={
                            'fontSize': '1.6rem', 'fontWeight': '600', 
                            'color': COLORS['ivy'] if mw_test.get('p_value', 1) >= 0.05 else COLORS['azalea']
                        }),
                        html.Div(mw_test.get('interpretation', 'N/A'), className="text-muted", style={
                            'fontSize': '0.8rem', 'marginTop': '5px'
                        })
                    ], className="card", style={
                        'padding': '15px', 'borderRadius': '10px',
                        'boxShadow': 'var(--card-shadow)',
                        'borderLeft': f'4px solid {COLORS["soot"]}',
                        'flex': '1.2'
                    })
                ], style={'display': 'flex', 'flexDirection': 'column', 'justifyContent': 'space-between', 'height': '100%', 'minHeight': '380px'})
            ], xs=12, lg=4, className="mb-3"),
            
            # Middle Column: Gender Average Bar Chart
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Span("Average Correlation by Gender", className="text-muted", style={
                            'fontSize': '0.85rem'
                        })
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    dcc.Loading(dcc.Graph(figure=make_gender_bar_chart(corr_df, 'Gender', template=template), id='corr-gender-bar', style={'height': '380px'}, config={'responsive': True}))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'borderLeft': f'4px solid {COLORS["buttercup"]}'
                })
            ], xs=12, lg=4, className="mb-3"),
            
            # Right Column: Boxplot - Gender Distribution
            dbc.Col([
                html.Div([
                    html.Div([
                    html.Span("Gender Distribution", className="text-muted", style={
                            'fontSize': '0.85rem'
                        })
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    dcc.Loading(dcc.Graph(figure=make_subgroup_boxplot(corr_df, 'Gender', template=template), id='corr-boxplot', style={'height': '380px'}, config={'responsive': True}))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden'
                })
            ], xs=12, lg=4, className="mb-3"),
        ], className="mb-5 g-3"),

        # === Individual Participant Detail ===
        html.Div([
            html.H5("Individual Participant Analysis", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}'
            }),
        ], style={'marginTop': '20px'}),
        
        html.Div([
            # Header with dropdown
            html.Div([
                html.Div([
                    html.Label("Select Participant:", style={'marginRight': '10px', 'fontWeight': '500'}),
                    dcc.Dropdown(
                        id='corr-subject-dd',
                        options=[{'label': f"Participant {PARTICIPANT_MAPPING.get(str(s), s)}", 'value': s} for s in subjects],
                        value=subjects[0] if subjects else None,
                        clearable=False,
                        style={'width': '150px'}
                    )
                ], style={'display': 'flex', 'alignItems': 'center'})
            ], style={
                'padding': '15px 20px', 'borderBottom': '1px solid #eee'
            }),
            
            # Scatter and Time Series plots
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.P("Scatter Plot", style={
                            'textAlign': 'center', 'fontWeight': '500', 
                            'margin': '15px 0 0 0', 'fontSize': '0.9rem'
                        }),
                        dcc.Loading(dcc.Graph(id='corr-scatter-plot', style={'height': '320px'}, config={'responsive': True}))
                    ])
                ], xs=12, lg=12, className="mb-4"),
                dbc.Col([
                    html.Div([
                        html.P("Time Series Overlay", style={
                            'textAlign': 'center', 'fontWeight': '500', 
                            'margin': '15px 0 0 0', 'fontSize': '0.9rem'
                        }),
                        dcc.Loading(dcc.Graph(id='corr-time-plot', style={'height': '320px'}, config={'responsive': True}))
                    ])
                ], xs=12, lg=6),
            ], className="g-0")
        ], className="card", style={
            'borderRadius': '10px',
            'boxShadow': 'var(--card-shadow)',
            'overflow': 'hidden',
            'marginBottom': '20px'
        }),
        
        # === ROW 4: Calorimetry Energy Expenditure & Intensity (NEW) ===
        html.Div([
            html.Div([
                html.H5("Energy Expenditure & Intensity (Calorimetry Ground-Truth)", style={
                    'fontWeight': '600', 'marginBottom': '0',
                }),
                html.I(className="bi bi-info-circle-fill ms-2", id="tooltip-calorimetry", style={"fontSize": "0.9rem", "color": "#ccc", "cursor": "pointer"}),
                dbc.Tooltip(
                    "Displays actual Heart Rate and Metabolic Equivalent of Task (METs) measured via Indirect Calorimetry (e.g. Vyaire Medical oxygen consumption). The background shading indicates activity intensity zones defined as Light (<3 MET), Moderate (3-6 MET), and Vigorous (>6 MET).",
                    target="tooltip-calorimetry",
                    placement="top",
                    style={"maxWidth": "350px", "textAlign": "left"}
                )
            ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '15px', 'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}', 'marginTop': '30px'}),
        ]),
        
        html.Div([
            html.Div([
                html.Span("Timeline vs Intensity Classification", className="text-muted", style={
                    'fontSize': '0.85rem'
                })
            ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
            dcc.Loading(dcc.Graph(id='calorimetry-timeline-plot', style={'height': '400px'}, config={'responsive': True}))
        ], className="card", style={
            'borderRadius': '10px',
            'boxShadow': 'var(--card-shadow)',
            'overflow': 'hidden',
            'borderLeft': f'4px solid {COLORS["ivy"]}'
        }),
        
    ], style={'padding': '20px', 'minHeight': '100vh'})


def create_about_layout() -> html.Div:
    """
    Create the 'About' tab layout with project information.
    """
    return html.Div([
        # Header Section
        # Header Section
        html.Div([
            html.H3("Design of an Intelligent Wearable for Activity and Health – The DIWAH Study", 
                   style={'margin': 0, 'fontWeight': '600', 'color': COLORS['soot']}),
            html.P("Project Background, Methodology, and Goals.", 
                  style={'margin': '5px 0 0 0', 'fontSize': '0.95rem', 'color': COLORS['soot']})
        ], style={
            'background': f"linear-gradient(135deg, {COLORS['buttercup']} 0%, {COLORS['lily']} 100%)",
            'padding': '20px 25px',
            'borderRadius': '12px',
            'marginBottom': '25px',
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)'
        }),

        # Goal & Vision Section
        dbc.Card([
            dbc.CardHeader(html.H4("Why Are We Doing This?", className="m-0")),
            dbc.CardBody([
                html.P([
                    "The overarching goal of the DIWAH-study is to develop algorithms for wearables that can be used in healthcare to ",
                    html.Strong("promote health, prevent disease, and aid in treatment"),
                    ". Current healthcare faces a demographic shift with an aging population, making it crucial to have proactive strategies."
                ], className="card-text"),
                html.P([
                    "We are developing AI-based algorithms to assess ",
                    html.Strong("Physical Activity (PA), Energy Expenditure (EE), and Blood Pressure (BP)"),
                    " at an individual level. The ultimate vision is a system that provides tailored activity recommendations in real-time to optimize an individual's health without human intervention."
                ], className="card-text"),
            ])
        ], className="mb-4 shadow-sm dashboard-card"),

        # Background & Challenges Section (Restored)
        dbc.Row([
            dbc.Col([
                html.H4("The Challenge", className="mt-3 text-primary"),
                html.P([
                    "Globally, life expectancy is increasing. One major societal challenge is to develop strategies for maintaining good health and quality of life in older age groups. "
                    "Regular Physical Activity (PA) is key to preventing diseases like cardiovascular issues and diabetes."
                ]),
                dbc.Alert([
                    html.H5("Commercial Wearables Issue", className="alert-heading"),
                    html.P("Current commercial wearables often have large measurement errors (25-90% off for Energy Expenditure) and questionable data security. They rely on algorithms trained on young, healthy populations, making them inaccurate for older adults."),
                    html.Hr(),
                    html.P("Our approach uses open-source, transparent, and clinically validated algorithms.", className="mb-0")
                ], color="warning", className="mt-3")
            ], xs=12, className="mb-4"),
        ]),

        dbc.Row([
            # Left Column: Devices & Data
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("The Devices & Data", className="m-0")),
                    dbc.CardBody([
                        html.P("We are comparing open-source wearables against commercial standards and gold-standard methods:", className="card-text"),
                        html.Ul([
                            html.Li([html.Strong("Bangle.js 2 & Pinetime:"), " Open-source smartwatches allowing full access to raw sensor data."]),
                            html.Li([html.Strong("Emotibit:"), " A research-grade biosensor for physiological data."]),
                            html.Li([html.Strong("Fitbit Sense:"), " A commercial reference device."]),
                        ]),
                    ])
                ], className="h-100 shadow-sm dashboard-card")
            ], md=6, className="mb-4"),

            # Right Column: Why Rest vs Activity
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Why Rest vs. Activity?", className="m-0")),
                    dbc.CardBody([
                        html.P([
                            "A key challenge is distinguishing physiological responses during physical activity versus rest. ",
                            "By accurately classifying these states, we can ensure that health recommendations are context-aware and precise."
                        ], className="card-text"),
                        html.Ul([
                            html.Li([html.Strong("Rest (20 min):"), " Establishing baseline metrics and measuring Blood Pressure."]),
                            html.Li([html.Strong("Activity:"), " Performing specific tasks to measure Energy Expenditure and movement intensity."]),
                        ]),
                    ])
                ], className="h-100 shadow-sm dashboard-card")
            ], md=6, className="mb-4"),
        ]),

        # Methods & Phases (Restored Accordion)
        html.H4("Project Methodology & Phases", className="mt-4 text-primary"),
        dbc.Accordion([
            dbc.AccordionItem([
                html.P("Goal: Identify and test different wearables (Bangle.js 2, Pinetime, Emotibit, Fitbit Sense) to ensure raw data access."),
            ], title="Phase 1: Mechanical Signal Testing"),
            dbc.AccordionItem([
                html.P("Goal: Develop and test AI-based algorithms in a controlled laboratory environment with ~30 participants."),
                html.Ul([
                    html.Li("Bioimpedance measurements (Body Composition)"),
                    html.Li("Health-related physical fitness tests"),
                    html.Li("Blood pressure measurement after rest")
                ])
            ], title="Phase 2: Laboratory Testing"),
            dbc.AccordionItem([
                html.P("Goal: Test the prototype during free living with ~50 participants."),
                html.P("Validation: Using Doubly Labeled Water (DLW) as the gold standard for Energy Expenditure errors within ±2%."),
            ], title="Phase 3: Naturalistic Validation"),
        ], start_collapsed=True, className="mb-5"),

        # Project Team & Links
        dbc.Card([
            dbc.CardBody([
                html.H5("Who Are We?", className="card-title"),
                html.P([
                    "This is a collaborative seed project involving researchers from ",
                    html.A("LNU Centre for Data Intensive Sciences and Applications (DISA)", href="https://lnu.se/en/research/research-groups/linnaeus-university-centre-for-data-intensive-sciences-and-applications/seed-projects/seed-project-development-of-an-intelligent-wearable-the-diwah-study/", target="_blank"),
                    ", the eHealth Institute, and the Knowledge Environment Sustainable Health."
                ], className="card-text"),
                html.P("Our team combines expertise in Physical Activity research, AI modelling, IoT development, and Biochemistry to solve complex health challenges.", className="card-text"),
            ])
        ], className="mb-4 shadow-sm dashboard-card"),
        
    ], className="p-4")

