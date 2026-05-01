"""
Machine Learning tab layout and visualization helpers for the DIWAH Dashboard.
This module is imported by layouts.py to render the enhanced ML evaluation tab.
"""

import json
from pathlib import Path
import plotly.graph_objects as go
from dash import html, dcc
import dash_bootstrap_components as dbc

from ..constants import COLORS


_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "Acc_pipe" / "data" / "processed"


def _load_json(filename: str):
    """Safely load a JSON file from the processed data directory."""
    path = _DATA_DIR / filename
    if path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _load_metrics() -> dict:
    """Load ML metrics, falling back to hardcoded defaults."""
    metrics_data = {
        'ActiGraph (Clinical)': {'MLR_MAE': 4.308, 'MLR_R2': -1.228, 'MLR_RMSE': 5.749, 'RF_MAE': 2.066, 'RF_R2': 0.518, 'RF_RMSE': 2.673},
        'EmotiBit (Consumer)': {'MLR_MAE': 7.288, 'MLR_R2': -7.325, 'MLR_RMSE': 11.113, 'RF_MAE': 2.033, 'RF_R2': 0.627, 'RF_RMSE': 2.352},
        'Bangle.js (Consumer)': {'MLR_MAE': 23.183, 'MLR_R2': -25.000, 'MLR_RMSE': 57.201, 'RF_MAE': 1.995, 'RF_R2': 0.561, 'RF_RMSE': 2.513},
    }

    real_res = _load_json("ml_metrics.json")
    if real_res:
        device_map = {
            'actigraph': 'ActiGraph (Clinical)',
            'emotibit': 'EmotiBit (Consumer)',
            'bangle': 'Bangle.js (Consumer)',
            'fused': 'Sensor Fusion',
        }
        for key, label in device_map.items():
            if key in real_res:
                metrics_data[label] = {
                    'MLR_MAE': real_res[key]['MLR']['MAE'],
                    'MLR_R2': real_res[key]['MLR']['R2'],
                    'MLR_RMSE': real_res[key]['MLR']['RMSE'],
                    'RF_MAE': real_res[key]['RF']['MAE'],
                    'RF_R2': real_res[key]['RF']['R2'],
                    'RF_RMSE': real_res[key]['RF']['RMSE'],
                }

    return metrics_data


