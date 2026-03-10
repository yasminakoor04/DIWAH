"""
Data loading and alignment utilities for DIWAH wearable sensor data.

This module provides functions to:
- Discover available subjects and sessions from raw data files
- Load and align accelerometer data from multiple devices (Actigraph, Bangle, Emotibit)
- Handle timestamp synchronization across devices with different sampling rates

Extracted from archive/create_dashboard.py to provide a clean, importable API.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

from src.backend.parsers import ActigraphParser, BangleParser, EmotibitParser
from src.backend.calorimetry_parser import CalorimetryParser
from src.config.paths import ACTIGRAPH_PATH, BANGLE_PATH, EMOTIBIT_PATH, DATA_ROOT
from src.constants import PARTICIPANT_MAPPING


def get_available_subjects_sessions() -> Dict[str, List[str]]:
    """
    Scan data directories to find all available subject/session combinations.
    
    Scans Bangle files as the primary source since they have consistent naming.
    
    Returns:
        Dict mapping subject IDs to lists of session types.
        Example: {'2002': ['activity', 'rest'], '2003': ['work']}
    """
    subjects_sessions: Dict[str, List[str]] = {}
    
    # Scan Bangle files (most reliable for subject/session combinations)
    bangle_files = list(BANGLE_PATH.glob("*.csv"))
    
    for file in bangle_files:
        # Parse filename like "2002_activity.csv"
        name = file.stem
        if '_' in name:
            subject, session = name.split('_', 1)
            
            # Filter out non-participants (e.g., malformed filenames or external datasets)
            if subject not in PARTICIPANT_MAPPING:
                continue
                
            if subject not in subjects_sessions:
                subjects_sessions[subject] = []
            if session not in subjects_sessions[subject]:
                subjects_sessions[subject].append(session)
    
    return subjects_sessions


def get_session_start_time(subject_id: str, session_type: str, device: str) -> Optional[datetime]:
    """
    Extract session start time from device-specific file metadata.
    
    Currently only implemented for Emotibit, which embeds timestamps in filenames.
    
    Args:
        subject_id: Subject identifier (e.g., '2002')
        session_type: Session type (e.g., 'activity', 'rest')
        device: Device name ('emotibit', 'actigraph', 'bangle')
    
    Returns:
        datetime of session start, or None if not determinable
    """
    if device == 'emotibit':
        emotibit_dir = EMOTIBIT_PATH / f"{subject_id}_{session_type}"
        if emotibit_dir.exists():
            csv_files = list(emotibit_dir.glob("*.csv"))
            if csv_files:
                filename = csv_files[0].stem
                try:
                    # Emotibit filenames: "2024-01-15_10-30-45-something.csv"
                    date_str = filename.rsplit('-', 1)[0]
                    dt = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
                    return dt
                except (ValueError, IndexError):
                    pass
    return None


def load_and_align_data(
    subject_id: str, 
    session_type: str
) -> Tuple[Dict[str, pd.DataFrame], Optional[pd.Timestamp]]:
    """
    Load and temporally align accelerometer data from all available devices.
    
    Loads data from Actigraph, Bangle, and Emotibit devices for a given subject
    and session. Uses Actigraph's timestamp as the reference for alignment since
    it has absolute timestamps. Bangle and Emotibit timestamps are adjusted
    relative to this reference.
    
    Args:
        subject_id: Subject identifier (e.g., '2002')
        session_type: Session type (e.g., 'activity', 'rest')
    
    Returns:
        Tuple of:
        - Dict mapping device names to DataFrames with aligned timestamps
        - Reference timestamp used for alignment (from Actigraph), or None
        
    Note:
        Each DataFrame contains at minimum: 'timestamp', 'acc_x', 'acc_y', 'acc_z', 
        'acc_magnitude', 'device' columns. Column names may vary by device parser.
    """
    aligned_data: Dict[str, pd.DataFrame] = {}
    reference_time: Optional[pd.Timestamp] = None
    
    # 1. Load Actigraph (100Hz, absolute timestamps)
    actigraph_pattern = f"{subject_id}*RAW.csv"
    actigraph_files = list(ACTIGRAPH_PATH.glob(actigraph_pattern))
    
    if actigraph_files:
        # Prefer smaller files (avoid extremely large recordings)
        acti_file = None
        for f in actigraph_files:
            if f.stat().st_size < 50 * 1024 * 1024:  # < 50MB
                acti_file = f
                break
        if not acti_file and actigraph_files:
            acti_file = actigraph_files[0]
        
        if acti_file:
            df_acti = ActigraphParser.parse_raw_file(acti_file)
            reference_time = df_acti['timestamp'].min()
            df_acti['device'] = 'Actigraph'
            aligned_data['actigraph'] = df_acti
    
    # 2. Load Bangle (12.5Hz, relative timestamps as cumulative ms)
    bangle_file = BANGLE_PATH / f"{subject_id}_{session_type}.csv"
    if bangle_file.exists():
        df_bangle = BangleParser.parse_file(bangle_file)
        
        # Bangle records delta times, align to reference time (Actigraph)
        if reference_time is not None and 'cumulative_time_ms' in df_bangle.columns:
            df_bangle['timestamp'] = reference_time + pd.to_timedelta(
                df_bangle['cumulative_time_ms'], unit='ms'
            )
        
        df_bangle['device'] = 'Bangle'
        aligned_data['bangle'] = df_bangle
    
    # 3. Load Emotibit (25Hz, timestamps from filename or relative)
    emotibit_dir = EMOTIBIT_PATH / f"{subject_id}_{session_type}"
    if emotibit_dir.exists():
        csv_files = list(emotibit_dir.glob("*.csv"))
        if csv_files:
            df_emoti_raw = EmotibitParser.parse_csv_file(csv_files[0])
            df_emoti = EmotibitParser.extract_accelerometer(df_emoti_raw)
            
            # Try to get start time from filename
            emotibit_start = get_session_start_time(subject_id, session_type, 'emotibit')
            
            if emotibit_start:
                df_emoti['timestamp'] = emotibit_start + pd.to_timedelta(
                    df_emoti['timestamp'] - df_emoti['timestamp'].min(), unit='ms'
                )
            elif reference_time is not None:
                df_emoti['timestamp'] = reference_time + pd.to_timedelta(
                    df_emoti['timestamp'] - df_emoti['timestamp'].min(), unit='ms'
                )
            
            df_emoti['device'] = 'Emotibit'
            aligned_data['emotibit'] = df_emoti
            
    # 4. Load Calorimetry Data (Ground Truth Heart Rate and METS)
    calorimetry_file = DATA_ROOT / 'calorimetry_anonymized' / f"{subject_id}_{session_type}.xls"
    if calorimetry_file.exists():
        df_calorimetry = CalorimetryParser.parse_file(calorimetry_file)
        if not df_calorimetry.empty and reference_time is not None:
             # Convert relative 'Time_s' elapsed since start to absolute timestamps
             df_calorimetry['timestamp'] = reference_time + pd.to_timedelta(df_calorimetry['Time_s'], unit='s')
             df_calorimetry['device'] = 'Calorimetry'
             aligned_data['calorimetry'] = df_calorimetry
    
    return aligned_data, reference_time


def aggregate_to_windows(
    df: pd.DataFrame, 
    window_seconds: int = 5,
    timestamp_col: str = 'timestamp', 
    value_col: str = 'acc_magnitude'
) -> pd.DataFrame:
    """
    Aggregate accelerometer data into fixed-size time windows.
    
    Args:
        df: DataFrame with timestamp and value columns
        window_seconds: Window size in seconds (default: 5)
        timestamp_col: Name of timestamp column
        value_col: Name of value column to aggregate
    
    Returns:
        DataFrame with columns: timestamp, {value_col}_mean, {value_col}_std, sample_count
    """
    if timestamp_col not in df.columns:
        return df
    
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        return df
    
    df_copy = df.copy()
    df_copy.set_index(timestamp_col, inplace=True)
    
    window_str = f'{window_seconds}s'
    result = df_copy[value_col].resample(window_str).agg(['mean', 'std', 'count']).reset_index()
    result.columns = [timestamp_col, f'{value_col}_mean', f'{value_col}_std', 'sample_count']
    result = result[result['sample_count'] > 0]
    
    return result
