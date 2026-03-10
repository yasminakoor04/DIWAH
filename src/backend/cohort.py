"""
Cohort data management with caching for DIWAH Analytics Dashboard.

This module provides functions for loading and caching cohort-wide data
to avoid duplicate queries.
"""

import logging
import pandas as pd
from typing import Dict, List, Optional, Callable, Any
from functools import lru_cache
import time

from ..constants import COHORT_CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

# Cache state
_cache_timestamp: float = 0
_cached_cohort_data: Optional[pd.DataFrame] = None


def _is_cache_valid() -> bool:
    """Check if the cache is still valid based on TTL."""
    global _cache_timestamp
    return (time.time() - _cache_timestamp) < COHORT_CACHE_TTL_SECONDS


def invalidate_cache() -> None:
    """Manually invalidate the cohort data cache."""
    global _cached_cohort_data, _cache_timestamp
    _cached_cohort_data = None
    _cache_timestamp = 0
    logger.debug("Cohort data cache invalidated")


def get_cohort_data(
    tag_values_func: Callable[[str, Optional[str]], List[str]],
    load_data_func: Callable[[str, str], Optional[Dict[str, Any]]],
    calculate_summary_stats_func: Callable[[Dict[str, Any]], Dict[str, Dict[str, float]]]
) -> pd.DataFrame:
    """
    Load cohort data for all subjects and sessions with caching.
    
    This function consolidates the duplicate logic that was in both
    the tab-cohort rendering and export_csv callback.
    
    Args:
        tag_values_func: Function to get tag values from database
        load_data_func: Function to load data for a subject/session
        calculate_summary_stats_func: Function to calculate statistics
    
    Returns:
        DataFrame with columns: Subject, Session, {Device}_Mean, {Device}_Std, {Device}_Samples
    """
    global _cached_cohort_data, _cache_timestamp
    
    # Return cached data if valid
    if _cached_cohort_data is not None and _is_cache_valid():
        logger.debug("Returning cached cohort data")
        return _cached_cohort_data.copy()
    
    logger.info("Loading cohort data for all subjects and sessions")
    
    all_subjects = tag_values_func('subject')
    all_data: List[Dict] = []
    
    for subj in all_subjects:
        sessions = tag_values_func('session', subject=subj)
        for sess_type in sessions:
            try:
                sess_data = load_data_func(subj, sess_type)
                if sess_data and not sess_data.get('error'):
                    stats = calculate_summary_stats_func(sess_data)
                    row = {'Subject': subj, 'Session': sess_type}
                    for dev, st in stats.items():
                        row[f'{dev.title()}_Mean'] = round(st['mean'], 2)
                        row[f'{dev.title()}_Std'] = round(st['std'], 2)
                        row[f'{dev.title()}_Samples'] = st['count']
                    all_data.append(row)
            except Exception as e:
                logger.warning(f"Failed to load data for {subj}/{sess_type}: {e}")
                continue
    
    if not all_data:
        logger.warning("No cohort data available")
        return pd.DataFrame()
    
    df = pd.DataFrame(all_data)
    
    # Ensure expected columns exist even if some subjects lack a device
    expected_mean_cols = ['Actigraph_Mean', 'Bangle_Mean', 'Emotibit_Mean']
    expected_std_cols = ['Actigraph_Std', 'Bangle_Std', 'Emotibit_Std']
    expected_sample_cols = ['Actigraph_Samples', 'Bangle_Samples', 'Emotibit_Samples']
    
    for col in expected_mean_cols + expected_std_cols + expected_sample_cols:
        if col not in df.columns:
            df[col] = pd.NA
    
    # Convert to numeric to allow aggregation
    for col in expected_mean_cols + expected_std_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    for col in expected_sample_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    
    # Update cache
    _cached_cohort_data = df
    _cache_timestamp = time.time()
    logger.info(f"Cached cohort data: {len(df)} records")
    
    return df.copy()


def get_cohort_summary(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Generate summary statistics from cohort data.
    
    Args:
        df: Cohort DataFrame from get_cohort_data()
    
    Returns:
        Dictionary with 'by_subject' and 'by_session' summary DataFrames
    """
    if df.empty:
        return {'by_subject': pd.DataFrame(), 'by_session': pd.DataFrame()}
    
    agg_cols = {
        'Actigraph_Mean': ['mean', 'std', 'count'],
        'Bangle_Mean': ['mean', 'std', 'count'],
        'Emotibit_Mean': ['mean', 'std', 'count']
    }
    
    # Filter to only columns that exist
    agg_cols = {k: v for k, v in agg_cols.items() if k in df.columns}
    
    if not agg_cols:
        return {'by_subject': pd.DataFrame(), 'by_session': pd.DataFrame()}
    
    by_subject = df.groupby('Subject').agg(agg_cols).round(2)
    by_session = df.groupby('Session').agg(agg_cols).round(2)
    
    return {
        'by_subject': by_subject,
        'by_session': by_session
    }
