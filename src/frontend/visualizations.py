"""
Visualization functions for DIWAH Analytics Dashboard.

This module contains all Plotly chart creation functions.
"""

from typing import Dict, Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from scipy import stats

from ..constants import COLORS, DEVICE_COLORS, PARTICIPANT_MAPPING
from ..backend.stats_utils import format_p_value


def make_time_plot(data: Any, subject: str, session: str = "", template: str = "plotly_white") -> go.Figure:
    """
    Create time-series plot. Supports processed DataFrame or legacy dict format.
    
    Args:
        data: DataFrame with device columns, or Dict containing 'raw'/'agg'.
        subject: Subject identifier
        session: Session label (optional)
        template: Plotly template name
    
    Returns:
        Plotly Figure with available data.
    """
    fig = go.Figure(layout=dict(template=template))
    
    # USER REQUEST: "only the second 5 sec and make it beautiful"
    # Regardless of data source (raw or offline), we ONLY show 5s aggregated data now.
    
    # 1. Extract 5s data
    plot_data = pd.DataFrame()
    
    # Check 'agg' first (populated by load_data for both offline and influxdb)
    if isinstance(data, dict) and 'agg' in data:
         for dev, df in data['agg'].items():
            temp = df.copy()
            if '_time' in temp.columns:
                temp.set_index('_time', inplace=True)
            if dev in temp.columns:
                 plot_data = plot_data.join(temp[dev], how='outer') if not plot_data.empty else temp[[dev]]
                 
    elif isinstance(data, pd.DataFrame):
        plot_data = data

    if plot_data.empty:
        fig = go.Figure()
        fig.add_annotation(text='No 5s data available', showarrow=False)
        return fig

    fig = go.Figure()
    
    # beautiful colors
    colors = {
        'Actigraph': '#636EFA', # Plotly Blue
        'Bangle': '#EF553B',    # Plotly Red
        'EmotiBit': '#00CC96'   # Plotly Green
    }

    for dev in plot_data.columns:
        if dev in ['timestamp', 'Subject', '_time']: continue
            
        # Clean name
        name = dev.title()
        
        fig.add_trace(go.Scatter(
            x=plot_data.index,
            y=plot_data[dev],
            name=name,
            mode='lines',
            line=dict(width=2.5, color=colors.get(name, '#AB63FA')),
            opacity=0.9,
            hovertemplate='<b>%{y:.2f}g</b><extra>%{fullData.name}</extra>'
        ))
        
    # Theme-aware colors
    is_dark = template == "plotly_dark"
    grid_color = '#444' if is_dark else '#eee'
    zero_line_color = '#666' if is_dark else '#ddd'
    text_color = '#f5f5f5' if is_dark else '#262626'
    
    fig.update_layout(
        template=template,
        title=dict(
            text=f"<b>Activity Magnitude (5s Average)</b><br><span style='font-size:12px;color:{'#aaa' if is_dark else 'gray'};'>Participant {PARTICIPANT_MAPPING.get(str(subject), subject)}</span>",
            x=0.05,
            xanchor='left'
        ),
        height=450,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', # Transparent for theme compatibility
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='#333' if is_dark else '#fff',
            font_color='#fff' if is_dark else '#000',
            bordercolor='#555' if is_dark else '#ddd'
        ),
        font=dict(family="Inter, sans-serif", color=text_color),
        margin=dict(l=60, r=40, t=80, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(0,0,0,0)'
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor=grid_color,
            showline=True,
            linecolor=zero_line_color,
            zeroline=False
        ),
        yaxis=dict(
            title="Magnitude (g)",
            showgrid=True,
            gridcolor=grid_color,
            zeroline=True,
            zerolinecolor=zero_line_color
        )
    )
    
    return fig


