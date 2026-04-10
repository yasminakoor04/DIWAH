"""
Constants and color definitions for DIWAH Analytics Dashboard.

This module provides shared constants used across the dashboard.
"""

# =============================================================================
# UI Colors (LNU Brand)
# =============================================================================

COLORS = {
    'buttercup': '#FFE000',  # Primary yellow
    'lily': '#FDECB2',       # Light yellow background
    'crocus': '#8859A5',     # Purple accent
    'azalea': '#E55385',     # Pink accent
    'ivy': '#008567',        # Green accent
    'soot': '#262626'        # Dark text/borders
}

# Device-specific colors for consistent visualization
DEVICE_COLORS = {
    'actigraph': COLORS['crocus'],  # Purple
    'bangle': COLORS['ivy'],        # Green
    'emotibit': COLORS['azalea']    # Pink
}

# Canonical device names (lowercase)
DEVICE_NAMES = ['actigraph', 'bangle', 'emotibit']

# =============================================================================
# Statistical Constants
# =============================================================================

# Minimum number of samples required for correlation analysis
MIN_SAMPLES_FOR_CORRELATION = 10

# Significance level for hypothesis tests (p < 0.05)
SIGNIFICANCE_LEVEL = 0.05

# =============================================================================
# Parser Constants
# =============================================================================

# Number of header lines to skip in ActiGraph RAW files
ACTIGRAPH_HEADER_LINES = 11

# Maximum columns to read from EmotiBit CSV files
EMOTIBIT_MAX_COLUMNS = 20

# =============================================================================
# Cache Settings
# =============================================================================

# Time-to-live for cohort data cache (in seconds)
COHORT_CACHE_TTL_SECONDS = 300

# =============================================================================
# Subject to Participant Mapping
# =============================================================================

# Mapping of raw backend Subject IDs to chronological Participant labels for UI display
PARTICIPANT_MAPPING = {
    '2002': 1, '2003': 2, '2005': 3, '2006': 4, '2007': 5, 
    '2008': 6, '2009': 7, '2010': 8, '2013': 9, '2014': 10, 
    '2015': 11, '2016': 12, '2017': 13, '2018': 14, '2019': 15, 
    '2020': 16, '2021': 17, '2022': 18, '2024': 19, '2025': 20, 
    '2026': 21, '2027': 22, '2030': 23, '2032': 24, '2033': 25, 
    '2034': 26, '2035': 27, '2036': 28, '2042': 29, '2004': 30,
}
