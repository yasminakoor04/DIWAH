"""
Correlation analysis module using InfluxDB for DIWAH Analytics Dashboard.

This module provides functions for calculating correlations between devices
using data from InfluxDB.
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
import logging
from typing import Dict, List, Optional, Tuple, Any

from ..config import INFLUX_BUCKET
from .database import get_query_api, health_check

# Setup logging
logger = logging.getLogger(__name__)

# In-memory caches — computed once, reused on every page load
_demographics_cache = None
_cohort_cache = None

COHORT_SUBJECTS: List[str] = [
    "2002", "2003", "2004", "2005", "2006", "2007", "2008", "2009", "2010",
    "2013", "2014", "2015", "2016", "2017", "2018", "2019", "2020", "2021",
    "2022", "2024", "2025", "2026", "2027", "2030", "2032", "2033", "2034",
    "2035", "2036", "2042",
]

from ..config.paths import DATA_ROOT

DEFAULT_DEMOGRAPHICS_CSV = DATA_ROOT / "participants_anonymized.csv"


def load_demographics() -> pd.DataFrame:
    """
    Load participant demographics from local CSV.
    
    Returns:
        DataFrame with columns: Subject, Gender, Length_cm, Weight_kg, Age_years, BMI_kg_m2
    """
    global _demographics_cache
    if _demographics_cache is not None:
        return _demographics_cache
    try:
        csv_path = Path(os.getenv("DEMOGRAPHICS_CSV", DEFAULT_DEMOGRAPHICS_CSV))
        if not csv_path.exists():
            logger.warning(f"Demographics CSV not found: {csv_path}")
            return pd.DataFrame()

        df = pd.read_csv(csv_path)
        if df.empty:
            return pd.DataFrame()

        col_mapping = {
            "ID": "Subject",
            "subject": "Subject",
            "gender": "Gender",
            "Gender": "Gender",
            "length_cm": "Length_cm",
            "Length_cm": "Length_cm",
            "weight_kg": "Weight_kg",
            "Weight_kg": "Weight_kg",
            "age_years": "Age_years",
            "Age_years": "Age_years",
            "bmi": "BMI_kg_m2",
            "BMI_kg_m2": "BMI_kg_m2",
        }
        df = df.rename(columns=col_mapping)

        if "Subject" in df.columns:
            df["Subject"] = (
                df["Subject"]
                .astype(str)
                .str.replace("Diwah", "", regex=False)
                .str.strip()
            )

        if "Gender" in df.columns:
            df["Gender"] = (
                df["Gender"]
                .replace({"Kvinna": "Female", "Man": "Male"})
                .astype(str)
                .str.strip()
            )

        keep_cols = ["Subject", "Gender", "Length_cm", "Weight_kg", "Age_years", "BMI_kg_m2"]
        df = df[[c for c in keep_cols if c in df.columns]]

        _demographics_cache = df.drop_duplicates(subset=["Subject"]) if "Subject" in df.columns else df
        return _demographics_cache
        
    except Exception as e:
        logger.warning(f"Could not load demographics from CSV: {e}")
        return pd.DataFrame()


def load_aligned_data(subject_id: str, session: str = None) -> Optional[pd.DataFrame]:
    """
    Load and merge aligned data for a subject from InfluxDB.
    Returns DataFrame with columns: timestamp, Actigraph, Bangle, EmotiBit (magnitudes)
    
    Args:
        subject_id: Subject identifier
        session: Optional session filter. If None, loads all sessions.
    """
    if not health_check():
        logger.warning("InfluxDB not available")
        return None
    
    try:
        query_api = get_query_api()
        
        # Build flux query - get all devices' magnitude values
        session_filter = f' and r.session == "{session}"' if session else ''
        
        flux = f'''from(bucket: "{INFLUX_BUCKET}")
            |> range(start: -100y)
            |> filter(fn: (r) => r._measurement == "accelerometer" and r.subject == "{subject_id}"{session_filter} and r._field == "magnitude")
            |> aggregateWindow(every: 5s, fn: mean, createEmpty: false)
            |> pivot(rowKey: ["_time"], columnKey: ["device"], valueColumn: "_value")
        '''
        
        df = query_api.query_data_frame(flux)
        
        if isinstance(df, list) and df:
            df = pd.concat(df, ignore_index=True)
        
        if df is None or df.empty:
            return None
        
        # Rename columns to match expected format
        col_mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'actigraph' in col_lower:
                col_mapping[col] = 'Actigraph'
            elif 'bangle' in col_lower:
                col_mapping[col] = 'Bangle'
            elif 'emotibit' in col_lower:
                col_mapping[col] = 'EmotiBit'
            elif col == '_time':
                col_mapping[col] = 'timestamp'
        
        df = df.rename(columns=col_mapping)
        
        # Merge duplicate columns resulting from case differences in device tags
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]
        
        # Keep only the columns we need
        keep_cols = ['timestamp'] + [c for c in ['Actigraph', 'Bangle', 'EmotiBit'] if c in df.columns]
        df = df[[c for c in keep_cols if c in df.columns]]
        
        if 'timestamp' in df.columns:
            df = df.set_index('timestamp')
        
        # Drop rows with any NaN (keep only overlapping windows)
        df = df.dropna()
        
        return df if not df.empty else None
        
    except Exception as e:
        logger.error(f"Error loading data from InfluxDB for {subject_id}: {e}")
        return None


def calculate_subject_correlation(subject_id: str, session: str = None) -> Dict[str, float]:
    """
    Calculate Pearson correlation between devices for a single subject.
    """
    df = load_aligned_data(subject_id, session)
    if df is None or df.empty or len(df) < 10:
        return {}
        
    results = {}
    
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        
        # Bangle vs Actigraph
        if 'Bangle' in df.columns and 'Actigraph' in df.columns:
            # Check for constant arrays (zero variance) before correlation
            if df['Bangle'].std() > 0 and df['Actigraph'].std() > 0:
                r, p = stats.pearsonr(df['Bangle'], df['Actigraph'])
                results['Bangle_Actigraph'] = r
            results['Bangle_Mean'] = df['Bangle'].mean()
            results['Actigraph_Mean'] = df['Actigraph'].mean()
            
        # EmotiBit vs Actigraph
        if 'EmotiBit' in df.columns and 'Actigraph' in df.columns:
            if df['EmotiBit'].std() > 0 and df['Actigraph'].std() > 0:
                r, p = stats.pearsonr(df['EmotiBit'], df['Actigraph'])
                results['EmotiBit_Actigraph'] = r
        
    return results


def get_cohort_analysis(session_filter: str = 'activity') -> pd.DataFrame:
    """
    Generate cohort-level analysis dataframe from InfluxDB.
    Columns: Subject, Age, Gender, BMI, r_Bangle_Actigraph, ...
    Accelerometer data is loaded from InfluxDB and demographics from local CSV.
    """
    global _cohort_cache
    if _cohort_cache is not None:
        return _cohort_cache
    # 1. Load demographics from local CSV
    demo_df = load_demographics()
    
    # 2. Use fixed subject roster to ensure full cohort accounting.
    subjects = COHORT_SUBJECTS
    
    # 3. Calculate correlations for all subjects
    corr_data = []
    for sub in subjects:
        # We only want to correlate the specific requested session (default: activity) to prevent rest data skewing metrics.
        corrs = calculate_subject_correlation(sub, session_filter)
        row = {'Subject': sub, 'Session': session_filter}
        row.update(corrs)
        corr_data.append(row)
            
    corr_df = pd.DataFrame(corr_data)
    
    # 4. Merge with demographics if available
    if not demo_df.empty and 'Subject' in demo_df.columns:
        full_df = pd.merge(demo_df, corr_df, on='Subject', how='right')
    else:
        full_df = corr_df
    
    _cohort_cache = full_df
    return _cohort_cache


def perform_subgroup_comparison(df: pd.DataFrame, group_col: str, metric_col: str = 'Bangle_Actigraph') -> Dict[str, Any]:
    """
    Compare correlation metric between groups (e.g. Male vs Female).
    Returns dict with stats and p-value.
    """
    if df.empty or group_col not in df.columns or metric_col not in df.columns:
        return {}
        
    groups = df.groupby(group_col)[metric_col]
    keys = list(groups.groups.keys())
    
    if len(keys) != 2:
        return {'error': 'Only binary comparison supported for now'}
        
    g1 = df[df[group_col] == keys[0]][metric_col]
    g2 = df[df[group_col] == keys[1]][metric_col]
    
    # Mann-Whitney U test
    try:
        stat, p = stats.mannwhitneyu(g1, g2)
    except Exception as e:
        logger.error(f"Mann-Whitney failed: {e}")
        return {'error': str(e)}
    
    return {
        'groups': keys,
        'means': [g1.mean(), g2.mean()],
        'medians': [g1.median(), g2.median()],
        'p_value': p,
        'u_stat': stat,
        'test': 'Mann-Whitney U'
    }