def make_calorimetry_timeline(df: pd.DataFrame, subject: str, template: str = "plotly_white") -> go.Figure:
    """
    Create a timeline overlay for Calorimetry parameters: Heart Rate and METS.
    Includes background shading for Intensity Zones based on METS strictly.
    """
    if df is None or df.empty or 'HR' not in df.columns or 'METS' not in df.columns:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text='Calorimetry Data (HR/METS) not available for this participant.', showarrow=False)
        return fig
        
    # Get Plotly template colors
    is_dark = template == "plotly_dark"
    grid_color = '#444' if is_dark else '#eee'
    zero_line_color = '#666' if is_dark else '#ddd'
    text_color = '#f5f5f5' if is_dark else '#262626'
    
    fig = go.Figure()
    
    # Trace 1: Heart Rate (Primary Y-axis)
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['HR'],
        name='Heart Rate (BPM)',
        mode='lines',
        line=dict(width=2.5, color='#EF553B'), # Red-orange
        opacity=0.9,
        yaxis='y1',
        hovertemplate='<b>%{y:.0f} BPM</b><extra></extra>'
    ))
    
    # Trace 2: METS (Secondary Y-axis)
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['METS'],
        name='METs',
        mode='lines',
        line=dict(width=2.5, color='#00CC96'), # Green
        opacity=1.0,
        yaxis='y2',
        hovertemplate='<b>%{y:.1f} METs</b><extra></extra>'
    ))
    
    # Intensity Zones (Background Rectangles attached to y2 / METS axis)
    # Light (<3): Green tint
    # Mod (3-6): Yellow tint
    # Vigorous (>6): Red tint
    zones = [
        dict(type="rect", yref="y2", xref="paper", x0=0, x1=1, y0=0, y1=3, 
             fillcolor="rgba(0, 204, 150, 0.1)", line_width=0, layer="below"),
        dict(type="rect", yref="y2", xref="paper", x0=0, x1=1, y0=3, y1=6, 
             fillcolor="rgba(255, 215, 0, 0.1)", line_width=0, layer="below"),
        dict(type="rect", yref="y2", xref="paper", x0=0, x1=1, y0=6, y1=max(20, df['METS'].max() + 2), 
             fillcolor="rgba(239, 85, 59, 0.1)", line_width=0, layer="below")
    ]
    
    # Annotations for zones
    zone_annotations = [
        dict(x=1.0, y=1.5, xref="paper", yref="y2", text="Lätt (<3)", showarrow=False, xanchor="right", font=dict(color="#00CC96")),
        dict(x=1.0, y=4.5, xref="paper", yref="y2", text="Medel (3-6)", showarrow=False, xanchor="right", font=dict(color="#d4af37")),
        dict(x=1.0, y=7.5, xref="paper", yref="y2", text="Hög (>6)", showarrow=False, xanchor="right", font=dict(color="#EF553B"))
    ]
    
    max_hr = min(220, max(150, df['HR'].max() + 20))
    max_met = max(10, df['METS'].max() + 2)

    fig.update_layout(
        template=template,
        title=dict(
            text=f"<b>Heart Rate & Energy Expenditure</b><br><span style='font-size:12px;color:{'#aaa' if is_dark else 'gray'};'>Participant {PARTICIPANT_MAPPING.get(str(subject), subject)}</span>",
            x=0.05,
            xanchor='left'
        ),
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hovermode='x unified',
        font=dict(family="Inter, sans-serif", color=text_color),
        margin=dict(l=60, r=60, t=80, b=40),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor='rgba(0,0,0,0)'
        ),
        xaxis=dict(
            showgrid=True, gridcolor=grid_color, showline=True, linecolor=zero_line_color
        ),
        yaxis=dict(
            title=dict(
                text="Heart Rate (BPM)",
                font=dict(color="#EF553B")
            ),
            tickfont=dict(color="#EF553B"),
            showgrid=False,
            range=[40, max_hr]
        ),
        yaxis2=dict(
            title=dict(
                text="METs",
                font=dict(color="#00CC96")
            ),
            tickfont=dict(color="#00CC96"),
            anchor="x",
            overlaying="y",
            side="right",
            showgrid=False,
            range=[0, max_met]
        ),
        shapes=zones,
        annotations=zone_annotations
    )
    
    return fig


