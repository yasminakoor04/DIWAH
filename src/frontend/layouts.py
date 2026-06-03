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
        dbc.Tab(label='Bangle Correlation', tab_id='tab-corr'),
        dbc.Tab(label='EmotiBit Correlation', tab_id='tab-corr-emotibit'),
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
        valid_bangle = corr_df['Bangle_Actigraph'].dropna()
        overall_r = valid_bangle.mean() if len(valid_bangle) > 0 else 0.0
        min_r = valid_bangle.min() if len(valid_bangle) > 0 else 0.0
        max_r = valid_bangle.max() if len(valid_bangle) > 0 else 0.0
        n_subjects = len(valid_bangle)
        
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
                        html.Span(f"{n_subjects} high-quality subjects", style={
                            'fontSize': '0.8rem', 'color': COLORS['ivy'], 'fontWeight': '600',
                        }),
                    ], style={'display': 'flex', 'alignItems': 'center'}),
                    html.Div([
                        html.Small(f"{30 - n_subjects} excluded", 
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

        # === Cohort Aggregated Scatter ===
        html.Div([
            html.H5("Cohort Aggregated Scatter Plot", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}'
            }),
        ], style={'marginTop': '20px'}),

        dbc.Row([
            dbc.Col([
                html.Div([
                    html.P("Overall Correlation - Bangle.js vs. Actigraph", style={
                        'textAlign': 'center', 'fontWeight': '500', 
                        'margin': '15px 0 0 0', 'fontSize': '0.9rem'
                    }),
                    dcc.Loading(dcc.Graph(id='corr-cohort-scatter', style={'height': '400px'}, config={'responsive': True}))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'marginBottom': '20px'
                })
            ], xs=12)
        ]),

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


def create_emotibit_correlation_layout(corr_df: pd.DataFrame, subjects: List[str], template: str = "plotly_white") -> html.Div:
    """
    Create the EmotiBit Correlations tab layout — EmotiBit vs Actigraph.
    Mirrors the Bangle correlation page structure with EmotiBit-specific data.
    """
    from ..backend.correlation import perform_subgroup_comparison
    from ..backend.data_quality import get_bad_subjects, get_quality_summary
    from .visualizations import make_scatter_plot, make_time_series_overlay, make_correlation_bar_chart, make_subgroup_boxplot, make_gender_bar_chart

    quality_summary = get_quality_summary()
    bad_subjects = quality_summary.get('bad_subjects', [])

    # Overall Stats for EmotiBit
    overall_r = 0.0
    n_subjects = 0
    min_r = 0.0
    max_r = 0.0
    metric = 'EmotiBit_Actigraph'
    if not corr_df.empty and metric in corr_df.columns:
        valid = corr_df[metric].dropna()
        overall_r = valid.mean() if len(valid) > 0 else 0.0
        min_r = valid.min() if len(valid) > 0 else 0.0
        max_r = valid.max() if len(valid) > 0 else 0.0
        n_subjects = len(valid)

    # Demographic Stats (Gender)
    male_r = 0.0
    male_n = 0
    female_r = 0.0
    female_n = 0
    mw_test = {}

    if not corr_df.empty and 'Gender' in corr_df.columns and metric in corr_df.columns:
        valid_df = corr_df.dropna(subset=[metric])

        m_df = valid_df[valid_df['Gender'] == 'Male']
        if not m_df.empty:
            male_r = m_df[metric].mean()
            male_n = len(m_df)

        f_df = valid_df[valid_df['Gender'] == 'Female']
        if not f_df.empty:
            female_r = f_df[metric].mean()
            female_n = len(f_df)

        res = perform_subgroup_comparison(valid_df, 'Gender', metric)
        if 'p_value' in res:
            p_val = res['p_value']
            u_stat = res['u_stat']
            interp = "No significant difference between groups"
            if p_val < 0.05:
                interp = "Significant difference detected (p < 0.05)"
            mw_test = {'u_stat': u_stat, 'p_value': p_val, 'interpretation': interp}

    def get_quality_color(r_val):
        if r_val >= 0.7: return COLORS['ivy']
        elif r_val >= 0.5: return COLORS['buttercup']
        else: return COLORS['azalea']

    return html.Div([
        # === Header Banner ===
        html.Div([
            html.Div([
                html.Div([
                    html.H3("Correlation Analysis",
                           style={'margin': 0, 'fontWeight': '600', 'color': COLORS['soot']}),
                    html.P("EmotiBit vs Actigraph (Research-Grade Reference)",
                          style={'margin': '5px 0 0 0', 'fontSize': '0.95rem', 'color': COLORS['soot']})
                ]),
                html.Div([
                    html.Div([
                        html.Span(f"{n_subjects} high-quality subjects", style={
                            'fontSize': '0.8rem', 'color': COLORS['ivy'], 'fontWeight': '600',
                        }),
                    ], style={'display': 'flex', 'alignItems': 'center'}),
                    html.Div([
                        html.Small(f"{30 - n_subjects} excluded",
                                  style={'color': '#666', 'fontSize': '0.75rem', 'marginRight': '5px'}),
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

        # === ROW 1: Overall Correlation ===
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Div([
                            html.Span("OVERALL CORRELATION", className="text-muted", style={
                                'fontSize': '0.75rem', 'fontWeight': '600',
                                'letterSpacing': '1px', 'marginBottom': '10px'
                            }),
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}),
                        html.Div(id='emo-overall-corr-value'),
                        html.Div(id='emo-overall-corr-info', className="text-muted", style={
                            'fontSize': '0.9rem', 'marginTop': '8px'
                        })
                    ], style={'textAlign': 'center'})
                ], className="card", style={
                    'padding': '25px 40px', 'borderRadius': '12px',
                    'boxShadow': 'var(--card-shadow)',
                    'borderTop': f'4px solid {get_quality_color(overall_r)}'
                })
            ], xs=12, md=12)
        ], className="mb-4"),

        # === ROW 2: Correlation by Participant ===
        html.Div([
            html.H5("Correlation by Participant", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["crocus"]}'
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
                    dcc.Loading(dcc.Graph(
                        figure=make_correlation_bar_chart(corr_df, metric=metric, template=template),
                        id='emo-corr-bar-chart',
                        style={'height': f'{max(450, len(corr_df) * 32)}px'},
                        config={'responsive': True}
                    ))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'borderLeft': f'4px solid {COLORS["crocus"]}'
                })
            ], xs=12, lg=12, className="mb-4"),
        ]),

        # === ROW 3: Gender Comparison ===
        html.Div([
            html.H5("Gender Comparison", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["crocus"]}'
            }),
        ], style={'marginTop': '20px'}),

        dbc.Row([
            # Left Column: Stats Cards
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
                    dcc.Loading(dcc.Graph(
                        figure=make_gender_bar_chart(corr_df, 'Gender', metric=metric, template=template),
                        id='emo-corr-gender-bar',
                        style={'height': '380px'},
                        config={'responsive': True}
                    ))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'borderLeft': f'4px solid {COLORS["buttercup"]}'
                })
            ], xs=12, lg=4, className="mb-3"),

            # Right Column: Boxplot
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Span("Gender Distribution", className="text-muted", style={
                            'fontSize': '0.85rem'
                        })
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    dcc.Loading(dcc.Graph(
                        figure=make_subgroup_boxplot(corr_df, 'Gender', metric=metric, template=template),
                        id='emo-corr-boxplot',
                        style={'height': '380px'},
                        config={'responsive': True}
                    ))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden'
                })
            ], xs=12, lg=4, className="mb-3"),
        ], className="mb-5 g-3"),

        # === Cohort Aggregated Scatter ===
        html.Div([
            html.H5("Cohort Aggregated Scatter Plot", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["crocus"]}'
            }),
        ], style={'marginTop': '20px'}),

        dbc.Row([
            dbc.Col([
                html.Div([
                    html.P("Overall Correlation - EmotiBit vs. Actigraph", style={
                        'textAlign': 'center', 'fontWeight': '500', 
                        'margin': '15px 0 0 0', 'fontSize': '0.9rem'
                    }),
                    dcc.Loading(dcc.Graph(id='emo-corr-cohort-scatter', style={'height': '400px'}, config={'responsive': True}))
                ], className="card", style={
                    'borderRadius': '10px',
                    'boxShadow': 'var(--card-shadow)',
                    'overflow': 'hidden',
                    'marginBottom': '20px'
                })
            ], xs=12)
        ]),

        # === Individual Participant Detail ===
        html.Div([
            html.H5("Individual Participant Analysis", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["crocus"]}'
            }),
        ], style={'marginTop': '20px'}),

        html.Div([
            html.Div([
                html.Div([
                    html.Label("Select Participant:", style={'marginRight': '10px', 'fontWeight': '500'}),
                    dcc.Dropdown(
                        id='emo-corr-subject-dd',
                        options=[{'label': f"Participant {PARTICIPANT_MAPPING.get(str(s), s)}", 'value': s} for s in subjects],
                        value=subjects[0] if subjects else None,
                        clearable=False,
                        style={'width': '150px'}
                    )
                ], style={'display': 'flex', 'alignItems': 'center'})
            ], style={
                'padding': '15px 20px', 'borderBottom': '1px solid #eee'
            }),

            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.P("Scatter Plot — EmotiBit vs Actigraph", style={
                            'textAlign': 'center', 'fontWeight': '500',
                            'margin': '15px 0 0 0', 'fontSize': '0.9rem'
                        }),
                        dcc.Loading(dcc.Graph(id='emo-corr-scatter-plot', style={'height': '320px'}, config={'responsive': True}))
                    ])
                ], xs=12, lg=12, className="mb-4"),
                dbc.Col([
                    html.Div([
                        html.P("Time Series Overlay", style={
                            'textAlign': 'center', 'fontWeight': '500',
                            'margin': '15px 0 0 0', 'fontSize': '0.9rem'
                        }),
                        dcc.Loading(dcc.Graph(id='emo-corr-time-plot', style={'height': '320px'}, config={'responsive': True}))
                    ])
                ], xs=12, lg=6),
            ], className="g-0")
        ], className="card", style={
            'borderRadius': '10px',
            'boxShadow': 'var(--card-shadow)',
            'overflow': 'hidden',
            'marginBottom': '20px'
        }),

    ], style={'padding': '20px', 'minHeight': '100vh'})


