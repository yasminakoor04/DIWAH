"""
DIWAH Dashboard Configuration Package.

This package provides configuration management split into logical modules:
- paths: File and directory path definitions
- settings: Processing parameters and constants  
- database: InfluxDB connection configuration

Usage:
    from src.config import INFLUX_URL, DATA_ROOT, SAMPLING_RATES
    
Or import specific modules:
    from src.config.paths import DATA_ROOT, ACTIGRAPH_PATH
    from src.config.settings import SAMPLING_RATES
    from src.config.database import INFLUX_URL, INFLUX_TOKEN
"""

# Re-export all configuration for backward compatibility
from .paths import (
    DATA_ROOT,
    ACTIGRAPH_PATH,
    BANGLE_PATH,
    EMOTIBIT_PATH,
    CALORIMETRY_PATH,
    OUTPUT_ROOT,
    PROCESSED_DATA_PATH,
    PLOTS_PATH,
    START_LINES_FILE,
    ensure_output_directories
)

from .settings import (
    ACCELEROMETER_WINDOW_SECONDS,
    SAMPLING_RATES,
    EXCLUDED_SUBJECTS
)

from .database import (
    INFLUX_URL,
    INFLUX_TOKEN,
    INFLUX_ORG,
    INFLUX_BUCKET
)

__all__ = [
    # Paths
    'DATA_ROOT',
    'ACTIGRAPH_PATH',
    'BANGLE_PATH', 
    'EMOTIBIT_PATH',
    'CALORIMETRY_PATH',
    'OUTPUT_ROOT',
    'PROCESSED_DATA_PATH',
    'PLOTS_PATH',
    'START_LINES_FILE',
    'ensure_output_directories',
    # Settings
    'ACCELEROMETER_WINDOW_SECONDS',
    'SAMPLING_RATES',
    'EXCLUDED_SUBJECTS',
    # Database
    'INFLUX_URL',
    'INFLUX_TOKEN',
    'INFLUX_ORG',
    'INFLUX_BUCKET'
]