def make_correlation_heatmap(corr_df: pd.DataFrame, template: str = "plotly_white") -> go.Figure:
    """
    Create correlation heatmap from correlation matrix.
    
    Args:
        corr_df: DataFrame with correlation coefficients
        template: Plotly template name
    
    Returns:
        Plotly Figure with heatmap
    """
    if corr_df.empty:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text='Not enough data', showarrow=False)
        return fig
    
    fig = px.imshow(
        corr_df,
        text_auto='.2f',
        color_continuous_scale='RdYlGn',
        zmin=-1,
        zmax=1,
        aspect='auto',
        template=template
    )
    fig.update_layout(
        title='Device Correlation Matrix',
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    
    return fig


def make_correlation_bar_chart(df: pd.DataFrame, metric: str = 'Bangle_Actigraph', template: str = "plotly_white") -> go.Figure:
    """
    Create a beautiful bar chart of correlation coefficients by subject.
    Uses gradient colors based on correlation strength.
    """
    if df.empty or metric not in df.columns:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text='No data available', showarrow=False)
        return fig
    
    # Sort descending (missing data at bottom)
    df_sorted = df.sort_values(metric, ascending=True, na_position='first').copy()
    
    # Color scale: poor (pink) -> acceptable (yellow) -> good (green)
    def get_color(r):
        if pd.isna(r): return 'gray'
        if r >= 0.7: return COLORS['ivy']
        elif r >= 0.5: return COLORS['buttercup']
        elif r >= 0.3: return '#FFA500'  # Orange
        else: return COLORS['azalea']
    
    colors = [get_color(r) for r in df_sorted[metric]]
    
    fig = go.Figure(go.Bar(
        x=df_sorted[metric].fillna(0.01),
        y=[f'Participant {PARTICIPANT_MAPPING.get(str(s), s)}' for s in df_sorted['Subject']],
        orientation='h',
        text=[f'{r:.2f}' if not pd.isna(r) else 'N/A' for r in df_sorted[metric]],
        textposition='auto',
        textfont=dict(color=['#555' if pd.isna(r) else 'white' for r in df_sorted[metric]], size=11, family='Arial Black'),
        marker=dict(
            color=colors,
            line=dict(color='white', width=1)
        ),
        hovertemplate='%{y}<br>r = %{text}<extra></extra>'
    ))
    
    # Add reference lines
    fig.add_vline(x=0.7, line_dash="dash", line_color=COLORS['ivy'], 
                  annotation_text="Good (0.7)", annotation_position="top")
    fig.add_vline(x=0.5, line_dash="dot", line_color=COLORS['buttercup'], 
                  annotation_text="Acceptable (0.5)", annotation_position="bottom")
    
    fig.update_layout(
        template=template,
        height=max(350, len(df) * 28),
        xaxis=dict(
            title="Pearson Correlation (r)",
            range=[0, 1.05],
            showgrid=False,
            tickfont=dict(size=11)
        ),
        yaxis=dict(
            title="",
            dtick=1,
            tickfont=dict(size=11)
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=80, r=20, t=20, b=50),
        showlegend=False
    )
    return fig


def make_subgroup_boxplot(df: pd.DataFrame, group_col: str, metric: str = 'Bangle_Actigraph', template: str = "plotly_white") -> go.Figure:
    """
    Create beautiful box plots comparing correlation distributions by subgroup.
    """
    if df.empty or group_col not in df.columns or metric not in df.columns:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text='No subgroup data available', showarrow=False)
        return fig
    
    # Custom colors for gender
    color_map = {
        'Male': COLORS['crocus'],
        'Female': COLORS['azalea'],
        'Man': COLORS['crocus'],
        'Kvinna': COLORS['azalea']
    }
    
    groups = df[group_col].unique()
    fig = go.Figure()
    
    def hex_to_rgba(hex_color, alpha=0.3):
        """Convert hex color to rgba string."""
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f'rgba({r},{g},{b},{alpha})'
    
    for group in groups:
        group_data = df[df[group_col] == group][metric].dropna()
        color = color_map.get(group, COLORS['ivy'])
        
        fig.add_trace(go.Box(
            y=group_data,
            name=str(group),
            boxpoints='all',
            jitter=0.3,
            pointpos=-1.5,
            marker=dict(
                color=color,
                size=8,
                opacity=0.7
            ),
            line=dict(color=color, width=2),
            fillcolor=hex_to_rgba(color) if color.startswith('#') else color
        ))
    
    # Add reference line for good correlation
    fig.add_hline(y=0.7, line_dash="dash", line_color=COLORS['ivy'], 
                  annotation_text="Good (r=0.7)")
    
    text_color = 'white' if 'dark' in template else COLORS['soot']
    
    fig.update_layout(
        template=template,
        yaxis=dict(
            title="Pearson Correlation (r)",
            autorange=True,
            gridcolor='#f0f0f0' if 'white' in template else '#333',
            tickfont=dict(size=11)
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=12, color=text_color)
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        margin=dict(l=60, r=20, t=20, b=40),
        height=380
    )
    return fig


