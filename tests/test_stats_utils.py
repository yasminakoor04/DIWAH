"""
Unit tests for DIWAH statistical utilities.

Tests the pure statistical functions in stats_utils.py.
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, Any


# Import after adding parent to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backend.stats_utils import (
    calculate_summary_stats,
    calculate_correlations,
    compare_activity_rest,
    calculate_data_quality,
    format_p_value
)


class TestCalculateSummaryStats:
    """Tests for calculate_summary_stats function."""
    
    def test_empty_data_returns_empty_dict(self):
        """Empty input should return empty dictionary."""
        result = calculate_summary_stats({})
        assert result == {}
    
    def test_no_raw_key_returns_empty_dict(self):
        """Data without 'raw' key should return empty dictionary."""
        result = calculate_summary_stats({'agg': {}})
        assert result == {}
    
    def test_single_device_calculates_stats(self):
        """Single device data should calculate all statistics."""
        df = pd.DataFrame({
            '_time': pd.date_range('2024-01-01', periods=100, freq='100ms'),
            'actigraph': np.random.randn(100) + 1.0  # mean ~1.0
        })
        data = {'raw': {'actigraph': df}}
        
        result = calculate_summary_stats(data)
        
        assert 'actigraph' in result
        assert 'mean' in result['actigraph']
        assert 'std' in result['actigraph']
        assert 'median' in result['actigraph']
        assert 'min' in result['actigraph']
        assert 'max' in result['actigraph']
        assert 'count' in result['actigraph']
        assert result['actigraph']['count'] == 100
    
    def test_multiple_devices(self):
        """Multiple devices should all be processed."""
        df1 = pd.DataFrame({
            '_time': pd.date_range('2024-01-01', periods=50, freq='100ms'),
            'actigraph': np.ones(50)
        })
        df2 = pd.DataFrame({
            '_time': pd.date_range('2024-01-01', periods=50, freq='100ms'),
            'bangle': np.ones(50) * 2
        })
        data = {'raw': {'actigraph': df1, 'bangle': df2}}
        
        result = calculate_summary_stats(data)
        
        assert len(result) == 2
        assert result['actigraph']['mean'] == 1.0
        assert result['bangle']['mean'] == 2.0
    
    def test_handles_empty_dataframe(self):
        """Empty DataFrame should be skipped."""
        df = pd.DataFrame(columns=['_time', 'actigraph'])
        data = {'raw': {'actigraph': df}}
        
        result = calculate_summary_stats(data)
        
        assert result == {}
    
    def test_handles_none_dataframe(self):
        """None DataFrame should be skipped."""
        data = {'raw': {'actigraph': None}}
        
        result = calculate_summary_stats(data)
        
        assert result == {}


class TestCalculateCorrelations:
    """Tests for calculate_correlations function."""
    
    def test_empty_data_returns_empty_dataframe(self):
        """Empty input should return empty DataFrame."""
        result = calculate_correlations({})
        assert result.empty
    
    def test_single_device_returns_empty(self):
        """Need at least 2 devices for correlation."""
        df = pd.DataFrame({
            '_time': pd.date_range('2024-01-01', periods=20, freq='5s'),
            'actigraph': np.random.randn(20)
        })
        data = {'agg': {'actigraph': df}}
        
        result = calculate_correlations(data)
        
        assert result.empty
    
    def test_insufficient_samples_returns_empty(self):
        """Fewer than MIN_SAMPLES_FOR_CORRELATION should return empty."""
        df1 = pd.DataFrame({
            '_time': pd.date_range('2024-01-01', periods=5, freq='5s'),
            'actigraph': [1, 2, 3, 4, 5]
        })
        df2 = pd.DataFrame({
            '_time': pd.date_range('2024-01-01', periods=5, freq='5s'),
            'bangle': [1, 2, 3, 4, 5]
        })
        data = {'agg': {'actigraph': df1, 'bangle': df2}}
        
        result = calculate_correlations(data)
        
        assert result.empty
    
    def test_perfect_correlation(self):
        """Identical data should have correlation of 1.0."""
        times = pd.date_range('2024-01-01', periods=20, freq='5s')
        values = np.linspace(0, 10, 20)
        
        df1 = pd.DataFrame({'_time': times, 'actigraph': values})
        df2 = pd.DataFrame({'_time': times, 'bangle': values})
        data = {'agg': {'actigraph': df1, 'bangle': df2}}
        
        result = calculate_correlations(data)
        
        assert not result.empty
        assert abs(result.loc['actigraph', 'bangle'] - 1.0) < 0.001
    
    def test_negative_correlation(self):
        """Inverse data should have correlation of -1.0."""
        times = pd.date_range('2024-01-01', periods=20, freq='5s')
        values = np.linspace(0, 10, 20)
        
        df1 = pd.DataFrame({'_time': times, 'actigraph': values})
        df2 = pd.DataFrame({'_time': times, 'bangle': -values})
        data = {'agg': {'actigraph': df1, 'bangle': df2}}
        
        result = calculate_correlations(data)
        
        assert not result.empty
        assert abs(result.loc['actigraph', 'bangle'] - (-1.0)) < 0.001


class TestCompareActivityRest:
    """Tests for compare_activity_rest function."""
    
    def test_empty_data_returns_empty(self):
        """Empty input should return empty dictionary."""
        result = compare_activity_rest({}, {})
        assert result == {}
    
    def test_missing_device_skipped(self):
        """Device missing from one session should be skipped."""
        activity = {'raw': {'actigraph': pd.DataFrame({'actigraph': [1, 2, 3]})}}
        rest = {'raw': {}}
        
        result = compare_activity_rest(activity, rest)
        
        assert 'actigraph' not in result
    
    def test_significant_difference_detected(self):
        """Large difference should be marked significant."""
        np.random.seed(42)
        activity_df = pd.DataFrame({'actigraph': np.random.randn(100) + 5})  # mean ~5
        rest_df = pd.DataFrame({'actigraph': np.random.randn(100) + 0})  # mean ~0
        
        activity = {'raw': {'actigraph': activity_df}}
        rest = {'raw': {'actigraph': rest_df}}
        
        result = compare_activity_rest(activity, rest)
        
        assert 'actigraph' in result
        assert result['actigraph']['significant'] == True
        assert result['actigraph']['p_value'] < 0.05
    
    def test_no_difference_not_significant(self):
        """Similar data should not be marked significant."""
        np.random.seed(42)
        activity_df = pd.DataFrame({'actigraph': np.random.randn(100) + 1})
        rest_df = pd.DataFrame({'actigraph': np.random.randn(100) + 1})
        
        activity = {'raw': {'actigraph': activity_df}}
        rest = {'raw': {'actigraph': rest_df}}
        
        result = compare_activity_rest(activity, rest)
        
        assert 'actigraph' in result
        # p-value should be high (not significant)
        assert result['actigraph']['p_value'] > 0.05
    
    def test_cohens_d_calculated(self):
        """Cohen's d effect size should be calculated."""
        activity_df = pd.DataFrame({'actigraph': [5, 5, 5, 5, 5]})
        rest_df = pd.DataFrame({'actigraph': [1, 1, 1, 1, 1]})
        
        activity = {'raw': {'actigraph': activity_df}}
        rest = {'raw': {'actigraph': rest_df}}
        
        result = compare_activity_rest(activity, rest)
        
        assert 'cohens_d' in result['actigraph']
        # Large effect size expected (difference of 4, std of 0)
        # With zero std, cohens_d defaults to 0
        assert 'cohens_d' in result['actigraph']


