"""
Device-specific data parsers for DIWAH wearable sensors.

This module provides parser classes for each device type:
- ActigraphParser: ActiGraph GT9X Link accelerometer (100Hz)
- BangleParser: Bangle.js 2 smartwatch (12.5Hz)
- EmotibitParser: EmotiBit biosensor (25Hz accelerometer)

All parsers are pure functions that accept file paths as parameters.
They do not depend on global configuration.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from ..constants import ACTIGRAPH_HEADER_LINES, EMOTIBIT_MAX_COLUMNS


class ActigraphParser:
    """Parser for ActiGraph GT9X Link accelerometer data."""
    
    @staticmethod
    def parse_raw_file(file_path: Path) -> pd.DataFrame:
        """
        Parse an ActiGraph RAW accelerometer file.
        
        Args:
            file_path: Path to the RAW.csv file
        
        Returns:
            DataFrame with columns: timestamp, acc_x, acc_y, acc_z, acc_magnitude
            
        Note:
            Supports both European format (semicolon separator, comma decimal)
            and US format (comma separator, period decimal).
        """
        # Skip header lines (first 11 lines are metadata including column names)
        # Use header=None since we rename columns anyway
        # Try European format first (semicolon separator, comma decimal)
        try:
            df = pd.read_csv(file_path, skiprows=ACTIGRAPH_HEADER_LINES, sep=';', decimal=',', header=None)
            if len(df.columns) == 4:  # Valid parse
                pass  # Use this df
            else:
                raise ValueError("Wrong column count, try different format")
        except (ValueError, pd.errors.ParserError):
            # Fall back to US format (comma separator, period decimal)
            df = pd.read_csv(file_path, skiprows=ACTIGRAPH_HEADER_LINES, header=None)
        
        # Rename columns
        df.columns = ['timestamp', 'acc_x', 'acc_y', 'acc_z']
        
        # Ensure numeric types
        df['acc_x'] = pd.to_numeric(df['acc_x'], errors='coerce')
        df['acc_y'] = pd.to_numeric(df['acc_y'], errors='coerce')
        df['acc_z'] = pd.to_numeric(df['acc_z'], errors='coerce')
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Calculate vector magnitude
        df['acc_magnitude'] = np.sqrt(
            df['acc_x']**2 + df['acc_y']**2 + df['acc_z']**2
        )
        
        return df


class BangleParser:
    """Parser for Bangle.js 2 smartwatch accelerometer data."""
    
    @staticmethod
    def parse_file(file_path: Path) -> pd.DataFrame:
        """
        Parse a Bangle.js accelerometer CSV file.
        
        Bangle records delta times between readings. This parser calculates
        cumulative time which can be aligned to a reference timestamp later.
        
        Args:
            file_path: Path to the CSV file
        
        Returns:
            DataFrame with columns: timestamp, Acc_x, Acc_y, Acc_z, acc_magnitude,
            cumulative_time_ms
        """
        df = pd.read_csv(file_path)
        
        # Ensure Time column is numeric
        df['Time'] = pd.to_numeric(df.get('Time'), errors='coerce')
        
        # Drop rows with invalid Time values
        df = df.dropna(subset=['Time'])
        
        if len(df) > 0:
            # All Time values are deltas in milliseconds
            # Cumulative sum gives elapsed time from start of recording
            df['cumulative_time_ms'] = df['Time'].cumsum()
            
            # Create a placeholder timestamp (will be replaced during alignment)
            df['timestamp'] = pd.to_datetime(df['cumulative_time_ms'], unit='ms', utc=True)
        else:
            df['cumulative_time_ms'] = pd.Series(dtype=float)
            df['timestamp'] = pd.Series(dtype='datetime64[ns]')
        
        # Ensure accelerometer columns are numeric
        df['Acc_x'] = pd.to_numeric(df.get('Acc_x'), errors='coerce')
        df['Acc_y'] = pd.to_numeric(df.get('Acc_y'), errors='coerce')
        df['Acc_z'] = pd.to_numeric(df.get('Acc_z'), errors='coerce')
        
        # Drop rows with invalid accelerometer values
        df = df.dropna(subset=['Acc_x', 'Acc_y', 'Acc_z'])
        
        # Calculate accelerometer vector magnitude
        df['acc_magnitude'] = np.sqrt(
            df['Acc_x']**2 + df['Acc_y']**2 + df['Acc_z']**2
        )
        
        return df


class EmotibitParser:
    """Parser for EmotiBit biosensor data."""
    
    @staticmethod
    def parse_info_json(json_path: Path) -> dict:
        """
        Parse EmotiBit info JSON file.
        
        Args:
            json_path: Path to the JSON info file
        
        Returns:
            Dictionary with device info
        """
        with open(json_path, 'r') as f:
            info = json.load(f)
        return info
    
    @staticmethod
    def parse_csv_file(file_path: Path) -> pd.DataFrame:
        """
        Parse EmotiBit raw CSV file.
        
        EmotiBit CSV files have variable columns per row, so we read
        line by line and normalize to a fixed structure.
        
        Args:
            file_path: Path to the CSV file
        
        Returns:
            DataFrame with columns: local_timestamp, emotibit_timestamp,
            data_length, type_tag, packet_number, reliability, data_0..data_13
        """
        data: List[List[Optional[str]]] = []
        
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                # Pad with None if needed
                while len(parts) < EMOTIBIT_MAX_COLUMNS:
                    parts.append(None)
                data.append(parts[:EMOTIBIT_MAX_COLUMNS])
        
        # Create dataframe
        base_cols = [
            'local_timestamp', 'emotibit_timestamp', 'data_length',
            'type_tag', 'packet_number', 'reliability'
        ]
        data_cols = [f'data_{i}' for i in range(14)]
        
        df = pd.DataFrame(data, columns=base_cols + data_cols)
        
        # Convert numeric columns
        df['local_timestamp'] = pd.to_numeric(df['local_timestamp'], errors='coerce')
        df['emotibit_timestamp'] = pd.to_numeric(df['emotibit_timestamp'], errors='coerce')
        df['data_length'] = pd.to_numeric(df['data_length'], errors='coerce')
        
        return df
    
    @staticmethod
    def extract_accelerometer(df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract accelerometer data from EmotiBit raw data.
        
        EmotiBit stores accelerometer data in separate rows for each axis
        (AX, AY, AZ type tags).
        
        Args:
            df: Raw EmotiBit DataFrame from parse_csv_file()
        
        Returns:
            DataFrame with columns: timestamp, acc_x, acc_y, acc_z, acc_magnitude
        """
        ax = df[df['type_tag'] == 'AX'].copy()
        ay = df[df['type_tag'] == 'AY'].copy()
        az = df[df['type_tag'] == 'AZ'].copy()
        
        # Combine into single dataframe
        # Note: data can have multiple values per row (data_length > 1)
        acc_data: List[Dict[str, Any]] = []
        
        for tag, data in [('x', ax), ('y', ay), ('z', az)]:
            for _, row in data.iterrows():
                try:
                    num_values = int(row['data_length']) if pd.notna(row['data_length']) else 1
                    timestamp = row['local_timestamp']
                    
                    for i in range(num_values):
                        col_name = f'data_{i}'
                        if col_name not in row.index or pd.isna(row[col_name]):
                            continue
                        
                        acc_data.append({
                            'timestamp': timestamp,
                            'axis': tag,
                            'value': float(row[col_name])
                        })
                except (ValueError, KeyError, TypeError) as exc:
                    # Skip malformed rows but log at debug level
                    continue
        
        if not acc_data:
            return pd.DataFrame(columns=['timestamp', 'acc_x', 'acc_y', 'acc_z', 'acc_magnitude'])
        
        acc_df = pd.DataFrame(acc_data)
        
        # Pivot to have x, y, z as columns
        acc_pivot = acc_df.pivot_table(
            index='timestamp',
            columns='axis',
            values='value',
            aggfunc='first'
        )
        acc_pivot.columns = ['acc_x', 'acc_y', 'acc_z']
        acc_pivot.reset_index(inplace=True)
        
        # Calculate magnitude
        acc_pivot['acc_magnitude'] = np.sqrt(
            acc_pivot['acc_x']**2 + 
            acc_pivot['acc_y']**2 + 
            acc_pivot['acc_z']**2
        )
        
        return acc_pivot


def calculate_magnitude_windows(
    df: pd.DataFrame,
    timestamp_col: str = 'timestamp',
    window: str = '5s'
) -> pd.DataFrame:
    """
    Resample accelerometer data into fixed time windows.
    
    Args:
        df: DataFrame with timestamp and acc_magnitude columns
        timestamp_col: Name of timestamp column
        window: Pandas resample window string (e.g., '5s', '1min')
    
    Returns:
        DataFrame with resampled mean magnitudes
    """
    df_copy = df.copy()
    df_copy.set_index(timestamp_col, inplace=True)
    
    result = df_copy['acc_magnitude'].resample(window).mean().reset_index()
    result.columns = [timestamp_col, 'acc_magnitude_5s']
    
    return result