def make_gender_bar_chart(df: pd.DataFrame, group_col: str, metric: str = 'Bangle_Actigraph', template: str = "plotly_white") -> go.Figure:
    """
    Create a bar chart comparing the average correlation between subgroups (e.g., Male vs Female).
    """
    if df.empty or group_col not in df.columns or metric not in df.columns:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text='No subgroup data available', showarrow=False)
        return fig
        
    color_map = {
        'Male': COLORS['crocus'],
        'Female': COLORS['azalea']
    }
    
    # Calculate means and ensure consistent sorting order
    groups = df.groupby(group_col)[metric].mean().reset_index()
    groups = groups.sort_values(group_col).copy()
    groups.dropna(inplace=True)
    
    fig = go.Figure(go.Bar(
        x=groups[group_col],
        y=groups[metric],
        text=[f'{val:.2f}' for val in groups[metric]],
        textposition='auto',
        marker_color=[color_map.get(str(g), COLORS['ivy']) for g in groups[group_col]]
    ))
    
    text_color = 'white' if 'dark' in template else COLORS['soot']
    
    fig.update_layout(
        template=template,
        bargap=0.4,
        yaxis=dict(
            title="Pearson Correlation (r)",
            range=[0, 1.05],
            dtick=0.2,
            gridcolor='#f0f0f0' if 'white' in template else '#333',
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=12, color=text_color)
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        margin=dict(l=60, r=20, t=20, b=40),
        height=380
    )
    return fig


def make_scatter_plot(df: pd.DataFrame, x_col: str, y_col: str, template: str = "plotly_white") -> go.Figure:
    """
    Create beautiful scatter plot of aligned magnitudes with correlation line.
    """
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        fig = go.Figure(layout=dict(template=template))
        fig.add_annotation(text='No data for scatter plot', showarrow=False)
        return fig
        
    # Downsample for performance if needed
    if len(df) > 2000:
        plot_df = df.sample(2000)
    else:
        plot_df = df
        
    r, p = stats.pearsonr(plot_df[x_col].dropna(), plot_df[y_col].dropna())
    
    # Create scatter
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=plot_df[x_col],
        y=plot_df[y_col],
        mode='markers',
        marker=dict(
            color=COLORS['crocus'],
            size=6,
            opacity=0.5,
            line=dict(width=0)
        ),
        hovertemplate='Actigraph: %{x:.2f}g<br>Bangle: %{y:.2f}g<extra></extra>'
    ))
    
    # Add identity line (perfect agreement)
    min_val = min(plot_df[x_col].min(), plot_df[y_col].min())
    max_val = max(plot_df[x_col].max(), plot_df[y_col].max())
    fig.add_trace(go.Scatter(
        x=[min_val, max_val],
        y=[min_val, max_val],
        mode='lines',
        line=dict(color=COLORS['ivy'], width=2, dash='dash'),
        name='Perfect Agreement',
        showlegend=False
    ))
    
    
    # Add correlation annotation
    text_color = 'white' if 'dark' in template else COLORS['soot']
    
    fig.add_annotation(
        x=0.95, y=0.05,
        xref='paper', yref='paper',
        text=f"<b>r = {r:.2f}</b>",
        showarrow=False,
        font=dict(size=14, color=text_color),
        bgcolor='rgba(0,0,0,0)',
        bordercolor=COLORS['buttercup'],
        borderwidth=2,
        borderpad=6
    )
    
    grid_color = '#f0f0f0' if 'white' in template else '#333'
    
    fig.update_layout(
        template=template,
        xaxis=dict(
            title="Actigraph (g)",
            gridcolor=grid_color,
            tickfont=dict(size=10)
        ),
        yaxis=dict(
            title="Bangle (g)",
            gridcolor=grid_color,
            tickfont=dict(size=10)
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=50, r=20, t=10, b=50),
        height=300,
        showlegend=False
    )
    return fig


def make_time_series_overlay(data: pd.DataFrame, columns: list, title: str = "Time Series Overlay", template: str = "plotly_white") -> go.Figure:
    """
    Create a time series plot overlaying multiple columns.
    """
    fig = go.Figure(layout=dict(template=template))
    
    for col in columns:
        if col not in data.columns:
            continue
            
        color = DEVICE_COLORS.get(col.lower(), 'gray')
        
        fig.add_trace(go.Scatter(
            x=data.index,
            y=data[col],
            name=col,
            mode='lines',
            line=dict(color=color, width=1.5),
            opacity=0.8
        ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Magnitude (g)",
        legend_title="Device",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20),
        height=320,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    
    return fig
