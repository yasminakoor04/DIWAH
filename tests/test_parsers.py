"""
Unit tests for DIWAH device parsers.

Tests the parser classes for ActiGraph, Bangle, and EmotiBit devices.
Uses fixtures to create sample data files for testing.
"""

import pytest
import pandas as pd
import numpy as np
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backend.parsers import (
    ActigraphParser,
    BangleParser,
    EmotibitParser,
    calculate_magnitude_windows
)
from src.constants import ACTIGRAPH_HEADER_LINES


class TestActigraphParser:
    """Tests for ActigraphParser class."""
    
    @pytest.fixture
    def sample_actigraph_file(self, tmp_path):
        """Create a sample ActiGraph RAW CSV file."""
        # ActiGraph files have 11 header lines (metadata + column names)
        # The parser skips all 11, so line 12 (index 11) is first data
        header_lines = [
            "------------ Data File Created By ActiGraph GT9X Link ActiLife v6.13.4 Firmware v1.9.2 date format M/d/yyyy at 100 Hz  Filter Normal -----------",
            "Serial Number: NEO1234567890",
            "Start Time 10:00:00",
            "Start Date 1/15/2024",
            "Epoch Period (hh:mm:ss) 00:00:00",
            "Download Time 11:00:00",
            "Download Date 1/15/2024", 
            "Current Memory Address: 0",
            "Current Battery Voltage: 4.19     Mode = 61",
            "--------------------------------------------------",
            "Timestamp,Accelerometer X,Accelerometer Y,Accelerometer Z",
        ]
        # Note: 11 header lines total (indices 0-10)
        
        # Sample accelerometer data using standard US format (comma separator, period decimal)
        # These start at line index 11 (the 12th line)
        data_lines = [
            "2024-01-15 10:00:00.000,0.123,0.456,0.789",
            "2024-01-15 10:00:00.010,0.234,0.567,0.890",
            "2024-01-15 10:00:00.020,0.345,0.678,0.901",
            "2024-01-15 10:00:00.030,1.000,1.000,1.000",
            "2024-01-15 10:00:00.040,0.500,0.500,0.500",
        ]
        
        file_path = tmp_path / "actigraph_test.csv"
        with open(file_path, 'w') as f:
            f.write('\n'.join(header_lines) + '\n')
            f.write('\n'.join(data_lines))
        
        return file_path
    
    def test_parse_raw_file_columns(self, sample_actigraph_file):
        """Parsed data should have expected columns."""
        df = ActigraphParser.parse_raw_file(sample_actigraph_file)
        
        expected_columns = ['timestamp', 'acc_x', 'acc_y', 'acc_z', 'acc_magnitude']
        assert list(df.columns) == expected_columns
    
    def test_parse_raw_file_row_count(self, sample_actigraph_file):
        """Should parse all data rows."""
        df = ActigraphParser.parse_raw_file(sample_actigraph_file)
        
        assert len(df) == 5
    
    def test_magnitude_calculation(self, sample_actigraph_file):
        """Magnitude should be sqrt(x² + y² + z²)."""
        df = ActigraphParser.parse_raw_file(sample_actigraph_file)
        
        # Row 4 has (1.0, 1.0, 1.0) -> magnitude = sqrt(3) ≈ 1.732
        row = df.iloc[3]
        expected_magnitude = np.sqrt(1.0**2 + 1.0**2 + 1.0**2)
        assert abs(row['acc_magnitude'] - expected_magnitude) < 0.001
    
    def test_timestamp_parsing(self, sample_actigraph_file):
        """Timestamps should be parsed as datetime."""
        df = ActigraphParser.parse_raw_file(sample_actigraph_file)
        
        assert pd.api.types.is_datetime64_any_dtype(df['timestamp'])