def _make_grouped_bar(devices, mlr_vals, rf_vals, y_title, mlr_hover, rf_hover):
    """Helper to create a grouped bar chart (MAE, RMSE, or R²)."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=devices, y=mlr_vals,
        name='Linear Regression', marker_color=COLORS['crocus'],
        text=[f"{v:.2f}" for v in mlr_vals], textposition='outside', cliponaxis=False,
        hovertemplate=mlr_hover
    ))
    fig.add_trace(go.Bar(
        x=devices, y=rf_vals,
        name='Random Forest', marker_color=COLORS['buttercup'],
        text=[f"{v:.2f}" for v in rf_vals], textposition='outside', cliponaxis=False,
        hovertemplate=rf_hover
    ))
    fig.update_layout(
        yaxis_title=y_title, barmode='group',
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#888'),
        legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5),
        margin=dict(t=45, b=100, l=40, r=20),
        yaxis=dict(gridcolor='rgba(150,150,150,0.1)'),
        hovermode="x unified"
    )
    return fig


def _make_intensity_chart():
    """Build a grouped bar chart of MAE by intensity zone per device (RF only)."""
    data = _load_json("ml_intensity_breakdown.json")
    if not data:
        return None

    zone_labels = ["Light", "Moderate", "Vigorous"]
    zone_colors = [COLORS['ivy'], COLORS['buttercup'], COLORS['azalea']]

    device_map = {'actigraph': 'ActiGraph', 'emotibit': 'EmotiBit', 'bangle': 'Bangle.js', 'fused': 'Fusion'}
    devices_present = [k for k in device_map if k in data]

    fig = go.Figure()
    for zone, color in zip(zone_labels, zone_colors):
        mae_vals = []
        x_labels = []
        for dev_key in devices_present:
            rf_zone = data[dev_key].get("RF", {}).get(zone, {})
            mae = rf_zone.get("MAE")
            n = rf_zone.get("N", 0)
            mae_vals.append(mae if mae is not None else 0)
            x_labels.append(device_map[dev_key])

        fig.add_trace(go.Bar(
            x=x_labels, y=mae_vals, name=f"{zone} (n={n})",
            marker_color=color,
            text=[f"{v:.2f}" if v else "—" for v in mae_vals],
            textposition='outside', cliponaxis=False
        ))

    fig.update_layout(
        yaxis_title="MAE (METs)", barmode='group',
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#888'),
        legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5),
        margin=dict(t=30, b=100, l=40, r=20),
        yaxis=dict(gridcolor='rgba(150,150,150,0.1)'),
        hovermode="x unified"
    )
    return fig


def _make_feature_importance_chart():
    """Build a horizontal bar chart showing top-15 RF features per device."""
    data = _load_json("ml_feature_importance.json")
    if not data:
        return None

    device_dd_options = []
    device_map = {'actigraph': 'ActiGraph', 'emotibit': 'EmotiBit', 'bangle': 'Bangle.js', 'fused': 'Sensor Fusion'}
    for key, label in device_map.items():
        if key in data and data[key]:
            device_dd_options.append({"label": label, "value": key})

    return device_dd_options


def create_ml_layout() -> html.Div:
    """
    Renders the enhanced Machine Learning Dashboard with:
    - MAE / RMSE / R² bar charts
    - Feature importance section
    - Intensity breakdown
    - Interactive scatter + residual + Bland-Altman plots
    """
    metrics_data = _load_metrics()
    devices = list(metrics_data.keys())

    mlr_mae = [metrics_data[d]['MLR_MAE'] for d in devices]
    rf_mae = [metrics_data[d]['RF_MAE'] for d in devices]
    mlr_rmse = [metrics_data[d]['MLR_RMSE'] for d in devices]
    rf_rmse = [metrics_data[d]['RF_RMSE'] for d in devices]
    mlr_r2 = [metrics_data[d]['MLR_R2'] for d in devices]
    rf_r2 = [metrics_data[d]['RF_R2'] for d in devices]

    fig_mae = _make_grouped_bar(devices, mlr_mae, rf_mae, "Mean Absolute Error (METs)",
                                "<b>%{x}</b><br>MLR MAE: %{y:.3f} METs<extra></extra>",
                                "<b>%{x}</b><br>RF MAE: %{y:.3f} METs<extra></extra>")

    fig_rmse = _make_grouped_bar(devices, mlr_rmse, rf_rmse, "Root Mean Squared Error (METs)",
                                 "<b>%{x}</b><br>MLR RMSE: %{y:.3f} METs<extra></extra>",
                                 "<b>%{x}</b><br>RF RMSE: %{y:.3f} METs<extra></extra>")

    # R² chart with a zero-line
    fig_r2 = _make_grouped_bar(devices, mlr_r2, rf_r2, "R-squared (R²)",
                               "<b>%{x}</b><br>MLR R²: %{y:.3f}<extra></extra>",
                               "<b>%{x}</b><br>RF R²: %{y:.3f}<extra></extra>")
    fig_r2.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)",
                     annotation_text="Baseline (R²=0)", annotation_position="bottom right",
                     annotation_font_color="#888")

    # Intensity breakdown chart
    fig_intensity = _make_intensity_chart()

    # Feature importance dropdown options
    fi_options = _make_feature_importance_chart() or []
    default_fi_device = fi_options[0]["value"] if fi_options else "actigraph"

    # Scatter plot device options (include Sensor Fusion)
    scatter_device_options = [
        {"label": "ActiGraph", "value": "ActiGraph"},
        {"label": "EmotiBit", "value": "EmotiBit"},
        {"label": "Bangle.js", "value": "Bangle.js"},
        {"label": "Sensor Fusion", "value": "Sensor Fusion"},
    ]

    def _card(title, graph, border_color=COLORS['buttercup']):
        return html.Div([
            html.Div([
                html.Span(title, className="text-muted", style={'fontSize': '0.85rem'})
            ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
            dcc.Loading(graph)
        ], className="card", style={
            'borderRadius': '10px', 'boxShadow': 'var(--card-shadow)',
            'overflow': 'hidden', 'borderLeft': f'4px solid {border_color}'
        })

    children = [
        # === Header Banner ===
        html.Div([
            html.H3("Machine Learning Evaluation",
                     style={'margin': 0, 'fontWeight': '600', 'color': COLORS['soot']}),
            html.P("Predicting Energy Expenditure (METs) — Individual Devices vs. Sensor Fusion",
                    style={'margin': '5px 0 0 0', 'fontSize': '0.95rem', 'color': COLORS['soot']})
        ], style={
            'background': f"linear-gradient(135deg, {COLORS['buttercup']} 0%, {COLORS['lily']} 100%)",
            'padding': '20px 25px', 'borderRadius': '12px', 'marginBottom': '25px',
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)'
        }),

        html.P("Random Forest algorithms successfully map non-linear biological movement artifacts, "
               "reducing the Mean Absolute Error to ~2 METs across both clinical and consumer devices. "
               "Sensor Fusion (combining all devices) achieves the best overall performance.",
               className="text-muted", style={'fontSize': '1.05rem', 'marginBottom': '25px'}),

        # === ROW 1: MAE + RMSE ===
        dbc.Row([
            dbc.Col([_card("Mean Absolute Error (MAE in METs)",
                           dcc.Graph(figure=fig_mae, config={'displayModeBar': False}, style={'height': '400px'}, responsive=True),
                           COLORS['buttercup'])], xs=12, lg=6, className="mb-4"),
            dbc.Col([_card("Root Mean Squared Error (RMSE in METs)",
                           dcc.Graph(figure=fig_rmse, config={'displayModeBar': False}, style={'height': '400px'}, responsive=True),
                           COLORS['crocus'])], xs=12, lg=6, className="mb-4"),
        ]),

        # === ROW 2: R² ===
        dbc.Row([
            dbc.Col([_card("R-squared (R²) — Explained Variance",
                           dcc.Graph(figure=fig_r2, config={'displayModeBar': False}, style={'height': '400px'}, responsive=True),
                           COLORS['ivy'])], xs=12, lg=12 if not fig_intensity else 6, className="mb-4"),
        ] + ([
            dbc.Col([_card("RF Error by Exercise Intensity Zone",
                           dcc.Graph(figure=fig_intensity, config={'displayModeBar': False}, style={'height': '400px'}, responsive=True),
                           COLORS['azalea'])], xs=12, lg=6, className="mb-4"),
        ] if fig_intensity else [])),

        # === Feature Importance Section ===
        html.Div([
            html.H5("Random Forest — Feature Importance Analysis", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}'
            }),
        ], style={'marginTop': '20px'}),

        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Span("Top Features Driving MET Predictions", className="text-muted", style={'fontSize': '0.85rem'})
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.Label("Device:", className="fw-bold mb-1 text-muted", style={'fontSize': '0.85rem'}),
                                dcc.Dropdown(
                                    id="fi-device-dd",
                                    options=fi_options,
                                    value=default_fi_device,
                                    clearable=False,
                                    style={'color': '#212529'}
                                )
                            ], md=4, className="mb-3 mb-md-0"),
                        ])
                    ], style={'padding': '15px 20px'}),
                    dcc.Loading(dcc.Graph(id="fi-bar-chart", config={'displayModeBar': False}, style={'height': '450px'}))
                ], className="card", style={
                    'borderRadius': '10px', 'boxShadow': 'var(--card-shadow)',
                    'overflow': 'visible', 'borderLeft': f'4px solid {COLORS["ivy"]}'
                })
            ], xs=12, className="mb-4"),
        ]),

        # === Interactive Scatter / Residual / Bland-Altman Section ===
        html.Div([
            html.H5("Model Diagnostics — Prediction Analysis", style={
                'fontWeight': '600', 'marginBottom': '15px',
                'paddingBottom': '10px', 'borderBottom': f'2px solid {COLORS["buttercup"]}'
            }),
        ], style={'marginTop': '20px'}),

        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Span("Interactive Model Prediction Filter", className="text-muted", style={'fontSize': '0.85rem'})
                    ], style={'padding': '12px 20px', 'borderBottom': '1px solid var(--border-color)'}),
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.Label("Select Device:", className="fw-bold mb-1 text-muted", style={'fontSize': '0.85rem'}),
                                dcc.Dropdown(id="ml-device-dd", options=scatter_device_options,
                                             value="EmotiBit", clearable=False, style={'color': '#212529'})
                            ], md=6, className="mb-3 mb-md-0"),
                            dbc.Col([
                                html.Label("Select Model:", className="fw-bold mb-1 text-muted", style={'fontSize': '0.85rem'}),
                                dcc.Dropdown(id="ml-model-dd", options=[
                                    {"label": "Multiple Linear Regression", "value": "Multiple Linear Regression"},
                                    {"label": "Random Forest", "value": "Random Forest"}
                                ], value="Random Forest", clearable=False, style={'color': '#212529'})
                            ], md=6)
                        ])
                    ], style={'padding': '20px'})
                ], className="card", style={
                    'borderRadius': '10px', 'boxShadow': 'var(--card-shadow)',
                    'overflow': 'visible', 'borderLeft': f'4px solid {COLORS["soot"]}'
                })
            ], xs=12, className="mb-4")
        ]),

        # Scatter + Residual row
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Loading(dcc.Graph(id="ml-scatter-plot", config={"displayModeBar": False}, style={'height': '450px'}))
                ), className="border-0 shadow-sm mb-4 bg-transparent")
            ], xs=12, lg=6),
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Loading(dcc.Graph(id="ml-residual-plot", config={"displayModeBar": False}, style={'height': '450px'}))
                ), className="border-0 shadow-sm mb-4 bg-transparent")
            ], xs=12, lg=6),
        ]),

        # Bland-Altman + Line chart row
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Loading(dcc.Graph(id="ml-bland-altman-plot", config={"displayModeBar": False}, style={'height': '450px'}))
                ), className="border-0 shadow-sm mb-4 bg-transparent")
            ], xs=12, lg=6),
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Loading(dcc.Graph(id="ml-line-plot", config={"displayModeBar": False}, style={'height': '450px'}))
                ), className="border-0 shadow-sm mb-4 bg-transparent")
            ], xs=12, lg=6),
        ], className="mb-5"),
    ]

    return html.Div(children)
