"""
File and directory path configuration for DIWAH Dashboard.

All paths can be overridden via environment variables for different deployments.
"""

import os
from pathlib import Path

# Data root - override with DATA_ROOT environment variable
# Default: look for Hanna's OneDrive path, then the legacy yasmi path
_project_root = Path(__file__).parent.parent.parent
_hanna_onedrive = Path(r"C:\Users\Hanna\Linnéuniversitetet\Oxana Sachenkova - diwah-wearable-anonymized")
_legacy_yasmi = Path(r"C:\Users\yasmi\Downloads\diwah-anonymized\diwah-anonymized")

if _hanna_onedrive.exists():
    _default_data_root = str(_hanna_onedrive)
elif _legacy_yasmi.exists():
    _default_data_root = str(_legacy_yasmi)
else:
    _default_data_root = str(_hanna_onedrive)  # Best guess for server env variable override

DATA_ROOT = Path(os.getenv("DATA_ROOT", _default_data_root))

# Device-specific data paths
ACTIGRAPH_PATH = DATA_ROOT / "Actigraph (research device accelerometry)"
BANGLE_PATH = DATA_ROOT / "Bangle"
EMOTIBIT_PATH = DATA_ROOT / "emotibit"
CALORIMETRY_PATH = DATA_ROOT / "calorimetry_anonymized"

# Output paths (relative to project root, not src directory)
_src_dir = Path(__file__).parent.parent
OUTPUT_ROOT = Path(os.getenv("OUTPUT_ROOT", r"c:\Users\yasmi\Downloads\diwah-anonymized\output"))
PROCESSED_DATA_PATH = OUTPUT_ROOT / "processed"
PLOTS_PATH = OUTPUT_ROOT / "plots"

# Configuration files
START_LINES_FILE = _src_dir / "config" / "start_lines.csv"


def ensure_output_directories() -> None:
    """
    Create output directories if they don't exist.
    
    Call this at application startup, not at import time.
    """
    OUTPUT_ROOT.mkdir(exist_ok=True)
    PROCESSED_DATA_PATH.mkdir(exist_ok=True)
    PLOTS_PATH.mkdir(exist_ok=True)


def validate_data_paths() -> dict:
    """
    Check which data paths exist and return status.
    
    Returns:
        Dictionary mapping path names to existence status
    """
    return {
        'DATA_ROOT': DATA_ROOT.exists(),
        'ACTIGRAPH_PATH': ACTIGRAPH_PATH.exists(),
        'BANGLE_PATH': BANGLE_PATH.exists(),
        'EMOTIBIT_PATH': EMOTIBIT_PATH.exists(),
        'CALORIMETRY_PATH': CALORIMETRY_PATH.exists()
    }
