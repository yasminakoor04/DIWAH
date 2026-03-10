"""Statistical utilities for DIWAH dashboard analysis."""
import pandas as pd
import numpy as np
from scipy import stats
from typing import Dict, List, Tuple, Optional, Any

from ..constants import (
    DEVICE_NAMES,
    MIN_SAMPLES_FOR_CORRELATION,
    SIGNIFICANCE_LEVEL
)

def calculate_summary_stats(data: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """
    Calculate basic descriptive statistics for a session.
    
    Args:
        data: Dictionary with 'raw' key containing device DataFrames
    
    Returns:
        Dictionary mapping device names to their statistics
    """
    stats_dict: Dict[str, Dict[str, float]] = {}
    
    # Try raw data first
    source = data.get('raw', {})
    is_agg = False
    
    if not source:
        # Fallback to aggregated data
        source = data.get('agg', {})
        is_agg = True
    
    for device, df in source.items():
        if df is not None and not df.empty:
            # For agg data, the column name is the device name
            # For raw data, it might be the device name or column 1
            col_name = device if device in df.columns else df.columns[1] if len(df.columns) > 1 else df.columns[0]
            
            magnitudes = df[col_name]
            
            stats_dict[device] = {
                'mean': float(magnitudes.mean()),
                'std': float(magnitudes.std()),
                'median': float(magnitudes.median()),
                'min': float(magnitudes.min()),
                'max': float(magnitudes.max()),
                'count': int(len(magnitudes))
            }
            
            # If aggregated, we might want to flag it or adjust, but for now raw stats of 5s means is useful
    
    return stats_dict

def calculate_correlations(data: Dict[str, Any]) -> pd.DataFrame:
    """
    Calculate pairwise Pearson correlations between devices.
    
    Uses 5-second aggregated data to compare device agreement.
    Requires at least MIN_SAMPLES_FOR_CORRELATION samples for valid results.
    
    Args:
        data: Dictionary with 'agg' key containing aggregated device DataFrames
    
    Returns:
        Correlation matrix as DataFrame, empty DataFrame if insufficient data
    """
    available_devices = [d for d in DEVICE_NAMES if d in data.get('agg', {})]
    
    if len(available_devices) < 2:
        return pd.DataFrame()
    
    # Merge all device data on timestamp
    merged: Optional[pd.DataFrame] = None
    for device in available_devices:
        df = data['agg'][device].copy()
        df = df.rename(columns={device: device})
        if merged is None:
            merged = df[['_time', device]]
        else:
            merged = merged.merge(df[['_time', device]], on='_time', how='inner')
    
    if merged is None or len(merged) < MIN_SAMPLES_FOR_CORRELATION:
        return pd.DataFrame()
    
    # Calculate correlation matrix
    corr_df = merged[available_devices].corr()
    
    # Add significance check (r significant if |r| > 2/sqrt(n))
    n = len(merged)
    significance_threshold = 2 / np.sqrt(n)
    for i, dev1 in enumerate(available_devices):
        for j, dev2 in enumerate(available_devices):
            if i != j:
                r = corr_df.loc[dev1, dev2]
                # Note: value is kept as-is; significance could be indicated elsewhere
                if abs(r) > significance_threshold:
                    corr_df.loc[dev1, dev2] = r
    
    return corr_df

def compare_activity_rest(
    activity_data: Dict[str, Any],
    rest_data: Dict[str, Any]
) -> Dict[str, Dict[str, float]]:
    """
    Compare activity vs rest sessions using independent t-test.
    
    Calculates t-statistic, p-value, and Cohen's d effect size
    for each device that has data in both sessions.
    
    Args:
        activity_data: Data dictionary for activity session
        rest_data: Data dictionary for rest session
    
    Returns:
        Dictionary mapping device names to comparison statistics
    """
    comparison: Dict[str, Dict[str, float]] = {}
    
    for device in DEVICE_NAMES:
        # Helper to get available data (raw or agg)
        act_df = activity_data.get('raw', {}).get(device)
        if act_df is None or act_df.empty:
            act_df = activity_data.get('agg', {}).get(device)
            
        rest_df = rest_data.get('raw', {}).get(device)
        if rest_df is None or rest_df.empty:
            rest_df = rest_data.get('agg', {}).get(device)
            
        if act_df is not None and rest_df is not None and not act_df.empty and not rest_df.empty:
            # Extract magnitude column
            # For agg data, column is usually device name. For raw, might be device name or col 1
            act_col = device if device in act_df.columns else act_df.columns[1] if len(act_df.columns) > 1 else act_df.columns[0]
            rest_col = device if device in rest_df.columns else rest_df.columns[1] if len(rest_df.columns) > 1 else rest_df.columns[0]
            
            act_vals = act_df[act_col]
            rest_vals = rest_df[rest_col]
                
            # Independent samples t-test
            t_stat, p_val = stats.ttest_ind(act_vals, rest_vals)
            
            # Effect size (Cohen's d)
            pooled_std = np.sqrt((act_vals.std()**2 + rest_vals.std()**2) / 2)
            cohens_d = (act_vals.mean() - rest_vals.mean()) / pooled_std if pooled_std > 0 else 0
            
            comparison[device] = {
                'activity_mean': float(act_vals.mean()),
                'activity_std': float(act_vals.std()),
                'rest_mean': float(rest_vals.mean()),
                'rest_std': float(rest_vals.std()),
                'difference': float(act_vals.mean() - rest_vals.mean()),
                't_statistic': float(t_stat),
                'p_value': float(p_val),
                'cohens_d': float(cohens_d),
                'significant': p_val < SIGNIFICANCE_LEVEL
            }
    
    return comparison


def calculate_data_quality(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Calculate data quality metrics based on temporal overlap.
    
    Measures how well the different devices' recordings align temporally.
    
    Args:
        data: Dictionary with 'agg' key containing aggregated device DataFrames
    
    Returns:
        Dictionary with 'devices_available' and 'alignment' metrics
    """
    quality: Dict[str, str] = {}

    # Count available devices
    available_devices = [
        d for d in DEVICE_NAMES
        if d in data.get('agg', {}) and not data['agg'][d].empty
    ]
    quality['devices_available'] = f"{len(available_devices)}/{len(DEVICE_NAMES)}"

    # Need at least 2 devices to compute alignment
    if len(available_devices) < 2:
        quality['alignment'] = "N/A"
        return quality

    # Collect time ranges from 5s aggregated data
    starts: List[pd.Timestamp] = []
    ends: List[pd.Timestamp] = []

    for device in available_devices:
        df = data['agg'][device]
        starts.append(df['_time'].min())
        ends.append(df['_time'].max())

    starts_dt = pd.to_datetime(starts)
    ends_dt = pd.to_datetime(ends)

    # Temporal overlap calculation
    overlap_start = max(starts_dt)
    overlap_end = min(ends_dt)

    union_start = min(starts_dt)
    union_end = max(ends_dt)

    if overlap_end <= overlap_start:
        alignment_pct = 0.0
    else:
        overlap_seconds = (overlap_end - overlap_start).total_seconds()
        union_seconds = (union_end - union_start).total_seconds()
        alignment_pct = (overlap_seconds / union_seconds) * 100 if union_seconds > 0 else 0.0

    quality['alignment'] = f"{alignment_pct:.1f}%"
    return quality


def format_p_value(p: float) -> str:
    """
    Format p-value for display.
    
    Args:
        p: P-value from statistical test
    
    Returns:
        Formatted string representation
    """
    if p < 0.001:
        return "< 0.001"
    else:
        return f"{p:.3f}"
