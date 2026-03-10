import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class CalorimetryParser:
    """Parser for Calorimetry data files explicitly exported as TSV but ending in .xls"""
    
    @staticmethod
    def parse_file(file_path: Path) -> pd.DataFrame:
        """
        Parses a calorimetry file and extracts Heart Rate (HR) and METS perfectly aligned with Time (Tid).
        
        Args:
            file_path: Path to the calorimetry .xls file
            
        Returns:
            DataFrame with Time (seconds), HR, and METS.
        """
        try:
            # Calorimetry files often contain non-UTF-8 characters in their intro headers (e.g. Swedish "Ö" or "Å")
            with open(file_path, 'r', encoding='latin1') as f:
                lines = f.readlines()
                
            # Find the header row dynamically
            start_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('Tid'):
                    start_idx = i
                    break
                    
            if start_idx == 0:
                logger.warning(f"Could not find 'Tid' header in {file_path}")
                return pd.DataFrame()
                
            # Load the TSV file using pandas
            df = pd.read_csv(file_path, delimiter='\t', skiprows=start_idx, encoding='latin1', keep_default_na=False)
            
            # The row immediately after the header contains units (e.g., "min", "1/min"), drop it
            df = df.drop(0).reset_index(drop=True)
            
            # Ensure required columns exist
            required_cols = ['Tid', 'HR', 'METS']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                logger.error(f"Missing expected columns in {file_path}: {missing_cols}")
                return pd.DataFrame()
            
            # Filter to required columns
            df = df[['Tid', 'HR', 'METS']]
            
            # Convert 'Tid' (MM:SS or HH:MM:SS) to total seconds elapsed
            def _time_to_seconds(tid_str: str) -> float:
                try:
                    parts = str(tid_str).strip().split(':')
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 3:
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    return float('nan')
                except Exception:
                    return float('nan')
                    
            df['Time_s'] = df['Tid'].apply(_time_to_seconds)
            
            # Drop invalid times
            df = df.dropna(subset=['Time_s'])
            
            # Convert HR and METS to numeric safely
            df['HR'] = pd.to_numeric(df['HR'], errors='coerce')
            df['METS'] = pd.to_numeric(df['METS'], errors='coerce')
            
            # Return strictly Time and the Targets
            return df[['Time_s', 'HR', 'METS']]
            
        except Exception as e:
            logger.error(f"Error parsing calorimetry file {file_path}: {e}")
            return pd.DataFrame()
