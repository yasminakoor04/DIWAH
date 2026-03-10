"""
Data Quality Module for DIWAH Dashboard.

Identifies and flags subjects with poor quality data based on:
1. Correlation threshold (r < 0.50)
2. Average magnitude threshold (must be > 1.0 to indicate activity)
"""

from typing import Dict, List, Set, Any
import pandas as pd
import logging

from .correlation import get_cohort_analysis, load_aligned_data

logger = logging.getLogger(__name__)

# Quality thresholds
CORRELATION_THRESHOLD = 0.50  # Below this = bad correlation
MAGNITUDE_THRESHOLD = 1.0     # Must be above 1g to indicate meaningful activity


# Known bad subjects with reason codes
BAD_SUBJECTS_REGISTRY: Dict[str, str] = {
    "2003": "Negative correlation (r = -0.06) - timestamps likely misaligned",
    "2006": "Very low correlation (r = 0.14) - possible sensor malfunction",
    "2025": "Very low correlation (r = 0.09) - large Actigraph/Bangle mismatch",
    "2032": "Low correlation (r = 0.23) - significant measurement discrepancy",
}


def get_bad_subjects() -> Set[str]:
    """Return set of subject IDs flagged as bad data."""
    return set(BAD_SUBJECTS_REGISTRY.keys())


def get_bad_subject_reasons() -> Dict[str, str]:
    """Return dictionary of bad subjects with their reason descriptions."""
    return BAD_SUBJECTS_REGISTRY.copy()


def assess_subject_quality(subject_id: str) -> Dict[str, Any]:
    """
    Assess data quality for a single subject.
    
    Returns dict with:
        - is_good: bool
        - correlation: float
        - bangle_avg: float
        - actigraph_avg: float
        - flags: list of issue descriptions
    """
    result = {
        "subject_id": subject_id,
        "is_good": True,
        "correlation": None,
        "bangle_avg": None,
        "actigraph_avg": None,
        "flags": []
    }
    
    # Get correlation from cohort data
    cohort_df = get_cohort_analysis()
    if cohort_df.empty:
        result["is_good"] = False
        result["flags"].append("No cohort data available")
        return result
    
    subject_row = cohort_df[cohort_df["Subject"] == str(subject_id)]
    if subject_row.empty:
        result["is_good"] = False
        result["flags"].append("Subject not found in cohort")
        return result
    
    r = subject_row["Bangle_Actigraph"].values[0]
    result["correlation"] = r
    
    # Check correlation threshold
    if r < CORRELATION_THRESHOLD:
        result["is_good"] = False
        result["flags"].append(f"Low correlation (r = {r:.2f} < {CORRELATION_THRESHOLD})")
    
    # Check magnitude averages
    bangle_avg = subject_row.get("Bangle_Mean", pd.Series([None])).values[0]
    acti_avg = subject_row.get("Actigraph_Mean", pd.Series([None])).values[0]
    
    if pd.notna(bangle_avg):
        result["bangle_avg"] = bangle_avg
        if bangle_avg <= MAGNITUDE_THRESHOLD:
            result["is_good"] = False
            result["flags"].append(f"Low Bangle average ({bangle_avg:.2f}g ≤ {MAGNITUDE_THRESHOLD}g)")
            
    if pd.notna(acti_avg):
        result["actigraph_avg"] = acti_avg
        if acti_avg <= MAGNITUDE_THRESHOLD:
            result["is_good"] = False
            result["flags"].append(f"Low Actigraph average ({acti_avg:.2f}g ≤ {MAGNITUDE_THRESHOLD}g)")
    
    # Fallback to loading data if means aren't in cohort_df
    if pd.isna(bangle_avg) or pd.isna(acti_avg):
        aligned = load_aligned_data(subject_id)
        if aligned is not None and not aligned.empty:
            if "Bangle" in aligned.columns and pd.isna(bangle_avg):
                bangle_avg = aligned["Bangle"].mean()
                result["bangle_avg"] = bangle_avg
                if bangle_avg <= MAGNITUDE_THRESHOLD:
                    result["is_good"] = False
                    result["flags"].append(f"Low Bangle average ({bangle_avg:.2f}g ≤ {MAGNITUDE_THRESHOLD}g)")
            
            if "Actigraph" in aligned.columns and pd.isna(acti_avg):
                acti_avg = aligned["Actigraph"].mean()
                result["actigraph_avg"] = acti_avg
                if acti_avg <= MAGNITUDE_THRESHOLD:
                    result["is_good"] = False
                    result["flags"].append(f"Low Actigraph average ({acti_avg:.2f}g ≤ {MAGNITUDE_THRESHOLD}g)")
    
    return result


def filter_good_subjects(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter cohort DataFrame to include only good quality subjects.
    
    Args:
        df: DataFrame with 'Subject' and 'Bangle_Actigraph' columns
        
    Returns:
        Filtered DataFrame with bad subjects removed
    """
    if df.empty:
        return df
    
    bad_subjects = get_bad_subjects()
    
    # Filter by registry
    filtered = df[~df["Subject"].astype(str).isin(bad_subjects)]
    
    # Also filter by correlation threshold (catches any not in registry)
    if "Bangle_Actigraph" in filtered.columns:
        filtered = filtered[filtered["Bangle_Actigraph"] >= CORRELATION_THRESHOLD]
        
    # Also filter by magnitude threshold
    if "Bangle_Mean" in filtered.columns:
        filtered = filtered[filtered["Bangle_Mean"] > MAGNITUDE_THRESHOLD]
    if "Actigraph_Mean" in filtered.columns:
        filtered = filtered[filtered["Actigraph_Mean"] > MAGNITUDE_THRESHOLD]
    
    return filtered


def get_quality_summary() -> Dict[str, Any]:
    """
    Get summary statistics for data quality across cohort.
    
    Returns:
        Dict with counts and percentages
    """
    cohort_df = get_cohort_analysis()
    if cohort_df.empty:
        return {"total": 0, "good": 0, "bad": 0, "good_pct": 0}
    
    total = len(cohort_df)
    
    # Dynamically find all bad subjects
    static_bad = set(BAD_SUBJECTS_REGISTRY.keys())
    bad_mask = cohort_df["Subject"].astype(str).isin(static_bad)
    
    if "Bangle_Actigraph" in cohort_df.columns:
        bad_mask |= (cohort_df["Bangle_Actigraph"] < CORRELATION_THRESHOLD)
        
    if "Bangle_Mean" in cohort_df.columns:
        bad_mask |= (cohort_df["Bangle_Mean"] <= MAGNITUDE_THRESHOLD)
        
    if "Actigraph_Mean" in cohort_df.columns:
        bad_mask |= (cohort_df["Actigraph_Mean"] <= MAGNITUDE_THRESHOLD)
        
    dynamic_bad_subjects = set(cohort_df[bad_mask]["Subject"].astype(str))
    
    bad_count = len(dynamic_bad_subjects)
    good_count = total - bad_count
    
    return {
        "total": total,
        "good": good_count,
        "bad": bad_count,
        "good_pct": (good_count / total * 100) if total > 0 else 0,
        "bad_subjects": list(dynamic_bad_subjects),
        "correlation_threshold": CORRELATION_THRESHOLD,
        "magnitude_threshold": MAGNITUDE_THRESHOLD
    }