def create_about_layout() -> html.Div:
    """
    Create the 'About' tab layout — a visually appealing introduction
    to the DIWAH thesis project and research context.
    """
    import dash

    # --- Shared style fragments ---
    _pill_style = {
        'display': 'inline-block', 'padding': '4px 14px',
        'borderRadius': '20px', 'fontSize': '0.75rem',
        'fontWeight': '700', 'letterSpacing': '0.5px',
        'marginRight': '8px', 'marginBottom': '6px',
    }

    def _device_card(name, subtitle, accent, desc, badge_text):
        """Build a single device showcase card."""
        return html.Div([
            # Top accent bar
            html.Div(style={
                'height': '4px',
                'background': f'linear-gradient(90deg, {accent}, {accent}88)',
                'borderRadius': '12px 12px 0 0',
            }),
            html.Div([
                # Accent dot + Title row
                html.Div([
                    html.Div(style={
                        'width': '10px', 'height': '10px', 'borderRadius': '50%',
                        'background': accent, 'flexShrink': '0',
                        'marginRight': '12px', 'marginTop': '2px',
                    }),
                    html.Div([
                        html.H5(name, style={
                            'margin': 0, 'fontWeight': '700',
                            'color': 'var(--text-primary)',
                        }),
                        html.Span(subtitle, style={
                            'fontSize': '0.8rem', 'color': 'var(--text-secondary)',
                        }),
                    ]),
                ], style={'display': 'flex', 'alignItems': 'flex-start', 'marginBottom': '14px'}),
                # Description
                html.P(desc, style={
                    'fontSize': '0.88rem', 'color': 'var(--text-secondary)',
                    'lineHeight': '1.55', 'margin': '0 0 14px 0',
                }),
                # Badge
                html.Span(badge_text, style={
                    **_pill_style,
                    'background': f'{accent}18', 'color': accent,
                    'border': f'1px solid {accent}44',
                }),
            ], style={'padding': '20px 22px 18px'}),
        ], className="card", style={
            'borderRadius': '12px', 'overflow': 'hidden',
            'boxShadow': 'var(--card-shadow)',
            'transition': 'transform 0.2s ease, box-shadow 0.2s ease',
            'height': '100%',
        })

    def _pipeline_step(number, title, subtitle, accent):
        """Build a single pipeline step block."""
        return html.Div([
            html.Div([
                html.Div(str(number), style={
                    'width': '36px', 'height': '36px', 'borderRadius': '50%',
                    'background': f'linear-gradient(135deg, {accent}, {accent}cc)',
                    'color': '#fff', 'display': 'flex',
                    'alignItems': 'center', 'justifyContent': 'center',
                    'fontWeight': '800', 'fontSize': '0.95rem',
                    'flexShrink': '0',
                }),
                html.Div([
                    html.Span(title, style={
                        'fontWeight': '700', 'fontSize': '0.92rem',
                        'color': 'var(--text-primary)',
                    }),
                    html.Br(),
                    html.Span(subtitle, style={
                        'fontSize': '0.78rem', 'color': 'var(--text-secondary)',
                    }),
                ], style={'marginLeft': '14px'}),
            ], style={'display': 'flex', 'alignItems': 'center'}),
        ], style={
            'padding': '16px 18px', 'borderRadius': '10px',
            'background': 'var(--bg-secondary)',
            'boxShadow': 'var(--card-shadow)',
            'marginBottom': '10px',
            'borderLeft': f'3px solid {accent}',
        })

    return html.Div([

        # ========================================================
        # HERO SECTION
        # ========================================================
        html.Div([
            html.Div([
                # Left: text content
                html.Div([
                    html.Div([
                        html.Span("BACHELOR'S THESIS", style={
                            **_pill_style,
                            'background': 'rgba(255,255,255,0.35)',
                            'color': COLORS['soot'], 'marginBottom': '16px',
                        }),
                        html.Span("LINNAEUS UNIVERSITY", style={
                            **_pill_style,
                            'background': 'rgba(255,255,255,0.35)',
                            'color': COLORS['soot'], 'marginBottom': '16px',
                        }),
                    ]),
                    html.H2("Predicting Exercise Intensity from Smartwatch Data", style={
                        'fontWeight': '800', 'color': COLORS['soot'],
                        'marginBottom': '6px', 'lineHeight': '1.25',
                        'fontSize': '1.8rem',
                    }),
                    html.P("Device Capabilities & Limitations", style={
                        'fontSize': '1.1rem', 'color': COLORS['soot'],
                        'fontWeight': '500', 'marginBottom': '18px',
                        'opacity': '0.75',
                    }),
                    html.P([
                        "By ", html.Strong("Hanna Szalai"),
                        " & ", html.Strong("Yasmin Akoor"),
                    ], style={
                        'fontSize': '0.95rem', 'color': COLORS['soot'],
                        'marginBottom': '4px',
                    }),
                    html.P([
                        "In collaboration with the ",
                        html.A("DIWAH Study", href="https://lnu.se/en/research/research-groups/linnaeus-university-centre-for-data-intensive-sciences-and-applications/seed-projects/seed-project-development-of-an-intelligent-wearable-the-diwah-study/",
                               target="_blank", style={
                                   'color': COLORS['soot'], 'fontWeight': '600',
                                   'textDecoration': 'underline',
                               }),
                        " — led by Patrick Bergman",
                    ], style={
                        'fontSize': '0.85rem', 'color': COLORS['soot'],
                        'opacity': '0.7', 'fontStyle': 'italic',
                    }),
                ], style={'maxWidth': '600px'}),

                # Right: quick-stat pills
                html.Div([
                    html.Div([
                        html.Div("30", style={
                            'fontSize': '2.2rem', 'fontWeight': '800',
                            'color': COLORS['soot'], 'lineHeight': '1',
                        }),
                        html.Div("Participants", style={
                            'fontSize': '0.78rem', 'color': COLORS['soot'],
                            'opacity': '0.7', 'fontWeight': '600',
                        }),
                    ], style={
                        'background': 'rgba(255,255,255,0.4)',
                        'borderRadius': '12px', 'padding': '16px 22px',
                        'textAlign': 'center', 'minWidth': '100px',
                    }),
                    html.Div([
                        html.Div("4", style={
                            'fontSize': '2.2rem', 'fontWeight': '800',
                            'color': COLORS['soot'], 'lineHeight': '1',
                        }),
                        html.Div("Devices", style={
                            'fontSize': '0.78rem', 'color': COLORS['soot'],
                            'opacity': '0.7', 'fontWeight': '600',
                        }),
                    ], style={
                        'background': 'rgba(255,255,255,0.4)',
                        'borderRadius': '12px', 'padding': '16px 22px',
                        'textAlign': 'center', 'minWidth': '100px',
                    }),
                    html.Div([
                        html.Div("3", style={
                            'fontSize': '2.2rem', 'fontWeight': '800',
                            'color': COLORS['soot'], 'lineHeight': '1',
                        }),
                        html.Div("Sensors", style={
                            'fontSize': '0.78rem', 'color': COLORS['soot'],
                            'opacity': '0.7', 'fontWeight': '600',
                        }),
                    ], style={
                        'background': 'rgba(255,255,255,0.4)',
                        'borderRadius': '12px', 'padding': '16px 22px',
                        'textAlign': 'center', 'minWidth': '100px',
                    }),
                ], style={
                    'display': 'flex', 'gap': '12px',
                    'flexWrap': 'wrap', 'justifyContent': 'flex-end',
                    'alignItems': 'flex-start',
                }),
            ], style={
                'display': 'flex', 'justifyContent': 'space-between',
                'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '20px',
            }),
        ], style={
            'background': f'linear-gradient(135deg, {COLORS["buttercup"]} 0%, {COLORS["lily"]} 60%, #fff8dc 100%)',
            'padding': '36px 32px',
            'borderRadius': '16px',
            'marginBottom': '30px',
            'boxShadow': '0 4px 20px rgba(0,0,0,0.08)',
            'position': 'relative',
            'overflow': 'hidden',
        }),

        # ========================================================
        # THE CORE QUESTION
        # ========================================================
        html.Div([
            html.Div([
                html.Div([
                    html.Span("The Core Question", style={
                        'fontWeight': '700', 'fontSize': '1rem',
                        'color': 'var(--text-primary)',
                    }),
                    html.P([
                        "Can ",
                        html.Span("affordable, open-source wearables", style={
                            'fontWeight': '700', 'color': COLORS['ivy'],
                        }),
                        " predict exercise intensity as accurately as ",
                        html.Span("expensive, research-grade devices", style={
                            'fontWeight': '700', 'color': COLORS['crocus'],
                        }),
                        "? We compare predictions from each wearable against the ",
                        html.Strong("Vyntus calorimetry system"),
                        " — the clinical gold standard for energy expenditure measurement.",
                    ], style={
                        'margin': '6px 0 0 0', 'fontSize': '0.92rem',
                        'color': 'var(--text-secondary)', 'lineHeight': '1.6',
                    }),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-start'}),
        ], className="card", style={
            'padding': '22px 26px', 'borderRadius': '12px',
            'boxShadow': 'var(--card-shadow)', 'marginBottom': '30px',
            'borderLeft': f'4px solid {COLORS["buttercup"]}',
        }),

        # ========================================================
        # DEVICE SHOWCASE
        # ========================================================
        html.Div([
            html.H4("The Devices", style={
                'fontWeight': '700', 'marginBottom': '4px',
                'color': 'var(--text-primary)',
            }),
            html.P("Four devices worn simultaneously during each exercise session, from consumer to clinical grade.", style={
                'fontSize': '0.9rem', 'color': 'var(--text-secondary)',
                'marginBottom': '20px',
            }),
        ]),

        dbc.Row([
            dbc.Col([
                _device_card(
                    "Bangle.js 2", "Open-source smartwatch",
                    COLORS['ivy'],
                    "A hackable, community-driven JavaScript smartwatch providing full access to raw heart rate and accelerometer streams at ~12.5 Hz.",
                    "Fully Open-Source · ~€30",
                )
            ], xs=12, sm=6, lg=3, className="mb-3"),
            dbc.Col([
                _device_card(
                    "EmotiBit", "Open biosensor platform",
                    COLORS['azalea'],
                    "Research-ready biometric sensor capturing PPG, EDA, and temperature with timestamped data export for reproducible experiments.",
                    "Open-Source · ~€300",
                )
            ], xs=12, sm=6, lg=3, className="mb-3"),
            dbc.Col([
                _device_card(
                    "ActiGraph", "Research-grade accelerometer",
                    COLORS['crocus'],
                    "The industry-standard accelerometer used in clinical studies worldwide, providing our research-grade reference baseline.",
                    "Proprietary SDK · ~€500",
                )
            ], xs=12, sm=6, lg=3, className="mb-3"),
            dbc.Col([
                _device_card(
                    "Vyntus CPX", "Clinical calorimetry",
                    COLORS['buttercup'],
                    "Medical-grade indirect calorimetry via a breathing mask that measures exact oxygen consumption — the gold standard for MET values.",
                    "Gold Standard · Medical",
                )
            ], xs=12, sm=6, lg=3, className="mb-3"),
        ], className="mb-4"),

        # ========================================================
        # RESEARCH QUESTIONS
        # ========================================================
        html.Div([
            html.H4("Research Questions", style={
                'fontWeight': '700', 'marginBottom': '4px',
                'color': 'var(--text-primary)',
            }),
            html.P("Two distinct challenges — one in data engineering, one in prediction.", style={
                'fontSize': '0.9rem', 'color': 'var(--text-secondary)',
                'marginBottom': '20px',
            }),
        ]),

        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div(style={
                        'height': '4px',
                        'background': f'linear-gradient(90deg, {COLORS["crocus"]}, {COLORS["crocus"]}88)',
                        'borderRadius': '12px 12px 0 0',
                    }),
                    html.Div([
                        html.Div([
                            html.Span("RQ1", style={
                                **_pill_style,
                                'background': f'{COLORS["crocus"]}18',
                                'color': COLORS['crocus'],
                                'border': f'1px solid {COLORS["crocus"]}44',
                            }),
                            html.Span("Design Science", style={
                                'fontSize': '0.78rem', 'color': 'var(--text-secondary)',
                                'fontWeight': '600',
                            }),
                        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px', 'marginBottom': '12px'}),
                        html.H5("Data Synchronization", style={
                            'fontWeight': '700', 'marginBottom': '10px',
                            'color': 'var(--text-primary)',
                        }),
                        html.P(
                            "How can heterogeneous data streams from three different wearable devices be reliably synchronized and mathematically aligned for comparative analysis?",
                            style={
                                'fontSize': '0.88rem', 'color': 'var(--text-secondary)',
                                'lineHeight': '1.6', 'margin': 0,
                            },
                        ),
                    ], style={'padding': '22px 24px'}),
                ], className="card", style={
                    'borderRadius': '12px', 'overflow': 'hidden',
                    'boxShadow': 'var(--card-shadow)', 'height': '100%',
                }),
            ], xs=12, lg=6, className="mb-3"),

            dbc.Col([
                html.Div([
                    html.Div(style={
                        'height': '4px',
                        'background': f'linear-gradient(90deg, {COLORS["ivy"]}, {COLORS["ivy"]}88)',
                        'borderRadius': '12px 12px 0 0',
                    }),
                    html.Div([
                        html.Div([
                            html.Span("RQ2", style={
                                **_pill_style,
                                'background': f'{COLORS["ivy"]}18',
                                'color': COLORS['ivy'],
                                'border': f'1px solid {COLORS["ivy"]}44',
                            }),
                            html.Span("Controlled Experiment", style={
                                'fontSize': '0.78rem', 'color': 'var(--text-secondary)',
                                'fontWeight': '600',
                            }),
                        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px', 'marginBottom': '12px'}),
                        html.H5("Intensity Prediction", style={
                            'fontWeight': '700', 'marginBottom': '10px',
                            'color': 'var(--text-primary)',
                        }),
                        html.P(
                            "Given properly synchronized heart rate and accelerometer data across heterogeneous wearables, is it feasible to predict exercise intensity (METs), and how does prediction performance vary by device architecture?",
                            style={
                                'fontSize': '0.88rem', 'color': 'var(--text-secondary)',
                                'lineHeight': '1.6', 'margin': 0,
                            },
                        ),
                    ], style={'padding': '22px 24px'}),
                ], className="card", style={
                    'borderRadius': '12px', 'overflow': 'hidden',
                    'boxShadow': 'var(--card-shadow)', 'height': '100%',
                }),
            ], xs=12, lg=6, className="mb-3"),
        ], className="mb-4"),

        # ========================================================
        # DATA PIPELINE
        # ========================================================
        html.Div([
            html.H4("Data Pipeline", style={
                'fontWeight': '700', 'marginBottom': '4px',
                'color': 'var(--text-primary)',
            }),
            html.P("From raw multi-device sensor streams to exercise intensity predictions.", style={
                'fontSize': '0.9rem', 'color': 'var(--text-secondary)',
                'marginBottom': '20px',
            }),
        ]),

        dbc.Row([
            dbc.Col([
                _pipeline_step(1, "Raw Data Collection", "3 wearable devices × varying sampling rates", COLORS['buttercup']),
                _pipeline_step(2, "Signal Synchronization", "Shiny App — manual cut, align & sync", COLORS['crocus']),
                _pipeline_step(3, "Time-Series Storage", "InfluxDB — high-frequency sensor data", COLORS['azalea']),
                _pipeline_step(4, "Feature Extraction", "FLIRT package — 60-second ML windows", COLORS['ivy']),
                _pipeline_step(5, "Model Training", "Random Forest regression → predict METs", COLORS['soot']),
            ], xs=12, lg=5, className="mb-4"),

            dbc.Col([
                html.Div([
                    dbc.CardImg(
                        src=dash.get_asset_url('pictures/alignment_shiny_app.png'),
                        top=True,
                        style={
                            'maxHeight': '260px', 'objectFit': 'cover',
                            'objectPosition': 'top', 'borderRadius': '10px 10px 0 0',
                        },
                    ),
                    html.Div([
                        html.H5("Signal Synchronization Tool", style={
                            'fontWeight': '700', 'marginBottom': '8px',
                            'color': 'var(--text-primary)',
                        }),
                        html.P([
                            "A custom ",
                            html.Strong("R Shiny App"),
                            " enables visual cutting, alignment, and synchronization of raw data across all devices for each participant. The resulting synchronized epochs form the core dataset that powers this dashboard.",
                        ], style={
                            'fontSize': '0.88rem', 'color': 'var(--text-secondary)',
                            'lineHeight': '1.55', 'margin': 0,
                        }),
                    ], style={'padding': '18px 20px'}),
                ], className="card", style={
                    'borderRadius': '12px', 'overflow': 'hidden',
                    'boxShadow': 'var(--card-shadow)',
                }),
            ], xs=12, lg=7, className="mb-4"),
        ]),

        # ========================================================
        # HARDWARE PHOTO
        # ========================================================
        html.Div([
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src=dash.get_asset_url('pictures/image.png'),
                            style={
                                'width': '100%', 'maxHeight': '320px',
                                'objectFit': 'contain', 'borderRadius': '10px',
                            },
                        ),
                    ], xs=12, lg=5, style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}),
                    dbc.Col([
                        html.Div([
                            html.H5("Data Collection Setup", style={
                                'fontWeight': '700', 'marginBottom': '10px',
                                'color': 'var(--text-primary)',
                            }),
                            html.P(
                                "All four devices are worn simultaneously by each participant during a controlled exercise protocol. This ensures we capture identical physiological events across every sensor, allowing direct head-to-head comparison of prediction accuracy.",
                                style={
                                    'fontSize': '0.9rem', 'color': 'var(--text-secondary)',
                                    'lineHeight': '1.6', 'marginBottom': '16px',
                                },
                            ),
                            html.Div([
                                html.Span("Heart Rate", style={
                                    **_pill_style,
                                    'background': f'{COLORS["azalea"]}15',
                                    'color': COLORS['azalea'],
                                    'border': f'1px solid {COLORS["azalea"]}33',
                                }),
                                html.Span("Accelerometer", style={
                                    **_pill_style,
                                    'background': f'{COLORS["ivy"]}15',
                                    'color': COLORS['ivy'],
                                    'border': f'1px solid {COLORS["ivy"]}33',
                                }),
                                html.Span("VO₂ (Calorimetry)", style={
                                    **_pill_style,
                                    'background': f'{COLORS["crocus"]}15',
                                    'color': COLORS['crocus'],
                                    'border': f'1px solid {COLORS["crocus"]}33',
                                }),
                            ]),
                        ], style={'padding': '10px 0'}),
                    ], xs=12, lg=7),
                ], className="g-4"),
            ], style={'padding': '24px'}),
        ], className="card", style={
            'borderRadius': '12px', 'boxShadow': 'var(--card-shadow)',
            'marginBottom': '30px', 'overflow': 'hidden',
        }),

        # ========================================================
        # FOOTER
        # ========================================================
        html.Div([
            html.Div([
                html.Div([
                    html.Span("DIWAH", style={
                        'fontWeight': '800', 'fontSize': '1.1rem',
                        'color': 'var(--text-primary)', 'marginRight': '6px',
                    }),
                    html.Span("·", style={'margin': '0 8px', 'color': 'var(--text-secondary)'}),
                    html.Span("Design of an Intelligent Wearable for Activity and Health", style={
                        'fontSize': '0.85rem', 'color': 'var(--text-secondary)',
                        'fontStyle': 'italic',
                    }),
                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                html.Div([
                    html.A("Linnaeus University", href="https://lnu.se", target="_blank", style={
                        'fontSize': '0.82rem', 'color': 'var(--text-secondary)',
                        'textDecoration': 'none', 'marginRight': '16px',
                    }),
                    html.Span("© 2026 · MIT License", style={
                        'fontSize': '0.82rem', 'color': 'var(--text-secondary)',
                    }),
                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
            ], style={
                'display': 'flex', 'justifyContent': 'space-between',
                'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '10px',
            }),
        ], style={
            'padding': '18px 26px',
            'borderTop': f'2px solid {COLORS["buttercup"]}',
            'marginTop': '10px',
        }),

    ], className="p-4")

from .ml_layout import create_ml_layout  # noqa: F401