class TestBangleParser:
    """Tests for BangleParser class."""
    
    @pytest.fixture
    def sample_bangle_file(self, tmp_path):
        """Create a sample Bangle.js CSV file."""
        # Bangle format: Time (delta ms), Acc_x, Acc_y, Acc_z
        data = """Time,Acc_x,Acc_y,Acc_z
80,0.1,0.2,0.3
80,0.2,0.3,0.4
80,0.3,0.4,0.5
80,0.4,0.5,0.6
80,0.5,0.6,0.7"""
        
        file_path = tmp_path / "bangle_test.csv"
        file_path.write_text(data)
        return file_path
    
    def test_parse_file_columns(self, sample_bangle_file):
        """Parsed data should have expected columns."""
        df = BangleParser.parse_file(sample_bangle_file)
        
        assert 'timestamp' in df.columns
        assert 'Acc_x' in df.columns
        assert 'Acc_y' in df.columns
        assert 'Acc_z' in df.columns
        assert 'acc_magnitude' in df.columns
        assert 'cumulative_time_ms' in df.columns
    
    def test_cumulative_time_calculation(self, sample_bangle_file):
        """Cumulative time should be sum of deltas."""
        df = BangleParser.parse_file(sample_bangle_file)
        
        # Each delta is 80ms, so cumulative should be 80, 160, 240, 320, 400
        assert df.iloc[0]['cumulative_time_ms'] == 80
        assert df.iloc[1]['cumulative_time_ms'] == 160
        assert df.iloc[4]['cumulative_time_ms'] == 400
    
    def test_magnitude_calculation(self, sample_bangle_file):
        """Magnitude should be calculated correctly."""
        df = BangleParser.parse_file(sample_bangle_file)
        
        # First row: (0.1, 0.2, 0.3) -> magnitude = sqrt(0.01 + 0.04 + 0.09) = sqrt(0.14)
        expected = np.sqrt(0.1**2 + 0.2**2 + 0.3**2)
        assert abs(df.iloc[0]['acc_magnitude'] - expected) < 0.001
    
    def test_handles_empty_file(self, tmp_path):
        """Should handle empty data gracefully."""
        file_path = tmp_path / "empty_bangle.csv"
        file_path.write_text("Time,Acc_x,Acc_y,Acc_z\n")
        
        df = BangleParser.parse_file(file_path)
        
        assert len(df) == 0
    
    def test_handles_invalid_values(self, tmp_path):
        """Should drop rows with invalid values."""
        data = """Time,Acc_x,Acc_y,Acc_z
80,0.1,0.2,0.3
invalid,0.2,0.3,0.4
80,NaN,0.4,0.5
80,0.4,0.5,0.6"""
        
        file_path = tmp_path / "invalid_bangle.csv"
        file_path.write_text(data)
        
        df = BangleParser.parse_file(file_path)
        
        # Should have 2 valid rows (first and last)
        assert len(df) == 2


class TestEmotibitParser:
    """Tests for EmotibitParser class."""
    
    @pytest.fixture
    def sample_emotibit_info(self, tmp_path):
        """Create a sample EmotiBit info JSON file."""
        import json
        info = {
            "device_id": "EMOTIBIT_001",
            "firmware_version": "1.0.0",
            "recording_start": "2024-01-15T10:00:00Z"
        }
        file_path = tmp_path / "emotibit_info.json"
        file_path.write_text(json.dumps(info))
        return file_path
    
    @pytest.fixture
    def sample_emotibit_csv(self, tmp_path):
        """Create a sample EmotiBit CSV file with accelerometer data."""
        # EmotiBit format: local_timestamp,emotibit_timestamp,data_length,type_tag,packet_number,reliability,data_0,...
        lines = [
            "1705312800000,12345,1,AX,1,100,0.5",
            "1705312800000,12345,1,AY,1,100,0.6",
            "1705312800000,12345,1,AZ,1,100,0.7",
            "1705312800010,12355,1,AX,2,100,0.6",
            "1705312800010,12355,1,AY,2,100,0.7",
            "1705312800010,12355,1,AZ,2,100,0.8",
        ]
        
        file_path = tmp_path / "emotibit_test.csv"
        file_path.write_text('\n'.join(lines))
        return file_path
    
    def test_parse_info_json(self, sample_emotibit_info):
        """Should parse JSON info file."""
        info = EmotibitParser.parse_info_json(sample_emotibit_info)
        
        assert info['device_id'] == 'EMOTIBIT_001'
        assert info['firmware_version'] == '1.0.0'
    
    def test_parse_csv_file(self, sample_emotibit_csv):
        """Should parse CSV file with variable columns."""
        df = EmotibitParser.parse_csv_file(sample_emotibit_csv)
        
        assert len(df) == 6
        assert 'type_tag' in df.columns
        assert 'local_timestamp' in df.columns
    
    def test_extract_accelerometer(self, sample_emotibit_csv):
        """Should extract and combine accelerometer axes."""
        raw_df = EmotibitParser.parse_csv_file(sample_emotibit_csv)
        acc_df = EmotibitParser.extract_accelerometer(raw_df)
        
        # Should have combined x, y, z into single rows
        assert 'acc_x' in acc_df.columns
        assert 'acc_y' in acc_df.columns
        assert 'acc_z' in acc_df.columns
        assert 'acc_magnitude' in acc_df.columns


class TestCalculateMagnitudeWindows:
    """Tests for calculate_magnitude_windows function."""
    
    def test_resamples_to_windows(self):
        """Should resample data to specified window size."""
        # Create 20 seconds of data at 10Hz (200 samples)
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01 10:00:00', periods=200, freq='100ms'),
            'acc_magnitude': np.ones(200)
        })
        
        result = calculate_magnitude_windows(df, timestamp_col='timestamp', window='5s')
        
        # 20 seconds / 5s windows = 4 windows
        assert len(result) == 4
    
    def test_calculates_mean(self):
        """Window values should be mean of samples."""
        # Create data where first 5s has values 1.0, second 5s has values 2.0
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=100, freq='100ms')
        values = np.array([1.0] * 50 + [2.0] * 50)
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'acc_magnitude': values
        })
        
        result = calculate_magnitude_windows(df, timestamp_col='timestamp', window='5s')
        
        assert len(result) == 2
        assert abs(result.iloc[0]['acc_magnitude_5s'] - 1.0) < 0.001
        assert abs(result.iloc[1]['acc_magnitude_5s'] - 2.0) < 0.001


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
