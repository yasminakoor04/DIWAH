"""
Data Quality Module for DIWAH Dashboard.

Quality status is controlled by a manual registry of excluded subjects.
No dynamic threshold-based filtering is applied.
"""

from typing import Dict, List, Set, Any
import pandas as pd
import logging

from .correlation import COHORT_SUBJECTS, get_cohort_analysis, load_aligned_data

logger = logging.getLogger(__name__)

# Known bad subjects with reason codes
BAD_SUBJECTS_REGISTRY: Dict[str, str] = {
    "2004": "Manual exclusion: untrimmed raw epochs retained for visual QA",
    "2005": "Manual exclusion: untrimmed raw epochs retained for visual QA",
    "2008": "Manual exclusion: untrimmed raw epochs retained for visual QA",
    "2014": "Manual exclusion: untrimmed raw epochs retained for visual QA",
    "2019": "Manual exclusion: untrimmed raw epochs retained for visual QA",
    "2032": "Manual exclusion: untrimmed raw epochs retained for visual QA",
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
    
    # Populate average values for diagnostics only.
    bangle_avg = subject_row.get("Bangle_Mean", pd.Series([None])).values[0]
    acti_avg = subject_row.get("Actigraph_Mean", pd.Series([None])).values[0]
    
    if pd.notna(bangle_avg):
        result["bangle_avg"] = bangle_avg
            
    if pd.notna(acti_avg):
        result["actigraph_avg"] = acti_avg
    
    # Fallback to loading data if means aren't in cohort_df
    if pd.isna(bangle_avg) or pd.isna(acti_avg):
        aligned = load_aligned_data(subject_id)
        if aligned is not None and not aligned.empty:
            if "Bangle" in aligned.columns and pd.isna(bangle_avg):
                bangle_avg = aligned["Bangle"].mean()
                result["bangle_avg"] = bangle_avg
            
            if "Actigraph" in aligned.columns and pd.isna(acti_avg):
                acti_avg = aligned["Actigraph"].mean()
                result["actigraph_avg"] = acti_avg

    if str(subject_id) in BAD_SUBJECTS_REGISTRY:
        result["is_good"] = False
        result["flags"].append(BAD_SUBJECTS_REGISTRY[str(subject_id)])
    
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
    return df[~df["Subject"].astype(str).isin(bad_subjects)]


def get_quality_summary() -> Dict[str, Any]:
    """
    Get summary statistics for data quality across cohort.
    
    Returns:
        Dict with counts and percentages
    """
    cohort_df = get_cohort_analysis()
    if cohort_df.empty:
        total = len(COHORT_SUBJECTS)
        bad_subjects = sorted(BAD_SUBJECTS_REGISTRY.keys())
        bad_count = len(bad_subjects)
        good_count = total - bad_count
        return {
            "total": total,
            "good": good_count,
            "bad": bad_count,
            "good_pct": (good_count / total * 100) if total > 0 else 0,
            "bad_subjects": bad_subjects
        }
    
    all_subjects = set(cohort_df["Subject"].astype(str))
    bad_subjects = sorted(s for s in BAD_SUBJECTS_REGISTRY.keys() if s in all_subjects)

    total = len(all_subjects)
    bad_count = len(bad_subjects)
    good_count = total - bad_count
    
    return {
        "total": total,
        "good": good_count,
        "bad": bad_count,
        "good_pct": (good_count / total * 100) if total > 0 else 0,
        "bad_subjects": bad_subjects
    }