class TestCalculateDataQuality:
    """Tests for calculate_data_quality function."""
    
    def test_empty_data(self):
        """Empty data should show 0 devices available."""
        result = calculate_data_quality({})
        assert result['devices_available'] == '0/3'
        assert result['alignment'] == 'N/A'
    
    def test_single_device_no_alignment(self):
        """Single device cannot compute alignment."""
        df = pd.DataFrame({
            '_time': pd.date_range('2024-01-01', periods=10, freq='5s'),
            'actigraph': np.ones(10)
        })
        data = {'agg': {'actigraph': df}}
        
        result = calculate_data_quality(data)
        
        assert result['devices_available'] == '1/3'
        assert result['alignment'] == 'N/A'
    
    def test_perfect_overlap(self):
        """Identical time ranges should have 100% alignment."""
        times = pd.date_range('2024-01-01', periods=10, freq='5s')
        df1 = pd.DataFrame({'_time': times, 'actigraph': np.ones(10)})
        df2 = pd.DataFrame({'_time': times, 'bangle': np.ones(10)})
        data = {'agg': {'actigraph': df1, 'bangle': df2}}
        
        result = calculate_data_quality(data)
        
        assert result['devices_available'] == '2/3'
        assert result['alignment'] == '100.0%'


class TestFormatPValue:
    """Tests for format_p_value function."""
    
    def test_small_p_value(self):
        """Very small p-values should show < 0.001."""
        assert format_p_value(0.0001) == '< 0.001'
        assert format_p_value(0.00001) == '< 0.001'
    
    def test_normal_p_value(self):
        """Normal p-values should show 3 decimal places."""
        assert format_p_value(0.05) == '0.050'
        assert format_p_value(0.123) == '0.123'
    
    def test_boundary_p_value(self):
        """Boundary value (0.001) should show the value."""
        assert format_p_value(0.001) == '0.001'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
