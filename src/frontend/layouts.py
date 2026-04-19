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


def create_kpi_card(title: str, value: str, subtext: str, color: str = "buttercup", tooltip_text: Optional[str] = None) -> dbc.Card:
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
        html.Div([
            html.I(className="bi bi-sliders me-2"),
            html.Span("Dashboard Controls", style={'fontWeight': '600', 'fontSize': '1.1rem'})
        ], className="controls-header mb-4", style={'color': 'var(--primary-color)', 'borderBottom': '2px solid var(--primary-color)', 'paddingBottom': '10px'}),
        
        html.Div([
            html.Label([
                html.I(className="bi bi-person-badge text-muted me-2"),
                "Active Participant"
            ], className="fw-bold mb-2 text-muted", style={'fontSize': '0.9rem', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
            dcc.Dropdown(
                id=f'{id_prefix}sub-dd',
                options=[{'label': f"Participant {PARTICIPANT_MAPPING.get(str(s), s)}", 'value': s} for s in subjects],
                value=subjects[0] if subjects else None,
                className="shadow-sm rounded-3 border-0",
                style={'color': '#212529'}
            ),
        ], className="mb-4"),
        
        html.Div([
            dbc.Switch(
                id=f'{id_prefix}exclude-bad-data-switch',
                value=False,
                style={'display': 'none'}
            ),
        ], style={'display': 'none'})
    ], className="card border-0 shadow-sm", style={'padding': '25px', 'borderRadius': '12px'})


