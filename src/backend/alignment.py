import pandas as pd
import numpy as np
from pathlib import Path
import logging
from typing import Dict, Optional, Tuple, List
import shutil

from .parsers import ActigraphParser, BangleParser, EmotibitParser
from .calorimetry_parser import CalorimetryParser
from ..config import START_LINES_FILE, DATA_ROOT

logger = logging.getLogger(__name__)

# Manual time shifts (in seconds) to apply to Bangle to fix timestamp misalignments
MANUAL_BANGLE_SHIFTS = {
    '2010': 25,   # +25 seconds
    '2020': 100,  # +100 seconds
    '2027': 90,   # +90 seconds
    '2035': 90    # +90 seconds
}

def auto_detect_activity_start(df: pd.DataFrame, threshold: float = 1.1, window: int = 50) -> Tuple[int, Optional[pd.Timestamp]]:
    """
    Auto-detect the start of activity period based on accelerometer magnitude.
    """
    if 'acc_magnitude' not in df.columns or df.empty:
        return 0, df.iloc[0]['timestamp'] if not df.empty else None
    
    # Rolling std dev to find variability change
    rolling_std = df['acc_magnitude'].rolling(window=window, min_periods=1).std()
    
    # Check for magnitude spikes OR high variability
    high_mag_mask = df['acc_magnitude'] > threshold
    high_std_mask = rolling_std > 0.03
    
    activity_mask = high_mag_mask | high_std_mask
    
    if activity_mask.any():
        activity_start_idx = activity_mask.idxmax()
        # Back up a bit to capture the start
        adjusted_idx = max(0, activity_start_idx - window // 4)
        return adjusted_idx, df.iloc[adjusted_idx]['timestamp']
    
    return 0, df.iloc[0]['timestamp']

class AlignmentPipeline:
    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.start_lines = self._load_start_lines()
        
    def _load_start_lines(self) -> Dict[str, int]:
        """Load Actigraph start line indices from CSV."""
        if not START_LINES_FILE.exists():
            logger.warning(f"Start lines file not found: {START_LINES_FILE}")
            return {}
        try:
            df = pd.read_csv(START_LINES_FILE)
            # Ensure columns exist. Valid names: Subject, AccelerometerStart
            if 'Subject' in df.columns and 'AccelerometerStart' in df.columns:
                 return dict(zip(df['Subject'].astype(str), df['AccelerometerStart']))
            return {}
        except Exception as e:
            logger.error(f"Error loading start lines: {e}")
            return {}

    def get_actigraph_start_time(self, df: pd.DataFrame, subject_id: str) -> Optional[pd.Timestamp]:
        """
        Get start time using lookup table (primary) or auto-detection (fallback).
        """
        line_index = self.start_lines.get(str(subject_id))
        
        # Actigraph header usually 10-11 lines. 
        # Line index in file includes header. Dataframe is just data.
        # Approximation: data_index = line_index - 11 (approx)
        
        if line_index and line_index > 100:
            # It's a valid manual entry
            # Convert line number to approximate dataframe index
            # This is heuristic; better is to use timestamp if we had it, but we have line index.
            # Assuming parser skips header.
            # Let's trust auto-detection for refinement if manual is vague?
            # User requirement: "Skip to line index from lookup table"
            
            # Implementation:
            # We need to map file line number to DF index.
            # Only ActigraphParser knows the header length exactly.
            # Let's assume header is ~10 lines.
            idx = max(0, line_index - 11) 
            if idx < len(df):
                return df.iloc[idx]['timestamp']
        
        # Fallback to auto-detection
        logger.info(f"Using auto-detection for {subject_id}")
        _, timestamp = auto_detect_activity_start(df)
        return timestamp

    def detect_end_time(self, df: pd.DataFrame) -> Optional[pd.Timestamp]:
        """
        Detect end of activity: drop in magnitude/variance.
        """
        if df.empty: return None
        
        # Reverse the dataframe to find the "end" (which is start of rest from the back)
        # Or look for long period of low variance.
        
        # Simple approach: Find last index where activity was high
        rolling_std = df['acc_magnitude'].rolling(window=50, min_periods=1).std()
        activity_mask = (df['acc_magnitude'] > 1.05) | (rolling_std > 0.02)
        
        if activity_mask.any():
            last_activity_idx = activity_mask[::-1].idxmax() # Last True
            return df.loc[last_activity_idx, 'timestamp']
        
        return df.iloc[-1]['timestamp']

    def find_subject_files(self, subject_id: str, session: str = "activity") -> Dict[str, Optional[Path]]:
        """
        Locate raw data files for a subject across device directories.
        
        Args:
            subject_id: Subject identifier
            session: Session type - "activity" or "rest"
        """
        files = {'Actigraph': None, 'Bangle': None, 'EmotiBit': None, 'Calorimetry': None}
        
        # 1. Actigraph - same file for both sessions (we clip differently based on session)
        # Pattern: {subject_id} (...)RAW.csv
        act_dir = self.data_dir / "Actigraph (research device accelerometry)"
        if act_dir.exists():
            # Try to match start of filename
            matches = list(act_dir.glob(f"{subject_id}*RAW.csv"))
            if matches:
                files['Actigraph'] = matches[0]
                
        # 2. Bangle
        # Pattern: {subject_id}_activity.csv or {subject_id}_rest.csv
        bangle_dir = self.data_dir / "Bangle"
        if bangle_dir.exists():
            if session == "activity":
                patterns = [
                    f"{subject_id}_activity.csv",
                    f"{subject_id}_work.csv",
                    f"{subject_id}_activitet.csv",  # typo seen in list
                    f"{subject_id}*activity*.csv"   # fallback
                ]
            else:  # rest
                patterns = [
                    f"{subject_id}_rest.csv",
                    f"{subject_id}_vila.csv",  # Swedish for rest
                    f"{subject_id}*rest*.csv"  # fallback
                ]
            for pat in patterns:
                matches = list(bangle_dir.glob(pat))
                if matches:
                    files['Bangle'] = matches[0]
                    break
                    
        # 3. EmotiBit
        # Pattern: Folder {subject_id}_activity or {subject_id}_rest -> CSV inside
        emoti_dir = self.data_dir / "emotibit"
        if emoti_dir.exists():
            if session == "activity":
                folder_patterns = [
                    f"{subject_id}_activity",
                    f"{subject_id}_work",
                    f"{subject_id}_activitet"
                ]
            else:  # rest
                folder_patterns = [
                    f"{subject_id}_rest",
                    f"{subject_id}_vila"
                ]
            target_folder = None
            for pat in folder_patterns:
                matches = list(emoti_dir.glob(pat))
                if matches:
                    target_folder = matches[0]
                    break
            
            if target_folder:
                # Find CSV inside
                csvs = list(target_folder.glob("*.csv"))
                if csvs:
                    files['EmotiBit'] = csvs[0]
                    
        # 4. Calorimetry - only for activity sessions (no calorimetry during rest)
        if session == "activity":
            calo_dir = self.data_dir / "calorimetry_anonymized"
            if calo_dir.exists():
                calo_matches = list(calo_dir.glob(f"{subject_id}_*.xls"))
                if calo_matches:
                    files['Calorimetry'] = calo_matches[0]
                    
        return files

    def process_subject(self, subject_id: str):
        """Process both activity and rest sessions for a subject."""
        logger.info(f"Processing subject {subject_id}...")
        
        # Process activity session
        self.process_subject_session(subject_id, "activity")
        
        # Process rest session
        self.process_subject_session(subject_id, "rest")
    
    def process_subject_session(self, subject_id: str, session: str):
        """Process a single session (activity or rest) for a subject."""
        logger.info(f"  Processing {session} session...")
        
        # Locate files for this session
        files = self.find_subject_files(subject_id, session)
        
        # For rest sessions, we don't require Actigraph - Bangle/EmotiBit can stand alone
        has_data = files['Bangle'] or files['EmotiBit'] or files['Actigraph']
        if not has_data:
            logger.info(f"  No {session} data files found for {subject_id}")
            return

        aligned_out_dir = self.output_dir / subject_id / session
        aligned_out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Load Data
        act_df = None
        bangle_df = None
        emotibit_df = None
        
        try:
            if files['Actigraph']:
                logger.info(f"  Parsing Actigraph: {files['Actigraph'].name}")
                act_df = ActigraphParser.parse_raw_file(files['Actigraph'])
                
            if files['Bangle']:
                logger.info(f"  Parsing Bangle: {files['Bangle'].name}")
                bangle_df = BangleParser.parse_file(files['Bangle'])
                
            if files['EmotiBit']:
                logger.info(f"  Parsing EmotiBit: {files['EmotiBit'].name}")
                # Parse raw CSV then extract accelerometer
                raw_emoti = EmotibitParser.parse_csv_file(files['EmotiBit'])
                emotibit_df = EmotibitParser.extract_accelerometer(raw_emoti)
                
            if files['Calorimetry']:
                logger.info(f"  Parsing Calorimetry: {files['Calorimetry'].name}")
                calorimetry_df = CalorimetryParser.parse_file(files['Calorimetry'])
                
        except Exception as e:
            logger.error(f"Failed to parse {subject_id} {session}: {e}")
            return # Don't crash entire pipeline

        frames = {}
        common_start = None
        common_end = None
        
        # 2. Determine Common Window
        if act_df is not None and not act_df.empty:
            # Activity sessions: Use Actigraph as reference
            start_time = self.get_actigraph_start_time(act_df, subject_id)
            if not start_time:
                start_time = act_df.iloc[0]['timestamp']
                
            end_time = self.detect_end_time(act_df)
            if not end_time:
                end_time = act_df.iloc[-1]['timestamp']
                
            logger.info(f"  Actigraph Window: {start_time} - {end_time}")
            
            act_clipped = act_df[(act_df['timestamp'] >= start_time) & (act_df['timestamp'] <= end_time)].copy()
            if not act_clipped.empty:
                frames['Actigraph'] = act_clipped
                
            common_start = start_time
            common_end = end_time
        elif session == "rest":
            # Rest sessions without Actigraph: Use Bangle/EmotiBit timestamps directly
            logger.info(f"  Rest session - no Actigraph reference, using device timestamps")
        else:
            # Activity session requires Actigraph
            logger.error(f"No valid Actigraph data for {subject_id}")
            return
        
        # 3. Align Other Devices
        if 'calorimetry_df' in locals() and calorimetry_df is not None and not calorimetry_df.empty and common_start:
            try:
                # Calorimetry timestamps are relative to start in seconds
                calorimetry_df['timestamp'] = pd.Timestamp(common_start) + pd.to_timedelta(calorimetry_df['Time_s'], unit='s')
                c_clipped = calorimetry_df[(calorimetry_df['timestamp'] >= common_start) & (calorimetry_df['timestamp'] <= common_end)].copy()
                if not c_clipped.empty:
                    frames['Calorimetry'] = c_clipped
            except Exception as e:
                logger.error(f"  Failed to align Calorimetry timestamps: {e}")
                
        if bangle_df is not None and not bangle_df.empty:
            if 'cumulative_time_ms' in bangle_df.columns:
                try:
                    if common_start is not None:
                        # Activity: Align Bangle start to Actigraph start
                        logger.info("  Aligning Bangle start to Actigraph start")
                        start_ts = pd.Timestamp(common_start)
                        
                        if pd.isna(start_ts):
                            raise ValueError("Invalid start time")

                        # Apply manual shift if configured (only for activity)
                        if session == "activity" and subject_id in MANUAL_BANGLE_SHIFTS:
                            shift_seconds = MANUAL_BANGLE_SHIFTS[subject_id]
                            logger.info(f"  Applying MANUAL BANGLE SHIFT: +{shift_seconds} seconds")
                            start_ts += pd.Timedelta(seconds=shift_seconds)

                        timedeltas = pd.to_timedelta(bangle_df['cumulative_time_ms'], unit='ms')
                        bangle_df['timestamp'] = pd.to_datetime(start_ts + timedeltas, errors='coerce')
                    else:
                        # Rest: Use Bangle's native timestamps (cumulative from file start)
                        logger.info("  Rest session: Using Bangle native timestamps")
                        # Create timestamps starting from a reference point (use file parsing time or epoch)
                        timedeltas = pd.to_timedelta(bangle_df['cumulative_time_ms'], unit='ms')
                        # Use a reference start time - first sample at epoch + cumulative
                        base_time = pd.Timestamp('2024-01-01')  # Arbitrary reference for rest data
                        bangle_df['timestamp'] = pd.to_datetime(base_time + timedeltas, errors='coerce')
                        
                except Exception as e:
                    logger.error(f"  Failed to align Bangle timestamps: {e}")
                    if 'timestamp' not in bangle_df.columns:
                        bangle_df = None

            # Filter to window (only if we have a common window)
            if bangle_df is not None and common_start is not None and common_end is not None:
                ts_start = pd.Timestamp(common_start)
                ts_end = pd.Timestamp(common_end)
                
                if not pd.isna(ts_start) and not pd.isna(ts_end):
                    if bangle_df['timestamp'].dtype == object:
                        bangle_df['timestamp'] = pd.to_datetime(bangle_df['timestamp'], errors='coerce')
                     
                    bangle_df = bangle_df.dropna(subset=['timestamp'])
                    try:
                        mask = (bangle_df['timestamp'] >= ts_start) & (bangle_df['timestamp'] <= ts_end)
                        b_clipped = bangle_df[mask].copy()
                        if not b_clipped.empty:
                            frames['Bangle'] = b_clipped
                    except Exception as e:
                        logger.error(f"  Failed to filter Bangle: {e}")
            elif bangle_df is not None and 'timestamp' in bangle_df.columns:
                # Rest session without Actigraph - use all Bangle data
                bangle_df = bangle_df.dropna(subset=['timestamp'])
                if not bangle_df.empty:
                    frames['Bangle'] = bangle_df.copy()

            
        if emotibit_df is not None and not emotibit_df.empty:
            try:
                # EmotiBit timestamp is numeric (Unix time), convert to datetime
                if pd.api.types.is_numeric_dtype(emotibit_df['timestamp']):
                    emotibit_df['timestamp'] = pd.to_datetime(emotibit_df['timestamp'], unit='s')
                
                if common_start is not None and common_end is not None:
                    # Activity: Clip to common window
                    e_clipped = emotibit_df[(emotibit_df['timestamp'] >= common_start) & (emotibit_df['timestamp'] <= common_end)].copy()
                    if not e_clipped.empty:
                        frames['EmotiBit'] = e_clipped
                else:
                    # Rest: Use all EmotiBit data
                    emotibit_df = emotibit_df.dropna(subset=['timestamp'])
                    if not emotibit_df.empty:
                        frames['EmotiBit'] = emotibit_df.copy()
            except Exception as e:
                logger.error(f"  Failed to process EmotiBit: {e}")

        # Check if we have any data to save
        if not frames:
            logger.warning(f"  No data frames to save for {subject_id} {session}")
            return

        # 4. Resample (5s) & Save
        logger.info(f"  Saving {len(frames)} device(s): {list(frames.keys())}")
        for device, df in frames.items():
            if df.empty: 
                logger.warning(f"  {device} data empty after clipping.")
                continue
            
            # Resample to 5s
            df.set_index('timestamp', inplace=True)
            try:
                # Calorimetry has HR and METS, other devices have acc_magnitude
                if device == 'Calorimetry':
                    resampled = df[['HR', 'METS']].resample('5s').mean().reset_index()
                else:
                    resampled = df['acc_magnitude'].resample('5s').mean().reset_index()
                    resampled.rename(columns={'acc_magnitude': 'acc_magnitude_5s'}, inplace=True)
                
                # Save - files go into session-specific subdirectory
                out_file = aligned_out_dir / f"{device}_aligned_5s.csv"
                resampled.to_csv(out_file, index=False)
                logger.info(f"    Saved: {out_file.name} ({len(resampled)} rows)")
            except Exception as e:
                logger.error(f"  Failed to resample {device}: {e}")


