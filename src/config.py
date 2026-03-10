"""
DEPRECATED: Configuration has been split into src/config/ package.

This file re-exports all config values for backward compatibility.
Please update your imports to use: from src.config import ...
"""

# Re-export everything from the new config package
from .config import (
    # Paths
    DATA_ROOT,
    ACTIGRAPH_PATH,
    BANGLE_PATH,
    EMOTIBIT_PATH,
    CALORIMETRY_PATH,
    OUTPUT_ROOT,
    PROCESSED_DATA_PATH,
    PLOTS_PATH,
    ensure_output_directories,
    # Settings
    ACCELEROMETER_WINDOW_SECONDS,
    SAMPLING_RATES,
    EXCLUDED_SUBJECTS,
    # Database
    INFLUX_URL,
    INFLUX_TOKEN,
    INFLUX_ORG,
    INFLUX_BUCKET
)

__all__ = [
    'DATA_ROOT', 'ACTIGRAPH_PATH', 'BANGLE_PATH', 'EMOTIBIT_PATH', 'CALORIMETRY_PATH',
    'OUTPUT_ROOT', 'PROCESSED_DATA_PATH', 'PLOTS_PATH', 'ensure_output_directories',
    'ACCELEROMETER_WINDOW_SECONDS', 'SAMPLING_RATES', 'EXCLUDED_SUBJECTS',
    'INFLUX_URL', 'INFLUX_TOKEN', 'INFLUX_ORG', 'INFLUX_BUCKET'
]