def create_main_tabs() -> dbc.Tabs:
    """Create the main tab navigation component."""
    return dbc.Tabs([
        dbc.Tab(label='Time Series', tab_id='tab-timeseries'),
        dbc.Tab(label='Statistics', tab_id='tab-stats'),
        dbc.Tab(label='Correlations', tab_id='tab-corr'),
        dbc.Tab(label='Machine Learning', tab_id='tab-ml'),
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
    Create the 'About' tab layout driven by the README thesis context.
    """
    import dash
    return html.Div([
        # Header Section
        html.Div([
            html.H3("Predicting Exercise Intensity from Smartwatch Data: Device Capabilities and Limitations", 
                   style={'margin': 0, 'fontWeight': '600', 'color': COLORS['soot']}),
            html.P("A Bachelor's Thesis Project by Hanna Szalai & Yasmin Akoor.", 
                  style={'margin': '5px 0 0 0', 'fontSize': '1.05rem', 'color': COLORS['soot']}),
            html.P("In collaboration with the Linnaeus University DIWAH Study.", 
                  style={'margin': '5px 0 0 0', 'fontSize': '0.95rem', 'color': '#6c757d', 'fontStyle': 'italic'})
        ], style={
            'background': f"linear-gradient(135deg, {COLORS['buttercup']} 0%, {COLORS['lily']} 100%)",
            'padding': '20px 25px',
            'borderRadius': '12px',
            'marginBottom': '25px',
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)'
        }),

        # Overview & Challenge
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("The Research Context", className="m-0")),
                    dbc.CardBody([
                        html.P([
                            "Wearable sensors and machine learning are increasingly used to predict exercise energy expenditure to promote health, especially in the elderly. ",
                            "However, popular commercial wearables (like Fitbit or Apple Watch) are expensive, 'black box' systems that restrict access to raw sensor data."
                        ], className="card-text"),
                        html.P(
                            "This thesis investigates whether significantly cheaper, open-source consumer wearables can reliably predict exercise intensity using raw heart rate and accelerometer data.",
                            className="card-text fw-bold text-primary"
                        ),
                        html.P(
                            "By comparing models trained on open-source devices (EmotiBit, Bangle.js) against a research-grade clinical baseline (ActiGraph), we evaluate their predictive accuracy against a medical-grade Vyntus calorimetry systems (a breathing mask that tracks exact oxygen consumption).",
                            className="card-text text-muted"
                        )
                    ])
                ], className="h-100 shadow-sm dashboard-card")
            ], md=12, lg=7, className="mb-4"),

            # Research Questions
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Research Questions", className="m-0")),
                    dbc.CardBody([
                        html.P("This project aims to bridge the knowledge gap through two distinct research phases:", className="card-text"),
                        html.Ul([
                            html.Li([html.Strong("RQ1 (Design Science):"), " How can heterogeneous data streams from three different wearable devices with varying sampling rates, missing data, and clock drift be reliably synchronized and mathematically aligned for comparative analysis?"]),
                            html.Br(),
                            html.Li([html.Strong("RQ2 (Controlled Experiment):"), " Given properly synchronized heart rate and accelerometer data across heterogeneous wearables, is it feasible to predict exercise intensity (METs), and how does prediction performance vary by device architecture?"])
                        ]),
                    ])
                ], className="h-100 shadow-sm dashboard-card", style={'borderLeft': f'4px solid {COLORS["crocus"]}'})
            ], md=12, lg=5, className="mb-4"),
        ]),

        # Hardware & Alignment Visuals
        html.H4("Methodology & Visual Alignment", className="mt-3 mb-3 text-primary", style={'borderBottom': f'2px solid {COLORS["buttercup"]}', 'paddingBottom': '10px'}),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardImg(src=dash.get_asset_url('pictures/image.png'), top=True, style={'maxHeight': '300px', 'objectFit': 'contain', 'padding': '10px'}),
                    dbc.CardBody([
                        html.H5("The Hardware Suite", className="card-title"),
                        html.P("All the wearables and clinical devices worn by a subject during data collection. The data pipeline extracts hardware-specific features to assess their absolute predictive caps.", className="card-text text-muted")
                    ])
                ], className="h-100 shadow-sm dashboard-card")
            ], md=12, lg=5, className="mb-4"),

            dbc.Col([
                dbc.Card([
                    dbc.CardImg(src=dash.get_asset_url('pictures/alignment_shiny_app.png'), top=True, style={'maxHeight': '300px', 'objectFit': 'cover', 'objectPosition': 'top'}),
                    dbc.CardBody([
                        html.H5("Signal Synchronization", className="card-title"),
                        html.P([
                            "We utilized a custom ", 
                            html.Strong("Shiny App"), 
                            " to manually cut, align, and synchronize the raw data. The synchronized epochs created from this tool form the core dataset we ingest to calculate highly reliable cross-correlation markers (r > 0.90)."
                        ], className="card-text text-muted")
                    ])
                ], className="h-100 shadow-sm dashboard-card")
            ], md=12, lg=7, className="mb-4"),
        ]),

        # Steps/Milestones
        dbc.Card([
            dbc.CardHeader(html.H5("Steps, Milestones, and Actions", className="m-0")),
            dbc.CardBody([
                html.Ul([
                    html.Li([html.Strong("Data Integration Tools: "), "Develop parsing and mathematical alignment tools to synchronize the raw, un-synced data from the ActiGraph, EmotiBit, and Bangle.js."]),
                    html.Li([html.Strong("Database Setup: "), "Deploy an InfluxDB architecture specifically optimized for high-frequency time-series sensor storage."]),
                    html.Li([html.Strong("Dashboard Development: "), "Build a visual dashboard to manually validate the data alignment and inspect the heart rate and movement data prior to machine learning."]),
                    html.Li([html.Strong("Feature Extraction: "), "Use the open-source FLIRT Python package to extract standardized physiological features from 5-second data epochs."]),
                    html.Li([html.Strong("Model Training & Evaluation: "), "Train simple regression and basic ML models (e.g., Random Forest) on the extracted features, and compare their predicted MET values against the Vyntus golden standard."])
                ], className="mt-2 mb-0", style={'lineHeight': '1.8'})
            ])
        ], className="mb-5 shadow-sm dashboard-card", style={'borderLeft': f'4px solid {COLORS["ivy"]}'})

    ], className="p-4")

import plotly.graph_objects as go

def create_ml_layout() -> html.Div:
    """
    Renders the Machine Learning Dashboard evaluating Random Forest vs MLR.
    """
    metrics_data = {
        'ActiGraph (Clinical)': {'MLR_MAE': 4.308, 'MLR_R2': -1.228, 'MLR_RMSE': 5.749, 'RF_MAE': 2.066, 'RF_R2': 0.518, 'RF_RMSE': 2.673},
        'EmotiBit (Consumer)': {'MLR_MAE': 7.288, 'MLR_R2': -7.325, 'MLR_RMSE': 11.113, 'RF_MAE': 2.033, 'RF_R2': 0.627, 'RF_RMSE': 2.352},
        'Bangle.js (Consumer)': {'MLR_MAE': 23.183, 'MLR_R2': -25.000, 'MLR_RMSE': 57.201, 'RF_MAE': 1.995, 'RF_R2': 0.561, 'RF_RMSE': 2.513}
    }
    
    import json
    from pathlib import Path
    metrics_path = Path(__file__).resolve().parents[2] / "scripts" / "Acc_pipe" / "data" / "processed" / "ml_metrics.json"
    if metrics_path.exists():
        try:
            with open(metrics_path, 'r') as f:
                real_res = json.load(f)
            
            # Map the actual exported metrics back to our graph labels
            if 'actigraph' in real_res:
                metrics_data['ActiGraph (Clinical)'] = {
                    'MLR_MAE': real_res['actigraph']['MLR']['MAE'],
                    'MLR_R2': real_res['actigraph']['MLR']['R2'],
                    'MLR_RMSE': real_res['actigraph']['MLR']['RMSE'],
                    'RF_MAE': real_res['actigraph']['RF']['MAE'],
                    'RF_R2': real_res['actigraph']['RF']['R2'],
                    'RF_RMSE': real_res['actigraph']['RF']['RMSE']
                }
            if 'emotibit' in real_res:
                metrics_data['EmotiBit (Consumer)'] = {
                    'MLR_MAE': real_res['emotibit']['MLR']['MAE'],
                    'MLR_R2': real_res['emotibit']['MLR']['R2'],
                    'MLR_RMSE': real_res['emotibit']['MLR']['RMSE'],
                    'RF_MAE': real_res['emotibit']['RF']['MAE'],
                    'RF_R2': real_res['emotibit']['RF']['R2'],
                    'RF_RMSE': real_res['emotibit']['RF']['RMSE']
                }
            if 'bangle' in real_res:
                metrics_data['Bangle.js (Consumer)'] = {
                    'MLR_MAE': real_res['bangle']['MLR']['MAE'],
                    'MLR_R2': real_res['bangle']['MLR']['R2'],
                    'MLR_RMSE': real_res['bangle']['MLR']['RMSE'],
                    'RF_MAE': real_res['bangle']['RF']['MAE'],
                    'RF_R2': real_res['bangle']['RF']['R2'],
                    'RF_RMSE': real_res['bangle']['RF']['RMSE']
                }
        except Exception as e:
            print(f"Error loading real ML metrics: {e}")

    devices = list(metrics_data.keys())
    
    # Extract data for plotting
    mlr_mae = [metrics_data[d]['MLR_MAE'] for d in devices]
    rf_mae = [metrics_data[d]['RF_MAE'] for d in devices]
    
    mlr_rmse = [metrics_data[d]['MLR_RMSE'] for d in devices]
    rf_rmse = [metrics_data[d]['RF_RMSE'] for d in devices]

    # --- CHART 1: Mean Absolute Error (MAE) ---
    fig_mae = go.Figure()
    fig_mae.add_trace(go.Bar(
        x=devices, y=mlr_mae,
        name='Linear Regression',
        marker_color=COLORS['crocus'],
        text=[f"{val:.2f}" for val in mlr_mae],
        textposition='outside',
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>MLR MAE: %{y:.3f} METs<extra></extra>"
    ))
    fig_mae.add_trace(go.Bar(
        x=devices, y=rf_mae,
        name='Random Forest',
        marker_color=COLORS['buttercup'],
        text=[f"{val:.2f}" for val in rf_mae],
        textposition='outside',
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Random Forest MAE: %{y:.3f} METs<extra></extra>"
    ))
    
    fig_mae.update_layout(
        yaxis_title="Mean Absolute Error (METs)",
        barmode='group',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#888'),
        legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5),
        margin=dict(t=45, b=100, l=40, r=20),
        yaxis=dict(gridcolor='rgba(150,150,150,0.1)'),
        hovermode="x unified"
    )

    # --- CHART 2: Root Mean Squared Error (RMSE) ---
    fig_rmse = go.Figure()
    fig_rmse.add_trace(go.Bar(
        x=devices, y=mlr_rmse,
        name='Linear Regression',
        marker_color=COLORS['crocus'],
        text=[f"{val:.2f}" for val in mlr_rmse],
        textposition='outside',
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>MLR RMSE: %{y:.3f} METs<extra></extra>"
    ))
    fig_rmse.add_trace(go.Bar(
        x=devices, y=rf_rmse,
        name='Random Forest',
        marker_color=COLORS['buttercup'],
        text=[f"{val:.2f}" for val in rf_rmse],
        textposition='outside',
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Random Forest RMSE: %{y:.3f} METs<extra></extra>"
    ))
    fig_rmse.update_layout(
        yaxis_title="Root Mean Squared Error (METs)",
        barmode='group',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#888'),
        legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5),
        margin=dict(t=45, b=100, l=40, r=20),
        yaxis=dict(gridcolor='rgba(150,150,150,0.1)'),
        hovermode="x unified"
    )

    return html.Div([
        # === Header Banner ===
        html.Div([
            html.Div([
                html.H3("Machine Learning Evaluation", 
                       style={'margin': 0, 'fontWeight': '600', 'color': COLORS['soot']}),
                html.P("Predicting Energy Expenditure (METs) using ActiGraph vs. Consumer Wearables", 
                      style={'margin': '5px 0 0 0', 'fontSize': '0.95rem', 'color': COLORS['soot']})
            ])
        ], style={
            'background': f"linear-gradient(135deg, {COLORS['buttercup']} 0%, {COLORS['lily']} 100%)",
            'padding': '20px 25px',
            'borderRadius': '12px',
            'marginBottom': '25px',
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)'
        }),
        
        # Methodological Explanation
        html.Div([
            html.P(
                "Random Forest algorithms successfully map non-linear biological movement artifacts, "
                "reducing the Mean Absolute Error to ~2 METs across both clinical and consumer devices.",
                className="text-muted",
                style={'fontSize': '1.05rem', 'marginBottom': '25px'}
            )
        ]),
        
        # === ROW 1: MAE and RMSE Metrics Side by Side ===
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Span("Mean Absolute Error (MAE in METs)", className="text-muted", style={'fontSize': '0.85rem'})
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    dcc.Loading(dcc.Graph(figure=fig_mae, config={'displayModeBar': False}, style={'height': '400px'}, responsive=True))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'borderLeft': f'4px solid {COLORS["buttercup"]}'
                })
            ], xs=12, lg=6, className="mb-4"),
            
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Span("Root Mean Squared Error (RMSE in METs)", className="text-muted", style={'fontSize': '0.85rem'})
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    dcc.Loading(dcc.Graph(figure=fig_rmse, config={'displayModeBar': False}, style={'height': '400px'}, responsive=True))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'borderLeft': f'4px solid {COLORS["crocus"]}'
                })
            ], xs=12, lg=6, className="mb-4")
        ]),
        
        # === ROW 3: Interactive Scatter Plot Section ===
        html.Div([
            html.H5("True vs. Predicted Exercise Intensity (METs)", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}'
            }),
        ], style={'marginTop': '20px'}),
        
        dbc.Row([
            dbc.Col([
                html.Div([
                    # Controls Head
                    html.Div([
                        html.Span("Interactive Model Prediction Filter", className="text-muted", style={'fontSize': '0.85rem'})
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    # Dropdowns container
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.Label("Select Device:", className="fw-bold mb-1 text-muted", style={'fontSize': '0.85rem'}),
                                dcc.Dropdown(
                                    id="ml-device-dd",
                                    options=[
                                        {"label": "ActiGraph", "value": "ActiGraph"},
                                        {"label": "EmotiBit", "value": "EmotiBit"},
                                        {"label": "Bangle.js", "value": "Bangle.js"}
                                    ],
                                    value="EmotiBit",
                                    clearable=False,
                                    className="mb-1",
                                    style={'color': '#212529'}
                                )
                            ], md=6, className="mb-3 mb-md-0"),
                            
                            dbc.Col([
                                html.Label("Select Model:", className="fw-bold mb-1 text-muted", style={'fontSize': '0.85rem'}),
                                dcc.Dropdown(
                                    id="ml-model-dd",
                                    options=[
                                        {"label": "Multiple Linear Regression", "value": "Multiple Linear Regression"},
                                        {"label": "Random Forest", "value": "Random Forest"}
                                    ],
                                    value="Random Forest",
                                    clearable=False,
                                    className="mb-1",
                                    style={'color': '#212529'}
                                )
                            ], md=6)
                        ])
                    ], style={'padding': '20px'})
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'visible', # Allow dropdowns to overflow standard blocks safely
                    'borderLeft': f'4px solid {COLORS["soot"]}'
                })
            ], xs=12, lg=12, className="mb-4")
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Loading(dcc.Graph(id="ml-scatter-plot", config={"displayModeBar": False}, style={'height': '450px'}))
                ), className="border-0 shadow-sm mb-4 bg-transparent")
            ], xs=12, lg=12),
            
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Loading(dcc.Graph(id="ml-line-plot", config={"displayModeBar": False}, style={'height': '450px'}))
                ), className="border-0 shadow-sm mb-4 bg-transparent")
            ], xs=12, lg=12)
        ], className="mb-5")
    ])
