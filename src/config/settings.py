"""
Processing settings and constants for DIWAH Dashboard.

These settings control data processing behavior and can be overridden
via environment variables where noted.
"""

import os
from typing import List

# Window size for accelerometer magnitude aggregation (seconds)
ACCELEROMETER_WINDOW_SECONDS = 5

# Device sampling rates (Hz) - used for calculations and documentation
SAMPLING_RATES = {
    'actigraph': 100,    # ActiGraph GT9X Link
    'bangle': 12.5,      # Bangle.js 2
    'emotibit': 25       # EmotiBit
}

# Excluded subjects - these are filtered out from analysis
# Reason: Subject 2004 has corrupted/incomplete accelerometer data
# Override: Set EXCLUDED_SUBJECTS=2004,2005 environment variable
_excluded_str = os.getenv("EXCLUDED_SUBJECTS", "2004")
EXCLUDED_SUBJECTS: List[str] = [
    s.strip() for s in _excluded_str.split(",") if s.strip()
]

# Statistical analysis settings
MIN_SAMPLES_FOR_CORRELATION = 10  # Minimum samples for correlation calculation
SIGNIFICANCE_LEVEL = 0.05          # p-value threshold for significance

# Parser settings
ACTIGRAPH_HEADER_LINES = 11  # Number of header lines in Actigraph RAW files
